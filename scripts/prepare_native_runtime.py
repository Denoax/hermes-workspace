"""Rebuild the allowlisted native source pack without installing or executing it."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native.install_runtime import EXPECTED_FILES


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    native={'backend.py','canary.py','proxy.py','supervisor.py','vm_service.py','window.py','evidence.py','jobs.py','nft_monitor.py','text_chat.py'}
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(EXPECTED_FILES):
            source=ROOT/'native'/name if name in native else ROOT/name
            if name=='guest/json_limits.py':source=ROOT/'starter/json_limits.py'
            if name=='guest/workspace_contract.py':source=ROOT/'lab/workspace_contract.py'
            if name=='guest/recovery.py':source=ROOT/'native/recovery.py'
            # Retain the measured pack's frozen metadata for byte reproduction.
            entry=zipfile.ZipInfo(name,(2026,10,12,22,41,6))
            entry.external_attr=0o600<<16;entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,source.read_bytes())
    args.output.chmod(0o600)
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__=='__main__':main()
