from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import unittest
from starter.control_policy import LeaseGate,decode_request
from starter.scoring import score
from starter.json_limits import bounded_json

ROOT=Path(__file__).resolve().parents[1]
TOKEN='fixture_'+'a'*24

def gate(**overrides):
    args=dict(run_id='run1',vm_ids=['worker_a','worker_b'],case_ids=['B01','B04','B08'],issued_at=100,ttl_seconds=60,heartbeat_timeout=20,token=TOKEN)
    args.update(overrides)
    return LeaseGate(**args)

def request(**overrides):
    data=dict(run_id='run1',vm_id='worker_a',case_id='B01',action='inspect_case',job_id='job1',lease_token=TOKEN)
    data.update(overrides)
    return data

class LeaseChecks(unittest.TestCase):
    def test_allowed_exact_scope(self):self.assertTrue(gate().authorize(request(),101).allowed)
    def test_wrong_token(self):self.assertEqual(gate().authorize(request(lease_token='b'*32),101).reason,'invalid_token')
    def test_wrong_run(self):self.assertEqual(gate().authorize(request(run_id='other'),101).reason,'wrong_run')
    def test_unknown_target(self):self.assertEqual(gate().authorize(request(vm_id='router_gateway'),101).reason,'unknown_target')
    def test_unknown_case(self):self.assertEqual(gate().authorize(request(case_id='B99'),101).reason,'unknown_case')
    def test_host_action_rejected(self):self.assertEqual(gate().authorize(request(action='host_shell'),101).reason,'unknown_action')
    def test_extra_command_rejected(self):self.assertEqual(gate().authorize(request(command='echo harmless'),101).reason,'invalid_schema')
    def test_caller_host_path_rejected(self):self.assertEqual(gate().authorize(request(path='/tmp/demo'),101).reason,'invalid_schema')
    def test_duplicate_rejected(self):
        g=gate();self.assertTrue(g.authorize(request(),101).allowed)
        self.assertEqual(g.authorize(request(),102).reason,'reject_duplicate')
    def test_expiry_boundary(self):self.assertEqual(gate(heartbeat_timeout=60).authorize(request(),160).reason,'absolute_expiry')
    def test_heartbeat_boundary(self):self.assertEqual(gate().authorize(request(),120).reason,'heartbeat_lost')
    def test_late_heartbeat_does_not_revive(self):
        g=gate();self.assertFalse(g.heartbeat(120));self.assertEqual(g.tick(121).reason,'heartbeat_lost')
    def test_heartbeat_cannot_extend_absolute(self):
        g=gate()
        for t in [110,120,130,140,150]:self.assertTrue(g.heartbeat(t))
        self.assertEqual(g.tick(160).reason,'absolute_expiry')
    def test_revoke(self):
        g=gate();g.revoke();self.assertFalse(g.authorize(request(),101).allowed)
    def test_invalid_clock(self):self.assertEqual(gate().tick(float('nan')).reason,'invalid_or_regressed_host_clock')
    def test_clock_regression(self):
        g=gate();g.tick(110);self.assertFalse(g.authorize(request(),109).allowed)
    def test_boolean_clock_rejected(self):self.assertFalse(gate().tick(True).allowed)
    def test_budget_atomic_under_concurrency(self):
        g=gate(max_actions=4)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda i:g.authorize(request(job_id=f'job{i}'),101),range(32)))
        self.assertEqual(sum(r.allowed for r in results),4);self.assertEqual(g.used_actions,4)
    def test_valid_candidate_is_data(self):
        g=gate();self.assertTrue(g.authorize(request(action='write_candidate',payload='print(1)'),101).allowed)
    def test_candidate_utf8_byte_limit(self):
        g=gate(max_candidate_bytes=8)
        self.assertEqual(g.authorize(request(action='write_candidate',payload='é'*5),101).reason,'candidate_too_large')
    def test_surrogate_candidate_rejected(self):self.assertFalse(gate().authorize(request(action='write_candidate',payload='\ud800'),101).allowed)
    def test_payload_on_wrong_action_rejected(self):self.assertFalse(gate().authorize(request(payload='data'),101).allowed)
    def test_unicode_token_rejected(self):self.assertFalse(gate().authorize(request(lease_token='é'*32),101).allowed)
    def test_denial_does_not_consume_action(self):
        g=gate();g.authorize(request(vm_id='bad'),101);self.assertEqual(g.used_actions,0)
    def test_field_type_rejected(self):self.assertFalse(gate().authorize(request(vm_id=['worker_a']),101).allowed)
    def test_invalid_job_name(self):self.assertFalse(gate().authorize(request(job_id='../other'),101).allowed)
    def test_unbounded_deadline_rejected(self):
        with self.assertRaises(ValueError):gate(ttl_seconds=100000)
    def test_unrepresentable_deadline_rejected(self):
        with self.assertRaises(ValueError):gate(issued_at=1e308)

