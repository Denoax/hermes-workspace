"""One-pass coordinate observation contracts; no X display or browser created."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import v6_zoom_restore as probe


class Browser:
    def rect(self, selector):
        assert selector == '#settings-toggle'
        return {'x': 1220, 'y': 20, 'width': 80, 'height': 40}


class OneRequalificationTests(unittest.TestCase):
    def setUp(self):
        self.client = {'at': [2220, 90], 'size': [1320, 900], 'address': '0x123'}
        self.calls = []

    def fresh(self, _browser, _native, gx, gy, expected_address):
        self.calls.append((gx, gy, expected_address))
        return {'requested_native': [gx, gy], 'cursor': {'x': gx, 'y': gy},
                'event': {'sequence': len(self.calls), 'x': gx - 2220, 'y': gy - 90, 'trusted': True,
                          'target': 'settings-toggle' if len(self.calls) > 4 else None},
                'fresh_DOM_event': True, 'cursor_matches': True}

    def test_one_fixed_body_pair_pass_and_nine_points_without_click_or_retry(self):
        with patch.object(probe, 'point_observation', side_effect=self.fresh):
            result = probe.qualify_points_once(Browser(), object(), self.client)
        self.assertEqual(result['status'], 'PASS_POINTS_ONLY')
        self.assertEqual(result['qualification_attempts'], 1)
        self.assertEqual(len(self.calls), 13)
        self.assertEqual(len(result['nine_points']), 9)
        self.assertEqual(result['mapping'], [1, 1, 2220, 90])
        self.assertFalse(result['clicks_or_settings_changes'])

    def test_stale_event_is_not_reported_as_measured_509_pixel_displacement(self):
        def stale(*args):
            value = self.fresh(*args)
            if len(self.calls) == 5:
                value['fresh_DOM_event'] = False
                value['event'].update(x=726, y=450, target=None)
            return value
        with patch.object(probe, 'point_observation', side_effect=stale):
            result = probe.qualify_points_once(Browser(), object(), self.client)
        self.assertEqual(result['status'], 'FAIL_SETTINGS_POINT')
        self.assertIsNone(result['nine_points'][0]['fresh_event_CSS_error'])
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(result['qualification_attempts'], 1)

    def test_missing_body_event_stops_without_wait_widening_or_a_second_attempt(self):
        def absent(*args):
            value = self.fresh(*args); value['fresh_DOM_event'] = False; return value
        with patch.object(probe, 'point_observation', side_effect=absent):
            result = probe.qualify_points_once(Browser(), object(), self.client)
        self.assertEqual(result['status'], 'FAIL_BODY_EVENT')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(probe.POINT_EVENT_SECONDS, .4)

    def test_outside_app_point_is_rejected_before_native_motion(self):
        class BadRect(Browser):
            def rect(self, selector):
                return {'x': 1400, 'y': 20, 'width': 80, 'height': 40}
        with patch.object(probe, 'point_observation', side_effect=self.fresh), self.assertRaisesRegex(RuntimeError, 'inside_original_app'):
            probe.qualify_points_once(BadRect(), object(), self.client)
        self.assertEqual(len(self.calls), 4)

    def test_unstable_calibration_is_not_hidden_by_repeated_mapping_attempts(self):
        def drift(*args):
            value = self.fresh(*args)
            if len(self.calls) > 2:
                value['event']['x'] += 10
            return value
        with patch.object(probe, 'point_observation', side_effect=drift), self.assertRaisesRegex(RuntimeError, 'not_stable'):
            probe.qualify_points_once(Browser(), object(), self.client)
        self.assertEqual(len(self.calls), 4)


if __name__ == '__main__':
    unittest.main()
