"""Single-threaded fixed nft observer with an exact outside-parent lifetime."""
import ctypes
import os
from pathlib import Path
import signal
import sys


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=Path('/usr/local/lib/mani-vmlab/nft_monitor.py') or len(sys.argv)!=2 or not sys.argv[1].isdigit():
        raise SystemExit('fixed_protected_nft_observer_only')
    parent=int(sys.argv[1])
    for path in (Path(__file__).absolute(),Path(__file__).absolute().parent):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or path.is_symlink():raise PermissionError('protected_observer_source_required')
    # This fresh interpreter has no application threads or inherited Python
    # locks. Fence the race where the parent exits before prctl is installed.
    if ctypes.CDLL(None).prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent:raise SystemExit(1)
    os.execve('/usr/bin/nft',['/usr/bin/nft','monitor','ruleset'],{'PATH':'/usr/bin:/bin','LANG':'C'})


if __name__=='__main__':main()
