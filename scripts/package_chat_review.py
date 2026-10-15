"""Exact committed public source plus sanitized evidence; verify every ZIP member."""
import argparse,hashlib,json,re,stat,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath

NAME='MANI_HERMES_LOCAL_CHAT_UI_v3_REVIEW'
BINARY={'.png','.webp','.gif','.ico','.wav','.woff2','.ttf','.mp4','.webm'}
DENIED={'client-cookie','catalog.sqlite3','secret.json','.env'}


def checked(name,data):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or any(p in DENIED or p in {'.git','node_modules','private-state','private-originals'} for p in path.parts):raise ValueError('private_or_unsafe_member:'+name)
    if len(data)>64*1024*1024:raise ValueError('member_limit')
    if path.suffix in BINARY:return
    value=data.decode('utf-8')
    for pattern in [r'-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----',r'github_pat_[A-Za-z0-9_]{50,}',r'gh[pousr]_[A-Za-z0-9]{30,}',r'sk-(?:proj-)?[A-Za-z0-9_-]{35,}']:
        if re.search(pattern,value):raise ValueError('credential_pattern:'+name)


def verify(archive,destination):
    with zipfile.ZipFile(archive) as source:
        names=source.namelist()
        if len(names)!=len(set(names)) or source.testzip():raise ValueError('duplicate_or_CRC_failure')
        for item in source.infolist():
            p=PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or stat.S_ISLNK(item.external_attr>>16):raise ValueError('unsafe_member')
        source.extractall(destination)
    root=Path(destination)/NAME;expected={}
    for line in (root/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);data=(root/name).read_bytes();checked(name,data)
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('payload_hash_failure:'+name)
        expected[NAME+'/'+name]=digest
    if set(expected)!=(set(names)-{NAME+'/SHA256SUMS.txt'}):raise ValueError('unchecked_member')
    return root,len(expected)


def package(source,review,output):
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain']):raise ValueError('clean_committed_public_source_required')
    commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip();payload={}
    names=subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().split('\0')
    for name in filter(None,names):
        path=source/name
        if path.is_symlink():raise ValueError('source_symlink')
        payload['source/'+name]=path.read_bytes()
    for path in sorted(review.rglob('*')):
        if path.is_file() and not path.is_symlink():
            relative=path.relative_to(review)
            if 'history' in relative.parts and path.suffix in {'.mp4','.webm'}:continue
            payload['review/'+relative.as_posix()]=path.read_bytes()
    manifest={n.removeprefix('source/'):hashlib.sha256(d).hexdigest() for n,d in payload.items() if n.startswith('source/')}
    payload['implementation.json']=(json.dumps({'commit':commit,'source_files':manifest,'private_backups_included':False},indent=2)+'\n').encode()
    for name,data in payload.items():checked(name,data)
    payload['SHA256SUMS.txt']=''.join(hashlib.sha256(d).hexdigest()+'  '+n+'\n' for n,d in sorted(payload.items())).encode()
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(payload.items()):
            item=zipfile.ZipInfo(NAME+'/'+name);item.external_attr=(stat.S_IFREG | (0o700 if name=='source/labctl' else 0o600))<<16;item.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(item,data)
    output.chmod(0o600)
    with tempfile.TemporaryDirectory(prefix='hermes-review-verify-') as directory:_,count=verify(output,directory)
    return {'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'payloads_verified':count,'commit':commit}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--review',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify',type=Path);p.add_argument('--extract',type=Path);args=p.parse_args()
    if args.verify:
        root,count=verify(args.verify,args.extract);print(json.dumps({'root':str(root),'payloads_verified':count}))
    else:print(json.dumps(package(args.source,args.review,args.output),indent=2))
