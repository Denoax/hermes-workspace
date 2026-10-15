"""Allowlisted, checksum-complete UI review export, including licensed fonts."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile
from package_review import source_files, SUFFIXES

NAME = 'MANI_HERMES_UI_OVERHAUL_REVIEW'
FONT_NAMES = {'BebasNeue.ttf', 'DMSans.ttf', 'SixCaps.ttf'}
MEDIA = {'live-dark-1915.png','live-dark-1440.png','live-dark-1024.png','live-dark-390.png',
         'live-light-1915.png','live-light-1440.png','live-light-1024.png','live-light-390.png',
         'live-file-1440.png','live-files-390.png','live-details.png','live-native-command.png',
         'fixture-conversation-1440.png','fixture-conversation-390.png','fixture-diff-1440.png','fixture-diff-390.png',
         'live-file-drift-error.png','live-interaction.mp4'}


def verify(archive, destination):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or z.testzip(): raise ValueError('duplicate_or_CRC_error')
        for item in z.infolist():
            n = PurePosixPath(item.filename)
            if n.is_absolute() or '..' in n.parts or stat.S_ISLNK(item.external_attr >> 16): raise ValueError('unsafe_member')
        z.extractall(destination)
        root = Path(destination) / NAME; checked = set()
        for line in (root / 'SHA256SUMS.txt').read_text().splitlines():
            expected, name = line.split('  ', 1); n = PurePosixPath(name)
            if n.is_absolute() or '..' in n.parts or not re.fullmatch('[a-f0-9]{64}', expected): raise ValueError('unsafe_manifest')
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected: raise ValueError('hash_mismatch')
            checked.add(NAME + '/' + name)
        if checked != set(names) - {NAME + '/SHA256SUMS.txt'}: raise ValueError('unchecked_member')
        return root, len(checked)


def package(project, review, output):
    payload = {}; binary = set()
    for path, relative in source_files(project): payload['source/' + relative.as_posix()] = path.read_bytes()
    payload['source/native/run_workspace_setup.sh'] = (project / 'native/run_workspace_setup.sh').read_bytes()
    for path in sorted((project / 'workspace').rglob('*')):
        if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts: continue
        relative = path.relative_to(project)
        if 'evidence' in relative.parts: continue
        name = 'source/' + relative.as_posix()
        if path.suffix in {'.py','.js','.html','.css','.md','.txt','.json'}: payload[name] = path.read_bytes()
        elif path.parent.name == 'fonts' and path.name in FONT_NAMES:
            payload[name] = path.read_bytes(); binary.add(name)
    for path in sorted((project / 'workspace/evidence/overhaul').iterdir()):
        if path.suffix == '.json' or path.name in MEDIA:
            name = 'evidence/' + path.name; payload[name] = path.read_bytes()
            if path.name in MEDIA: binary.add(name)
    for path in sorted((project / 'results').rglob('*')):
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES: payload['results/' + path.relative_to(project / 'results').as_posix()] = path.read_bytes()
    for path in sorted(review.rglob('*')):
        if not path.is_file() or path.is_symlink(): continue
        name = path.relative_to(review).as_posix()
        if path.suffix in {'.md','.txt','.json','.csv','.py','.js','.html','.css','.patch'}: payload[name] = path.read_bytes()
        elif name == 'evidence/before-user-supplied.png': payload[name] = path.read_bytes(); binary.add(name)
    for name, data in payload.items():
        if len(data) > 8 * 1024 ** 2: raise ValueError('member_size_limit')
        if name in binary:
            if name.endswith('.png') and not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('PNG_required')
            if name.endswith('.mp4') and data[4:8] != b'ftyp': raise ValueError('MP4_required')
            if name.endswith('.ttf') and data[:4] != b'\x00\x01\x00\x00': raise ValueError('TTF_required')
        else:
            text = data.decode('utf-8')
            if re.search(r'(?m)^-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----', text): raise ValueError('private_key_detected')
    source_hashes = {name.removeprefix('source/'): hashlib.sha256(data).hexdigest() for name,data in sorted(payload.items()) if name.startswith('source/')}
    payload['SOURCE_TREE.json'] = json.dumps({'files': source_hashes,'sha256':hashlib.sha256(json.dumps(source_hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()},indent=2).encode()
    payload['SHA256SUMS.txt'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in sorted(payload.items())).encode()
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(payload.items()):
            item = zipfile.ZipInfo(NAME + '/' + name); item.external_attr = (stat.S_IFREG | 0o600) << 16
            item.compress_type = zipfile.ZIP_DEFLATED; z.writestr(item, data)
    output.chmod(0o600)
    return {'path':str(output), 'bytes':output.stat().st_size, 'sha256':hashlib.sha256(output.read_bytes()).hexdigest(), 'payloads':len(payload)-1}


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('review',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();print(json.dumps(package(args.project,args.review,args.output),indent=2))
