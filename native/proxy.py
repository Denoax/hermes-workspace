"""Fixed SSH Unix-socket proxy. Input path is built only by the trusted broker."""
import os
import re
import selectors
import socket
import sys

PATH = re.compile(r'/home/mani-vmlab-data/runs/[0-9a-f]{32}/(?:controller|worker_a|worker_b)-control/ssh\.sock\Z')


def main():
    if len(sys.argv) != 2 or not PATH.fullmatch(sys.argv[1]) or os.geteuid() != 0:
        raise SystemExit('fixed_native_proxy_only')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(sys.argv[1])
        connection.settimeout(None)
        with selectors.DefaultSelector() as selector:
            selector.register(sys.stdin.buffer, selectors.EVENT_READ, 'input')
            selector.register(connection, selectors.EVENT_READ, 'socket')
            while selector.get_map():
                for key, _ in selector.select():
                    if key.data == 'input':
                        chunk = os.read(sys.stdin.fileno(), 16384)
                        if chunk:
                            connection.sendall(chunk)
                        else:
                            # SSH owns this pipe for the transport lifetime. EOF
                            # means its owner exited; close the guest socket too.
                            return
                    else:
                        chunk = connection.recv(16384)
                        if not chunk:
                            return
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
