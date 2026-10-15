#!/usr/bin/env python3
"""Verify a package directory or ZIP, without extracting or executing payloads."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

MAX_MEMBERS = 500
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024

def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Invalid payload name')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != name:
        raise ValueError('Unsafe or noncanonical payload path')
    return name

def validate_manifest(data):
    if data.get('schema_version') != 1 or not isinstance(data.get('files'), list):
        raise ValueError('Unsupported manifest')
    entries = {}
    for item in data['files']:
        name = safe_name(item['path'])
        if name == 'manifest.json' or name in entries:
            raise ValueError('Duplicate or self-referencing manifest entry')
        digest = item['sha256']
        size = item['size_bytes']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid SHA-256 entry')
        if type(size) is not int or not 0 <= size <= MAX_FILE:
            raise ValueError('Invalid payload size')
        entries[name] = item
    if not entries or len(entries) > MAX_MEMBERS or sum(x['size_bytes'] for x in entries.values()) > MAX_TOTAL:
        raise ValueError('Manifest exceeds limits')
    return entries

def verify_bytes(name, content, item):
    if len(content) != item['size_bytes']:
        raise ValueError(f'Size mismatch: {name}')
    if hashlib.sha256(content).hexdigest() != item['sha256']:
        raise ValueError(f'Hash mismatch: {name}')

def verify_directory(root):
    if root.is_symlink():
        raise ValueError('Package root must not be a symlink')
    paths = list(root.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('Symlink in package')
    files = {p.relative_to(root).as_posix(): p for p in paths if p.is_file()}
    if 'manifest.json' not in files or len(files) > MAX_MEMBERS:
        raise ValueError('Missing manifest or too many files')
    if any(p.stat().st_size > MAX_FILE for p in files.values()):
        raise ValueError('File exceeds limit')
    if sum(p.stat().st_size for p in files.values()) > MAX_TOTAL:
        raise ValueError('Package exceeds limit')
    entries = validate_manifest(json.loads(files['manifest.json'].read_text(encoding='utf-8')))
    if set(files) != set(entries) | {'manifest.json'}:
        raise ValueError('Unlisted or missing payload files')
    for name, item in entries.items():
        verify_bytes(name, files[name].read_bytes(), item)
    return len(entries)

def verify_zip(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS or len({i.filename for i in infos}) != len(infos):
            raise ValueError('Excessive or duplicate ZIP members')
        if sum(i.file_size for i in infos) > MAX_TOTAL:
            raise ValueError('ZIP exceeds expanded size limit')
        names = []
        for item in infos:
            safe_name(item.filename[:-1] if item.is_dir() else item.filename)
            if stat.S_ISLNK(item.external_attr >> 16) or item.file_size > MAX_FILE:
                raise ValueError('Symlink or oversized ZIP member')
            if not item.is_dir():
                names.append(item.filename)
        manifests = [n for n in names if PurePosixPath(n).name == 'manifest.json']
        if len(manifests) != 1:
            raise ValueError('ZIP must contain exactly one manifest')
        manifest = manifests[0]
        prefix = manifest[:-len('manifest.json')]
        if not prefix or any(not n.startswith(prefix) for n in names):
            raise ValueError('ZIP must have one package root')
        entries = validate_manifest(json.loads(archive.read(manifest)))
        if set(names) != {prefix+n for n in entries} | {manifest}:
            raise ValueError('Unlisted or missing ZIP payload')
        for name, item in entries.items():
            verify_bytes(name, archive.read(prefix+name), item)
        return len(entries)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path, help='Extracted package directory or original ZIP')
    args = parser.parse_args(argv)
    try:
        count = verify_directory(args.path) if args.path.is_dir() else verify_zip(args.path)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print(f'PASS: {count} payload files verified. Integrity only; no VM or model verification performed.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
