"""Boundary fixture: detaching an owned observer must preserve its document."""
import signal
import unittest
from unittest.mock import Mock, patch, call

from scripts.production_pin import ProductionPin


class PinPreservation(unittest.TestCase):
    def pin(self):
        pin = ProductionPin.__new__(ProductionPin)
        pin.pipe = Mock(read=12, write=13)
        pin.session = 'owned-observer'
        pin.owner = 14
        pin.paused = True
        pin.process = Mock()
        return pin

    @patch('scripts.production_pin.signal.pidfd_send_signal')
    @patch('scripts.production_pin.os.close')
    def test_detach_resumes_launcher_without_closing_browser(self, close, send):
        pin = self.pin()
        pipe = pin.pipe
        pin.detach_preserving_document()
        pipe.call.assert_called_once_with('Target.detachFromTarget', {'sessionId': 'owned-observer'})
        send.assert_called_once_with(14, signal.SIGCONT)
        self.assertEqual(close.call_args_list, [call(12), call(13), call(14)])
        pin.close()
        pin.process.wait.assert_not_called()
        pin.process.terminate.assert_not_called()
        self.assertIsNone(pin.pipe)
        self.assertIsNone(pin.owner)

    @patch('scripts.production_pin.time.sleep')
    def test_reload_waits_for_new_document_and_hydrated_input(self, sleep):
        pin = self.pin()
        pin.call = Mock()
        pin.evaluate = Mock(side_effect=[1000, False, False, True])
        pin.reload_ready()
        pin.call.assert_called_once_with('Page.reload')
        self.assertEqual(sleep.call_count, 2)
        self.assertIn('performance.timeOrigin!==1000', pin.evaluate.call_args.args[0])
        self.assertIn('!document.querySelector("#prompt").disabled', pin.evaluate.call_args.args[0])

    @patch('scripts.production_pin.time.sleep')
    def test_reload_tolerates_only_transient_protocol_context_failure(self, sleep):
        pin = self.pin()
        pin.call = Mock()
        pin.evaluate = Mock(side_effect=[1000, RuntimeError('browser_protocol_error'), True])
        pin.reload_ready()
        self.assertEqual(sleep.call_count, 1)
        pin.evaluate = Mock(side_effect=[2000, RuntimeError('app_failure')])
        with self.assertRaisesRegex(RuntimeError, 'app_failure'):
            pin.reload_ready()

    @patch('scripts.production_pin.signal.pidfd_send_signal')
    @patch('scripts.production_pin.os.close')
    def test_failed_observer_detach_still_releases_and_preserves_document(self, close, send):
        pin = self.pin()
        pin.pipe.call.side_effect = OSError('observer unavailable')
        with self.assertRaises(OSError):
            pin.detach_preserving_document()
        send.assert_called_once_with(14, signal.SIGCONT)
        self.assertEqual(close.call_count, 3)
        pin.close()
        pin.process.terminate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
