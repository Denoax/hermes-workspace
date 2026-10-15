"""One allowlisted workspace review ZIP; only inspected UI media is binary."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import stat
import tempfile
import zipfile
from package_review import source_files,SUFFIXES

ARCHIVE_ROOT='MANI_HERMES_WORKSPACE_REVIEW'
MEDIA={'authenticated-idle-desktop.png','editable-copy-desktop.png','explicit-window-command.png',
       'workspace-tablet.png','workspace-mobile.png','workspace-320.png','mobile-file-review.png',
       'workspace-interaction.mp4','actual-live-stop-before.png','actual-live-stop-after.png',
       'actual-live-diff.png','native-applications-tile.png'}
WORKSPACE_TYPES={'.py','.md','.html','.css','.js','.json'}


def verify(path):
    with zipfile.ZipFile(path) as archive,tempfile.TemporaryDirectory(prefix='workspace-review-audit-') as directory:
        names=archive.namelist()
        if len(names)!=len(set(names)) or archive.testzip() is not None:raise ValueError('archive_duplicate_or_CRC_failure')
        for item in archive.infolist():
            name=PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or stat.S_ISLNK(item.external_attr>>16):raise ValueError('unsafe_archive_member')
        archive.extractall(directory);root=Path(directory)/ARCHIVE_ROOT;checked=set()
        for line in (root/'SHA256SUMS.txt').read_text().splitlines():
            digest,name=line.split('  ',1);p=PurePosixPath(name)
            if not re.fullmatch('[0-9a-f]{64}',digest) or p.is_absolute() or '..' in p.parts:raise ValueError('unsafe_checksum_record')
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('payload_hash_mismatch')
            checked.add(ARCHIVE_ROOT+'/'+name)
        if checked!=set(names)-{ARCHIVE_ROOT+'/SHA256SUMS.txt'}:raise ValueError('unchecked_payload')
        return len(checked)


def package(project,docs,output):
    payload={};binary=set()
    for path,relative in source_files(project):payload['source/'+relative.as_posix()]=path.read_bytes()
    wrapper=project/'native/run_workspace_setup.sh'
    if wrapper.is_file() and not wrapper.is_symlink():payload['source/native/run_workspace_setup.sh']=wrapper.read_bytes()
    for path in sorted((project/'workspace').rglob('*')):
        if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:continue
        relative=path.relative_to(project).as_posix()
        if path.suffix in WORKSPACE_TYPES:payload['source/'+relative]=path.read_bytes()
        elif path.parent==project/'workspace/evidence' and path.name in MEDIA:
            name='evidence/'+path.name;payload[name]=path.read_bytes();binary.add(name)
    for path in sorted((project/'results').rglob('*')):
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES:payload['results/'+path.relative_to(project/'results').as_posix()]=path.read_bytes()
    for path in sorted(docs.iterdir()):
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES:payload[path.name]=path.read_bytes()
    for name,data in payload.items():
        if len(data)>8*1024**2:raise ValueError('bounded_review_member_required')
        if name in binary:
            if name.endswith('.png') and not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('trusted_PNG_signature_required')
            if name.endswith('.mp4') and data[4:8]!=b'ftyp':raise ValueError('trusted_MP4_signature_required')
            continue
        text=data.decode('utf-8')
        if re.search(r'(?m)^-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----',text):raise ValueError('private_key_in_review')
    payload['SHA256SUMS.txt']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(payload.items())).encode()
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(payload.items()):
            entry=zipfile.ZipInfo(ARCHIVE_ROOT+'/'+name);entry.external_attr=(stat.S_IFREG|0o600)<<16;entry.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(entry,data)
    output.chmod(0o600);count=verify(output)
    return {'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,
        'CRC_and_clean_extraction':True,'payloads_verified':count,'semantic_and_media_review_required':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('project',type=Path);parser.add_argument('docs',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    print(json.dumps(package(args.project,args.docs,args.output),indent=2))


if __name__=='__main__':main()
