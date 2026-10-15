"""Import a root-owned public lab receipt, retaining failures and missing cases."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.receipt import trial_rows
from lab.report import write_results
from starter.json_limits import bounded_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path)
    args=parser.parse_args();path=args.receipt
    if path.parent!=Path('/var/lib/mani-vmlab-review') or not re.fullmatch(r'smoke-\d{8}T\d{6}Z.json',path.name):
        raise ValueError('fixed_public_receipt_path_required')
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=0 or parent.st_mode&0o022:
        raise ValueError('protected_public_receipt_directory_required')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or info.st_size>1048576:
            raise ValueError('protected_bounded_native_receipt_required')
        raw=source.read(1048577)
    record=bounded_json(raw,max_bytes=1048576)
    keys=json.loads((ROOT/'bench/answer_keys.json').read_text())['answers']
    pins=json.loads((ROOT/'configs/backend-artifacts.lock.json').read_text())['models']
    rows=trial_rows(record,keys,pins)
    summary={stage:write_results(ROOT/'results'/stage,stage_rows) for stage,stage_rows in rows.items()}
    target=ROOT/'results/continuation'/path.name
    target.write_bytes(raw)
    print(json.dumps({'source_receipt':path.name,'source_pack_sha256':record['source_pack_sha256'],
                      'native_receipt_owner_verified':True,'stages':summary,'failures':record['failures']}))


if __name__=='__main__':main()