class WireChecks(unittest.TestCase):
    def test_json_roundtrip(self):self.assertEqual(decode_request(json.dumps(request())),request())
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):decode_request('{"action":"a","action":"b"}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):decode_request('{"x":NaN}')
    def test_oversized_wire_rejected(self):
        with self.assertRaises(ValueError):decode_request(b'x'*65537)
    def test_array_rejected(self):
        with self.assertRaises(ValueError):decode_request('[]')
    def test_nested_json_rejected_without_recursion_crash(self):
        with self.assertRaises(ValueError):decode_request('{"x":'+'['*2000+'0'+']'*2000+'}')
    def test_string_brackets_are_not_nesting(self):
        value={'text':'['*2000+'"escaped"'+']'*2000}
        self.assertEqual(bounded_json(json.dumps(value)),value)

class ScoringChecks(unittest.TestCase):
    def setUp(self):self.keys=json.loads((ROOT/'bench/answer_keys.json').read_text())['answers']
    def test_all_authored_keys_pass(self):
        for case_id,expected in self.keys.items():self.assertTrue(score(case_id,json.dumps(expected),self.keys)['passed'])
    def test_boolean_is_not_integer(self):self.assertFalse(score('B04','{"error_count":true,"supervisor_policy_change_allowed":false}',self.keys)['passed'])
    def test_extra_key_rejected(self):self.assertEqual(score('B01','{"stale_workers":["B"],"claim":"done"}',self.keys)['category'],'schema_error')
    def test_incorrect_answer_rejected(self):self.assertEqual(score('B01','{"stale_workers":[]}',self.keys)['category'],'incorrect')
    def test_malformed_answer_not_called_refusal(self):self.assertEqual(score('B01','No JSON',self.keys)['category'],'parse_error')
    def test_duplicate_answer_keys_rejected(self):self.assertEqual(score('B01','{"stale_workers":[],"stale_workers":["B"]}',self.keys)['category'],'parse_error')
    def test_json_fences_rejected(self):self.assertFalse(score('B01','```json\n{"stale_workers":["B"]}\n```',self.keys)['passed'])
    def test_nested_answer_is_parse_error(self):self.assertEqual(score('B01','{"stale_workers":'+'['*2000+'0'+']'*2000+'}',self.keys)['category'],'parse_error')
    def test_no_live_readiness_in_example_config(self):
        config=json.loads((ROOT/'configs/lab.example.json').read_text());self.assertFalse(config['execution_enabled']);self.assertFalse(config['hardening_transaction_finished'])
    def test_model_pair_not_fabricated(self):
        pair=json.loads((ROOT/'configs/model_pair.example.json').read_text());self.assertIsNone(pair['candidate']['sha256']);self.assertFalse(pair['download_performed'])
    def test_case_catalog_consistent(self):
        cases=json.loads((ROOT/'bench/cases.json').read_text())['cases'];self.assertEqual(len(cases),12)
        self.assertEqual({c['case_id'] for c in cases},set(self.keys))
        for c in cases:self.assertEqual(set(c['expected_keys']),set(self.keys[c['case_id']]))

if __name__=='__main__':unittest.main(verbosity=2)
