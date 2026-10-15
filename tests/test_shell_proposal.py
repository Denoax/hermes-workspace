"""Pure receipt-ownership guards only; never production/UI/native evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/'scripts/probe_v5_shell.py'
spec = importlib.util.spec_from_file_location('private_shell_proposal',path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class OwnedCaseGuards(unittest.TestCase):
    def setUp(self):
        self.case = {'status':'PASS_SCOPED_TECHNICAL','prefix':'V5review-1234abcd',
                     'nonce_location':'suffix',
                     'projects':[{'id':'a'*32,'label':'Local research · V5review-1234abcd'}],
                     'sessions':[{'id':'b'*32,'project':'a'*32,'title':'Long conversation title · V5review-1234abcd'}],
                     'selected_session_id':'b'*32}

    def test_accepts_selected_session_in_the_positive_owned_set(self):
        prefix,selected = probe.owned_case(copy.deepcopy(self.case))
        self.assertEqual(prefix,'V5review-1234abcd')
        self.assertEqual(selected['id'],'b'*32)
        self.assertTrue(selected['title'].endswith(prefix))

    def test_rejects_a_selected_record_not_in_the_positive_set(self):
        self.case['selected_session_id'] = 'c'*32
        with self.assertRaises(ValueError):
            probe.owned_case(self.case)

    def test_rejects_a_selected_session_pointing_outside_owned_projects(self):
        self.case['sessions'][0]['project'] = 'c'*32
        with self.assertRaises(ValueError):
            probe.owned_case(self.case)

    def test_rejects_duplicate_record_ids(self):
        self.case['sessions'].append(dict(self.case['sessions'][0]))
        with self.assertRaises(ValueError):
            probe.owned_case(self.case)

    def test_rejects_unverified_or_unrelated_receipts(self):
        for field,value in [('status','IN_PROGRESS'),('prefix','Original conversations')]:
            case = copy.deepcopy(self.case)
            case[field] = value
            with self.subTest(field=field),self.assertRaises(ValueError):
                probe.owned_case(case)

    def test_rejects_malformed_receipt_shapes_and_identifiers(self):
        for case in [None,[],{**self.case,'projects':['invalid']},
                     {**self.case,'projects':[{'id':'../outside','label':'Local research · V5review-1234abcd'}]},
                     {**self.case,'sessions':[{'id':'b'*32,'project':'a'*32,'title':'Unrelated conversation'}]}]:
            with self.subTest(case=case),self.assertRaises(ValueError):
                probe.owned_case(case)


class CalibrationLifetime(unittest.TestCase):
    def test_retiring_native_input_clears_mapping_before_close(self):
        events = []
        class Browser: pass
        browser = Browser()
        class Native:
            def close(self):
                events.append((browser._native_input,browser._native_coordinates))
        browser._native_input = Native()
        browser._native_coordinates = (2,2,1,1,'owned')
        probe.retire_native_input(browser)
        self.assertEqual(events,[(None,None)])

    def test_failed_native_close_cannot_keep_stale_coordinates(self):
        class Browser: pass
        class Native:
            def close(self): raise RuntimeError('close_failed')
        browser = Browser()
        browser._native_input = Native()
        browser._native_coordinates = (2,2,1,1,'owned')
        with self.assertRaisesRegex(RuntimeError,'close_failed'):
            probe.retire_native_input(browser)
        self.assertIsNone(browser._native_coordinates)
        self.assertIsNone(browser._native_input)

    def test_targeted_mode_selects_only_the_two_failed_rows(self):
        self.assertEqual(probe.selected_rows(True),('R01_R02_native_motion','reduced_transparency_forced_colors_high_contrast'))
        self.assertIsNone(probe.selected_rows(False))


if __name__=='__main__':
    unittest.main()
