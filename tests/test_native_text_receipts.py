"""Real local SCM_RIGHTS fixtures; never connect to the native lab service."""
import array
import errno
import json
import os
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from lab.native_client import NativeClient


class RootPeerFixture:
    """Labelled peer-identity fixture; data and descriptor I/O stay real."""
    def __init__(self, channel):
        self.channel = channel
        self.received = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.channel.close()

    def __getattr__(self, name):
        return getattr(self.channel, name)

    def connect(self, _path):
        pass  # socketpair is already connected to the fixture.

    def getsockopt(self, level, option, length=None):
        if (level, option) == (socket.SOL_SOCKET, socket.SO_PEERCRED):
            return struct.pack('3i', 1, 0, 0)
        return self.channel.getsockopt(level, option, length)

    def recvmsg(self, *args):
        result = self.channel.recvmsg(*args)
        for level, kind, rights in result[1]:
            if (level, kind) == (socket.SOL_SOCKET, socket.SCM_RIGHTS):
                received = array.array('i')
                received.frombytes(rights)
                self.received.extend(received)
        return result


class NativeTextReceipts(unittest.TestCase):
    def exchange(self, raw, descriptors=()):
        client_side, server_side = socket.socketpair()
        peer = RootPeerFixture(client_side)
        self.addCleanup(server_side.close)
        errors = []
        requests = []
        def respond():
            try:
                request = bytearray()
                while chunk := server_side.recv(8192):
                    request.extend(chunk)
                requests.append(json.loads(request))
                if descriptors:
                    server_side.sendmsg([raw], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', descriptors))])
                elif raw:
                    server_side.sendall(raw)
                server_side.shutdown(socket.SHUT_WR)
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=respond)
        worker.start()
        real_socket = socket.socket
        def make_socket(*args, **kwargs):
            return real_socket(*args, **kwargs) if 'fileno' in kwargs else peer
        try:
            with patch.object(NativeClient, 'available', return_value=True), patch('lab.native_client.socket.socket', side_effect=make_socket):
                result = NativeClient(timeout=2).text_connection('a' * 32, 'normal')
            return result, peer
        except BaseException:
            self.assert_closed(peer.received)
            raise
        finally:
            worker.join(3)
            self.assertFalse(worker.is_alive(), 'fixture exchange did not terminate')
            self.assertEqual(errors, [])
            self.assertEqual(requests, [{'operation': 'chat_admit', 'job_id': 'a' * 32, 'arm': 'normal'}])

    def assert_closed(self, descriptors):
        for descriptor in descriptors:
            with self.assertRaises(OSError) as failure:
                os.fstat(descriptor)
            self.assertEqual(failure.exception.errno, errno.EBADF)

    def pair(self):
        first, second = socket.socketpair()
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        return first, second

    def test_empty_reply_has_actionable_error_without_json_parser_details(self):
        with self.assertRaisesRegex(RuntimeError, 'closed without a receipt.*retry this turn') as failure:
            self.exchange(b'')
        self.assertNotIn('Expecting value', str(failure.exception))

    def test_malformed_or_nonobject_reply_is_sanitized_and_closes_received_descriptor(self):
        transfer, _ = self.pair()
        for raw in (b'PRIVATE-CONTROL-DATA', b'\xffPRIVATE', b'[]', b'{"status":"PRIVATE"}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(RuntimeError, 'invalid receipt.*retry this turn') as failure:
                self.exchange(raw, [transfer.fileno()])
            self.assertNotIn('PRIVATE', str(failure.exception))

    def test_extra_descriptors_are_rejected_and_all_received_copies_closed(self):
        first, _ = self.pair()
        second, _ = self.pair()
        with self.assertRaisesRegex(RuntimeError, 'native_text_admission_denied'):
            self.exchange(b'{"status":"ok"}', [first.fileno(), second.fileno()])
        # Sending SCM_RIGHTS transfers copies; fixture originals stay owned here.
        self.assertGreaterEqual(os.fstat(first.fileno()).st_ino, 0)
        self.assertGreaterEqual(os.fstat(second.fileno()).st_ino, 0)

    def test_non_socket_descriptor_is_closed_when_socket_construction_fails(self):
        with tempfile.TemporaryFile() as regular:
            with self.assertRaises(OSError):
                self.exchange(b'{"status":"ok"}', [regular.fileno()])

    def test_valid_single_socket_is_usable_and_close_on_exec(self):
        transfer, remote = self.pair()
        (receipt, connection), peer = self.exchange(b'{"status":"ok"}', [transfer.fileno()])
        try:
            self.assertEqual(receipt, {'status': 'ok'})
            self.assertEqual(len(peer.received), 1)
            self.assertFalse(os.get_inheritable(connection.fileno()))
            remote.sendall(b'labelled fixture')
            self.assertEqual(connection.recv(64), b'labelled fixture')
        finally:
            connection.close()
        self.assert_closed(peer.received)


if __name__ == '__main__':
    unittest.main()
