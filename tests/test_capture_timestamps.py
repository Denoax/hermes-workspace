"""Pure timestamp rules plus a real encoding-only fixture, never UI evidence."""
from pathlib import Path
import shutil
import tempfile
import unittest
from workspace.capture import encode_frames, frame_timeline


class FrameTimelineTests(unittest.TestCase):
    def test_distinct_17ms_frames_retain_their_timestamps(self):
        frames = [(Path(str(index)), 100 + index * .017) for index in range(12)]
        self.assertEqual([pts for _, pts in frame_timeline(frames)], list(range(0, 204, 17)))

    def test_small_clock_collision_is_bounded_without_dropping_a_frame(self):
        self.assertEqual([pts for _, pts in frame_timeline([('a', 1), ('b', 1), ('c', 1)])], [0, 1, 2])
        with self.assertRaisesRegex(ValueError, 'collision_exceeds'):
            frame_timeline([(str(index), 1) for index in range(4)])

    def test_missing_reversed_or_nonfinite_timestamps_are_rejected(self):
        for frames in ([], [('a', 2), ('b', 1)], [('a', float('nan'))], [('a', float('inf'))]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                frame_timeline(frames)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'native encoding tools required')
class EncodingFixtureTests(unittest.TestCase):
    def test_encoder_keeps_all_high_cadence_frames_and_end_time(self):
        with tempfile.TemporaryDirectory(prefix='hermes-encoding-contract-') as directory:
            root = Path(directory)
            # Authored32px flat-color PPM test inputs; not visual design assets,
            # model output, actual interface frames or a motion-quality claim.
            frames = []
            for index in range(12):
                path = root / f'{index}.ppm'
                path.write_bytes(b'P6\n32 32\n255\n' + bytes((index * 20, 40, 100)) * 32 * 32)
                frames.append((path, 100 + index * .017))
            result = encode_frames(frames, root / 'fixture.mp4', root)
            self.assertEqual(result['frames'], 12)
            self.assertEqual(result['encoded_frames'], 12)
            self.assertAlmostEqual(result['encoded_seconds'], .188, places=3)
            self.assertLess(result['maximum_timestamp_quantization_ms'], .001)
