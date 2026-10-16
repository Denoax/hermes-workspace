"""Pure ownership-guard fixtures only: no browser, RPC, native input or model."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import probe_v6_historic_citation as probe


class HistoricGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_id, session_id, attachment_id = '1' * 32, '2' * 32, '3' * 32
        attachment = {'id': attachment_id, 'metadata': {'search': {'provider': 'Wikipedia', 'sources': [{'url': 'https://en.wikipedia.org/wiki/Maple'}]}}}
        cls.recorded = {'nonce': 'V6interaction-fixture', 'project_id': '4' * 32, 'session_id': session_id,
            'attachment_id': attachment_id, 'attachment': attachment,
            'sources': deepcopy(attachment['metadata']['search']['sources']),
            'run': {'id': run_id, 'session': session_id, 'state': 'completed', 'model': 'normal',
                'identity': {'arm': 'normal', 'context': 65536},
                'settings': {'reasoning': 'off', 'prompt_sha256': 'unused_fixture_hash', 'attachments': [attachment_id]}}}

    def values(self):
        # Synthetic message bytes exercise guard rejection; this is never a
        # production response fixture and is not passed to a browser/backend.
        case = deepcopy(self.recorded)
        prompt, answer = 'fixture prompt', 'fixture answer [1]'
        case['prompt_sha256'], case['answer_sha256'] = probe.text_sha(prompt), probe.text_sha(answer)
        case['run']['settings']['prompt_sha256'] = case['prompt_sha256']
        run, metadata = deepcopy(case['run']), deepcopy(case['attachment'])
        projects = [{'id': case['project_id'], 'label': case['nonce'] + ' · Action review'}]
        sessions = [{'id': case['session_id'], 'project': case['project_id'], 'arm': 'normal',
                     'title': case['nonce'] + ' · Citation check'}]
        snapshot = {'runs': [deepcopy(run)], 'messages': [
            {'role': 'user', 'text': prompt, 'job': run['id']},
            {'role': 'assistant', 'text': answer, 'job': run['id']}],
            'attachments': {run['id']: [deepcopy(metadata)]}}
        return [case, projects, sessions, snapshot, run, {'text': '', 'mode': 'chat'}, [], metadata, None]

    def test_exact_two_message_fixture_satisfies_guard(self):
        self.assertTrue(probe.validate_historic(*self.values()))

    def test_changed_project_title_relation_or_arm_is_refused(self):
        for index, field, replacement in ((1, 'label', 'changed'), (2, 'title', 'changed'),
                                           (2, 'project', 'a' * 32), (2, 'arm', 'abliterated')):
            with self.subTest(field=field):
                values = self.values(); values[index][0][field] = replacement
                with self.assertRaises(RuntimeError): probe.validate_historic(*values)

    def test_later_message_or_second_run_is_refused(self):
        for key in ('messages', 'runs'):
            with self.subTest(key=key):
                values = self.values(); values[3][key].append(deepcopy(values[3][key][0]))
                with self.assertRaises(RuntimeError): probe.validate_historic(*values)

    def test_changed_prompt_answer_or_message_job_is_refused(self):
        for index, key, replacement in ((0, 'text', 'later draft'), (1, 'text', 'later answer [1]'), (1, 'job', 'b' * 32)):
            with self.subTest(index=index, key=key):
                values = self.values(); values[3]['messages'][index][key] = replacement
                with self.assertRaises(RuntimeError): probe.validate_historic(*values)

    def test_modified_run_is_refused_even_if_snapshot_agrees(self):
        values = self.values(); values[4]['settings']['reasoning'] = 'on'; values[3]['runs'] = [deepcopy(values[4])]
        with self.assertRaises(RuntimeError): probe.validate_historic(*values)

    def test_draft_jobs_or_stored_selection_is_refused(self):
        for index, replacement in ((5, {'text': 'later private draft', 'mode': 'chat'}),
                                   (6, [{'id': 'c' * 32, 'state': 'completed'}]),
                                   (8, '{"version":1,"ids":[]}')):
            with self.subTest(index=index):
                values = self.values(); values[index] = replacement
                with self.assertRaises(RuntimeError): probe.validate_historic(*values)

    def test_modified_canonical_metadata_is_refused(self):
        values = self.values(); values[7]['metadata']['search']['query'] = 'changed query'
        values[3]['attachments'][values[4]['id']] = [deepcopy(values[7])]
        with self.assertRaises(RuntimeError): probe.validate_historic(*values)

    def test_unrecorded_turn_attachment_is_refused(self):
        values = self.values(); values[3]['attachments'][values[4]['id']].append(deepcopy(values[7]))
        with self.assertRaises(RuntimeError): probe.validate_historic(*values)


if __name__ == '__main__':
    unittest.main(verbosity=2)
