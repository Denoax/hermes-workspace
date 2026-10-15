#!/usr/bin/python3
"""Protected fixed window operations, invoked only after chosen interruption window."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True

SELF = Path('/usr/local/lib/mani-vmlab-setup/inference_window.py')


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_native_window_helper_only')
    sys.path.insert(0, '/usr/local/lib/mani-vmlab')
    import supervisor
    supervisor.initialize_imports()
    supervisor.protected(SELF)
    supervisor.protected(SELF.parent)
    import window
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('open', 'close', 'status', 'guard', 'restore'))
    operation = parser.parse_args().operation
    if operation == 'guard':
        window.guard()
        return
    if operation == 'restore':
        window.restore()
        return
    if operation in ('open', 'close'):
        window.command(['/usr/bin/systemctl', 'start' if operation == 'open' else 'stop', window.SERVICE], timeout=240)
    print(json.dumps(window.state()))


if __name__ == '__main__':
    main()
