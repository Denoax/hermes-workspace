"""Protected complete uninstall entry; never exposed to a model or browser."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
sys.dont_write_bytecode=True

SELF=Path('/usr/local/lib/mani-vmlab-setup/workspace_recovery.py')
REGISTER=Path('/var/lib/mani-vmlab-setup/workspace-complete-register.json')


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:raise SystemExit('protected_fixed_recovery_only')
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['plan','remove']);args=parser.parse_args()
    for path in [SELF,SELF.parent,REGISTER,REGISTER.parent]:
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):raise PermissionError('protected_recovery_source_required')
    sys.path.insert(0,str(SELF.parent))
    from recovery import Recovery,NativeServices
    recovery=Recovery(json.loads(REGISTER.read_text()),NativeServices())
    print(json.dumps(recovery.plan() if args.operation=='plan' else recovery.remove()))


if __name__=='__main__':main()
