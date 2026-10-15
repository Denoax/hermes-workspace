"""Reproduce pinned compiler data from verified cached/downloaded Ubuntu DEBs."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('cache',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    lock=json.loads((ROOT/'configs/compiler-artifacts.lock.json').read_text())
    args.cache.mkdir(mode=0o700,parents=True,exist_ok=True)
    data={}
    for item in lock['packages']:
        name=item['file'];path=args.cache/name
        if '/' in name or not item['url'].startswith('https://archive.ubuntu.com/ubuntu/pool/'):
            raise ValueError('pinned_official_package_required')
        raw=path.read_bytes() if path.exists() else urllib.request.urlopen(item['url'],timeout=60).read()
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('package_digest_changed')
        if not path.exists():path.write_bytes(raw);path.chmod(0o600)
        data[name]=raw
    manifest={key:value for key,value in lock.items() if key not in ('zip_entries','embedded_manifest_sha256','compiler_zip_sha256','installation')}
    raw=(json.dumps(manifest,indent=2)+'\n').encode()
    if hashlib.sha256(raw).hexdigest()!=lock['embedded_manifest_sha256']:raise ValueError('embedded_manifest_reproduction_failed')
    data['manifest.json']=raw
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for item in lock['zip_entries']:
            info=zipfile.ZipInfo(item['name'],tuple(item['date_time']));info.external_attr=item['external_attr'];info.create_system=item['create_system'];info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data[item['name']],compresslevel=1)
    args.output.chmod(0o600)
    actual=hashlib.sha256(args.output.read_bytes()).hexdigest()
    if actual!=lock['compiler_zip_sha256']:raise ValueError('compiler_ZIP_reproduction_failed')
    print(actual)


if __name__=='__main__':main()
