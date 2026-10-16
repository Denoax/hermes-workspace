"""Geometry/ownership/privacy contracts on fixtures; no native UI execution."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import v6_surface_review as surface


def box(x, y, width, height):
    return {'x': x, 'y': y, 'width': width, 'height': height}


class MeasuredGeometryTests(unittest.TestCase):
    def setUp(self):
        self.anchor = box(950, 100, 30, 30)
        self.panel = box(760, 136, 220, 140)
        self.viewport = {'left': 0, 'top': 0, 'width': 1000, 'height': 600}

    def test_fitting_adjacent_surface_and_stable_anchor_pass(self):
        result = surface.assess_popover(self.anchor, self.anchor, self.panel, self.viewport)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['trigger_drift_CSS_px'], 0)
        self.assertEqual(result['anchor_surface_separation_CSS_px'], 6)

    def test_trigger_size_or_position_drift_over_one_pixel_fails(self):
        for changed in ({**self.anchor, 'x': 948.9}, {**self.anchor, 'width': 31.1}):
            with self.subTest(changed=changed):
                result = surface.assess_popover(self.anchor, changed, self.panel, self.viewport)
                self.assertIn('trigger_drift_over_1_CSS_px', result['failures'])

    def test_each_clipped_edge_fails_even_with_correct_placement_label(self):
        for panel in (box(2, 136, 220, 140), box(780, 136, 220, 140),
                      box(760, 1, 220, 140), box(760, 470, 220, 140)):
            with self.subTest(panel=panel):
                result = surface.assess_popover(self.anchor, self.anchor, panel, self.viewport)
                self.assertIn('surface_outside_8_CSS_px_visual_viewport_inset', result['failures'])

    def test_visual_viewport_offsets_are_used_instead_of_zero_origin(self):
        shifted = {'left': 500, 'top': 200, 'width': 1000, 'height': 600}
        anchor, panel = box(1450, 300, 30, 30), box(1260, 336, 220, 140)
        self.assertEqual(surface.assess_popover(anchor, anchor, panel, shifted)['status'], 'PASS')

    def test_fitting_but_detached_popover_does_not_pass(self):
        result = surface.assess_popover(self.anchor, self.anchor, box(100, 300, 200, 200), self.viewport)
        self.assertIn('surface_detached_from_visible_trigger', result['failures'])

    def test_empty_or_nonfinite_measured_rect_is_rejected(self):
        for bad in (box(0, 0, 0, 4), box(0, 0, 4, -1), box(float('nan'), 0, 4, 4), box(0, 0, float('inf'), 4)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                surface.assess_popover(bad, self.anchor, self.panel, self.viewport)


class OwnershipAndPreservationTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b, self.old = 'a' * 32, 'b' * 32, 'c' * 32
        self.case = {'prefix': 'V6review-1234abcd', 'created_session_ids': [self.a, self.b],
                     'before_session_ids': [self.old], 'viewed_session_id': self.a, 'target_session_id': self.b}
        self.sessions = [{'id': self.a, 'title': 'V6review-1234abcd · A'},
                         {'id': self.b, 'title': 'V6review-1234abcd · B'}]
        self.context = {'view': {'session_id': self.a}, 'draft': {'text': 'private draft should not export'},
                        'prompt': 'private draft should not export', 'model': 'normal',
                        'storage': {surface.COMPOSING_INTENT: 'private storage value'},
                        'reading': {'top': 275.25, 'left': 0}}

    def test_distinct_new_live_nonce_confirmed_records_are_required(self):
        self.assertEqual(surface.owns_case(self.case, self.sessions), (self.a, self.b))
        for changes in ({'target_session_id': self.a}, {'before_session_ids': [self.a]},
                        {'created_session_ids': [self.a, self.a]}, {'prefix': 'original-user-project'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                surface.owns_case({**self.case, **changes}, self.sessions)

    def test_live_missing_or_renamed_target_is_not_accepted_by_id_alone(self):
        for sessions in (self.sessions[:1], [self.sessions[0], {'id': self.b, 'title': 'Unclassified user record'}]):
            with self.subTest(sessions=sessions), self.assertRaises(ValueError):
                surface.owns_case(self.case, sessions)

    def test_actual_interaction_nonce_still_requires_distinct_new_live_records(self):
        prefix = 'V6interaction-123456abcdef'
        case = {**self.case, 'prefix': prefix}
        sessions = [{**row, 'title': prefix + ' · ' + role} for row, role in zip(self.sessions, ('A', 'B'))]
        self.assertEqual(surface.owns_case(case, sessions), (self.a, self.b))
        for invalid in ({**case, 'prefix': prefix + 'extra'}, {**case, 'before_session_ids': [self.b]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                surface.owns_case(invalid, sessions)

    def test_same_private_context_outputs_only_hashes_and_booleans(self):
        result = surface.compare_context(self.context, deepcopy(self.context))
        self.assertEqual(result['status'], 'PASS')
        self.assertNotIn('private draft', repr(result))
        self.assertNotIn('private storage', repr(result))
        self.assertFalse(result['draft_text_exported'])
        self.assertFalse(result['storage_values_exported'])

    def test_view_draft_attachment_storage_model_or_reading_change_fails(self):
        changes = {'view': {'session_id': self.b}, 'draft': {'text': 'changed'}, 'prompt': 'changed',
                   'model': 'abliterated', 'storage': {surface.COMPOSING_INTENT: None},
                   'reading': {'top': 280, 'left': 0}}
        for key, value in changes.items():
            changed = {**deepcopy(self.context), key: value}
            with self.subTest(key=key):
                result = surface.compare_context(self.context, changed)
                self.assertEqual(result['status'], 'FAIL')

    def test_native_key_refuses_unqualified_input_and_unbounded_symbols(self):
        class Browser:
            pass
        with self.assertRaisesRegex(RuntimeError, 'fresh_native_XTEST'):
            surface.native_key(Browser(), 'Tab')
        for value in ('Control_L', 'F12', ';', 'Return; rm', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                surface.native_key(Browser(), value)

    def test_context_snapshot_reads_composing_intent_and_current_attachment_scope(self):
        class Browser:
            expressions = []
            def evaluate(self, expression):
                self.expressions.append(expression)
                if 'localStorage' in expression:
                    return {surface.COMPOSING_INTENT: None}
                if 'scrollTop' in expression:
                    return {'top': 0, 'left': 0}
                return None
        browser = Browser()
        reads = []
        def rpc_read(method, fields):
            reads.append((method, fields))
            return {'session_id': self.a} if method == 'view.read' else {'text': ''}
        value = surface.capture_context(browser, rpc_read)
        storage_read = next(item for item in browser.expressions if 'localStorage' in item)
        self.assertIn(surface.COMPOSING_INTENT, storage_read)
        self.assertIn('hermes:draft-attachments:v1:' + self.a, storage_read)
        self.assertEqual(reads, [('view.read', {}), ('draft.read', {'session_id': self.a})])
        self.assertEqual(value['draft'], {'text': ''})


class FailureEvidenceTests(unittest.TestCase):
    def test_failed_measurements_survive_without_converting_the_error_to_success(self):
        class Review:
            def __init__(self):
                self.rows = []
            @surface.recorded
            def measured_failure(self):
                self.rows[-1]['measured_width'] = 47.5
                raise RuntimeError('observed_geometry_failure')
        review = Review()
        with self.assertRaisesRegex(RuntimeError, 'observed_geometry_failure'):
            review.measured_failure()
        self.assertEqual(review.rows[0]['status'], 'FAIL')
        self.assertEqual(review.rows[0]['measured_width'], 47.5)
        self.assertEqual(review.rows[0]['error_code'], 'observed_geometry_failure')

    def test_success_is_explicit_and_private_freeform_errors_are_not_exported(self):
        class Review:
            def __init__(self):
                self.rows = []
            @surface.recorded
            def succeeds(self):
                return {'measured': True}
            @surface.recorded
            def private_error(self):
                raise RuntimeError('private user draft should not export')
        review = Review()
        self.assertEqual(review.succeeds()['status'], 'PASS')
        with self.assertRaises(RuntimeError):
            review.private_error()
        self.assertNotIn('private user draft', repr(review.rows))
        self.assertEqual(review.rows[1]['error_code'], 'see_private_outer_error')


if __name__ == '__main__':
    unittest.main()
