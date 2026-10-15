import importlib.util
from pathlib import Path
import unittest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


summary = module('performance_summary')
display = module('native_display_metadata')


class SummaryTests(unittest.TestCase):
    def raw(self):
        return {'schema': 'hermes-cpu-performance-v1', 'duration_ms': 300, 'stop_reason': 'caller',
                'browser': {'dpr': 1.25}, 'longtask_status': 'observing', 'visibility': [],
                'ignored_untrusted_inputs': 2,
                'marks': [{'at_ms': 0, 'phase': 'idle'}, {'at_ms': 100, 'phase': 'generating'}],
                'frames': [{'from_ms': 10, 'to_ms': 20, 'interval_ms': 10, 'visible_entire_interval': True},
                           {'from_ms': 20, 'to_ms': 150, 'interval_ms': 130, 'visible_entire_interval': False},
                           {'from_ms': 150, 'to_ms': 260, 'interval_ms': 110, 'visible_entire_interval': True}],
                'longtasks': [{'at_ms': 160, 'duration_ms': 90}],
                'inputs': [{'at_ms': 170, 'callback_at_ms': 260, 'handler_to_next_raf_ms': 90, 'event_to_next_raf_ms': 95},
                           {'at_ms': 290, 'callback_at_ms': None, 'handler_to_next_raf_ms': None}]}

    def test_adverse_and_hidden_samples_are_retained_and_phase_crossing_is_explicit(self):
        result = summary.summarize(self.raw())
        self.assertEqual(result['overall']['raf_interval_all']['max_ms'], 130)
        self.assertEqual(result['overall']['raf_interval_all']['p95_ms'], 130)
        self.assertEqual(result['overall']['raf_interval_visible_entire_interval']['count'], 2)
        self.assertEqual(result['phases'][0]['raf_interval_all']['count'], 1)
        self.assertEqual(result['phases'][0]['crossing_phase_measurements'], 1)
        self.assertEqual(result['phases'][1]['longtask_duration']['max_ms'], 90)
        self.assertEqual(result['overall']['inputs_without_next_callback'], 1)
        self.assertEqual(result['phases'][1]['trusted_event_to_next_raf_callback']['p95_ms'], 95)
        self.assertFalse(result['coverage_limited'])

    def test_limit_and_missing_support_are_not_reported_as_full_coverage(self):
        raw = self.raw(); raw.update(stop_reason='frame_limit', longtask_status='unsupported')
        result = summary.summarize(raw)
        self.assertTrue(result['coverage_limited'])
        self.assertEqual(result['longtask_status'], 'unsupported')
        self.assertEqual(result['status'], 'MEASURED')

    def test_invalid_and_absent_measurements_never_become_zero_latency(self):
        self.assertIsNone(summary.distribution([])['p95_ms'])
        for values in ([float('nan')], [-1], [True]):
            with self.subTest(values=values), self.assertRaises(ValueError):summary.distribution(values)
        raw = self.raw(); raw['duration_ms'] = None
        with self.assertRaises(ValueError):summary.summarize(raw)

    def test_native_metadata_excludes_serials_and_keeps_reported_scale_refresh(self):
        row = {'id': 1, 'name': 'DP-4', 'width': 1920, 'height': 1080, 'x': 1920, 'y': 0,
               'transform': 0, 'scale': 1.25, 'refreshRate': 240.299, 'focused': True,
               'serial': 'PRIVATE', 'description': 'PRIVATE', 'activeWorkspace': {'name': 'PRIVATE'}}
        result = display.sanitize_monitors([row])
        self.assertNotIn('PRIVATE', str(result))
        self.assertEqual(result['monitors'][0]['refresh_hz'], 240.299)
        self.assertEqual(result['monitors'][0]['scale'], 1.25)
        row['refreshRate'] = float('nan')
        with self.assertRaises(ValueError):display.sanitize_monitors([row])


if __name__ == '__main__':unittest.main()
