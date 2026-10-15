"""Owned canary inside one verified private VM network namespace, never host LAN."""
import json
import os
import selectors
import socket
import struct
import sys


def command(operation):
    if operation not in ('positive', 'reset', 'counters'):
        raise ValueError('fixed_canary_operation')
    reports = []
    for address, family in [('127.0.0.1', socket.AF_INET), ('::1', socket.AF_INET6),
                            ('198.18.0.1', socket.AF_INET), ('fd42:4d41:4e49::1', socket.AF_INET6)]:
        with socket.socket(family, socket.SOCK_STREAM) as channel:
            channel.settimeout(1)
            channel.connect((address, 18090))
            channel.sendall(operation.encode())
            channel.shutdown(socket.SHUT_WR)
            raw = channel.recv(1024)
            if operation == 'positive' and raw != b'owned-canary':
                raise RuntimeError('canary_positive_failed')
            reports.append(json.loads(raw) if operation == 'counters' else {'responded': True})
        if operation == 'positive':
            with socket.socket(family, socket.SOCK_DGRAM) as channel:
                channel.settimeout(1)
                query = struct.pack('!6H', 0x4d41, 0x0100, 1, 0, 0, 0) + b'\x06canary\x04test\x00' + struct.pack('!2H', 1, 1)
                channel.sendto(query, (address, 53))
                reply = channel.recv(1024)
                if len(reply) < 12 or struct.unpack('!6H', reply[:12]) != (0x4d41, 0x8183, 1, 0, 0, 0):
                    raise RuntimeError('DNS_canary_positive_failed')
    print(json.dumps({'operation': operation, 'endpoints': reports}))


def serve():
    counts = {'tcp': 0, 'udp': 0}
    sockets = []
    with selectors.DefaultSelector() as selector:
        try:
            for family, bind in [(socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')]:
                for kind, port in [(socket.SOCK_STREAM, 18090), (socket.SOCK_DGRAM, 53)]:
                    channel = socket.socket(family, kind)
                    channel.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    if family == socket.AF_INET6:
                        channel.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                    channel.bind((bind, port))
                    if kind == socket.SOCK_STREAM:
                        channel.listen(4)
                    selector.register(channel, selectors.EVENT_READ, kind)
                    sockets.append(channel)
            print('ready', flush=True)
            while True:
                for key, _ in selector.select():
                    if key.data == socket.SOCK_DGRAM:
                        raw, sender = key.fileobj.recvfrom(2048)
                        counts['udp'] += 1
                        if len(raw) >= 12:
                            key.fileobj.sendto(raw[:2]+struct.pack('!5H', 0x8183, 1, 0, 0, 0)+raw[12:], sender)
                    else:
                        channel, _ = key.fileobj.accept()
                        with channel:
                            channel.settimeout(1)
                            try:
                                raw = channel.recv(64)
                            except OSError:
                                raw = b''
                            if raw == b'reset':
                                counts.update(tcp=0, udp=0)
                                output = b'reset'
                            elif raw == b'counters':
                                output = json.dumps(counts).encode()
                            else:
                                counts['tcp'] += 1
                                output = b'owned-canary'
                            try:
                                channel.sendall(output)
                            except OSError:
                                pass
        finally:
            for channel in sockets:
                channel.close()


if __name__ == '__main__':
    if len(sys.argv) != 2 or os.geteuid() != 0:
        raise SystemExit('fixed_owned_namespace_canary_only')
    serve() if sys.argv[1] == 'serve' else command(sys.argv[1])
