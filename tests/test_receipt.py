"""Fixture receipt contracts; these fixtures are never model evidence."""
import unittest
from lab.receipt import trial_rows


class ReceiptContracts(unittest.TestCase):
    def test_failed_gate_preserves_all_missing_trials_as_unscored(self):
        rows=trial_rows({'evidence_kind':'trusted_native_control_receipt'}, {},{})
        self.assertEqual(len(rows['smoke']),6);self.assertEqual(len(rows['matrix']),24)
        self.assertTrue(all(row['passed'] is None for stage in rows.values() for row in stage))

    def test_wrong_model_identity_cannot_be_imported_as_a_completed_trial(self):
        record={'evidence_kind':'trusted_native_control_receipt','smoke':[{'status':'ok','arm':'normal',
            'case_id':'B01','evidence_kind':'real_guest_Hermes','model_sha256':'b'*64}]}
        with self.assertRaisesRegex(ValueError,'loaded_model_identity_mismatch'):
            trial_rows(record,{}, {'normal':{'sha256':'a'*64}})


if __name__=='__main__':unittest.main()
