"""Bounded paired orchestration and outside deterministic grading."""
import json
from pathlib import Path
import time
from lab.report import blocked_matrix,request_usage
from starter.scoring import score


def execute_matrix(client, run_id, cases, arms=('normal', 'abliterated'), cleanup=True):
    root = Path(__file__).resolve().parents[1]
    keys = json.loads((root/'bench/answer_keys.json').read_text())['answers']
    rows = []
    absolute_deadline = time.monotonic() + 5400
    try:
        for arm in arms:
            for case_id in cases:
                row = blocked_matrix([case_id], 'not_dispatched')[0]
                row['arm'] = arm
                if time.monotonic() >= absolute_deadline:
                    row['reason'] = 'outside_batch_budget_expired'
                    rows.append(row)
                    continue
                health = client.call('heartbeat', run_id=run_id)
                if health['status'] != 'ok':
                    row['reason'] = 'native_lease_inactive'
                    rows.append(row)
                    continue
                response = client.call('run_case', run_id=run_id, vm_id='controller', case_id=case_id, arm=arm)
                if response['status'] != 'ok':
                    row['reason'] = response.get('reason', response.get('error', 'native_case_failed'))
                    rows.append(row)
                    continue
                if response.get('evidence_kind') != 'real_guest_Hermes' or type(response.get('answer')) is not str:
                    raise ValueError('native_model_trial_evidence_required')
                model_hash = response.get('model_sha256')
                if type(model_hash) is not str or len(model_hash) != 64 or any(c not in '0123456789abcdef' for c in model_hash):
                    raise ValueError('loaded_model_byte_identity_required')
                grading = score(case_id, response['answer'], keys)
                row.update(status='completed', execution_kind=arm+'_guest_Hermes' if len(arms) == 1 else 'paired_guest_Hermes',
                           passed=grading['passed'], category=grading['category'], reason=None,
                           answer=response['answer'], model_sha256=model_hash,
                           wall_seconds=response.get('wall_seconds'), ttft_seconds=response.get('ttft_seconds'),
                           prompt_tokens=response.get('prompt_tokens'), completion_tokens=response.get('completion_tokens'),
                           finish_reason=response.get('finish_reason'), refusal=None,
                           containment='qualified_native_run')
                rows.append(row)
                row.update(request_usage(response))
    finally:
        # Native teardown never depends on a model answer or grader outcome.
        if cleanup:
            stopped = client.call('stop', run_id=run_id)
            if stopped['status'] != 'ok':
                raise RuntimeError('native_fleet_stop_unconfirmed')
            cleaned = client.call('cleanup', run_id=run_id)
            if cleaned['status'] != 'ok':
                raise RuntimeError('native_cleanup_failed')
    return rows
