"""Authenticated pinned Ubuntu image acquisition in trusted preparation only."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

FINGERPRINT = 'D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81'
RELEASE = 'release-20260926'
IMAGE = 'ubuntu-24.04-server-cloudimg-amd64.img'
BASE = 'https://cloud-images.ubuntu.com/releases/noble/' + RELEASE + '/'
KEY = 'https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x' + FINGERPRINT


def download(url, path, limit, expected_sha=None):
    if path.exists():
        raise ValueError('refuse_to_overwrite_artifact')
    checksum = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + 1800
    try:
        with urllib.request.urlopen(url, timeout=30) as source, path.open('xb') as output:
            path.chmod(0o600)
            while chunk := source.read(4*1024*1024):
                total += len(chunk)
                if total > limit or time.monotonic() >= deadline:
                    raise ValueError('artifact_download_limit')
                checksum.update(chunk)
                output.write(chunk)
        actual = checksum.hexdigest()
        if expected_sha is not None and actual != expected_sha:
            raise ValueError('artifact_hash_mismatch')
        return {'bytes': total, 'sha256': actual}
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def verify_signature(directory):
    directory = Path(directory)
    with tempfile.TemporaryDirectory(prefix='signer-', dir=directory) as homedir:
        command = ['/usr/bin/gpg', '--homedir', homedir, '--batch', '--no-auto-key-retrieve']
        subprocess.run(command + ['--import', str(directory/'signing-key.asc')], capture_output=True, check=True, timeout=15)
        keys = subprocess.run(command + ['--with-colons', '--fingerprint', FINGERPRINT], capture_output=True, check=True, timeout=15)
        fingerprints = [line.split(':')[9] for line in keys.stdout.decode().splitlines() if line.startswith('fpr:')]
        if not fingerprints or fingerprints[0] != FINGERPRINT:
            raise ValueError('signing_key_fingerprint_mismatch')
        result = subprocess.run(command + ['--status-fd', '1', '--verify', str(directory/'SHA256SUMS.gpg'), str(directory/'SHA256SUMS')],
                                capture_output=True, timeout=15)
        signatures = [line.split() for line in result.stdout.decode().splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
        if result.returncode != 0 or not signatures or not all(FINGERPRINT in (row[2], row[-1]) for row in signatures):
            raise ValueError('checksum_signature_invalid_or_wrong_signer')
        return {'primary_signer_fingerprint': FINGERPRINT, 'signature_valid': True,
                'signed_checksums_sha256': hashlib.sha256((directory/'SHA256SUMS').read_bytes()).hexdigest()}


def checksum_for_image(raw):
    matches = []
    for line in raw.decode('ascii').splitlines():
        found = re.fullmatch(r'([0-9a-f]{64}) [ *](.+)', line)
        if found and found.group(2) == IMAGE:
            matches.append(found.group(1))
    if len(matches) != 1:
        raise ValueError('unique_signed_image_checksum_required')
    return matches[0]


def acquire(directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError('private_preparation_directory_required')
    for filename, url, limit in [('signing-key.asc', KEY, 1024*1024),
                                 ('SHA256SUMS', BASE+'SHA256SUMS', 1024*1024),
                                 ('SHA256SUMS.gpg', BASE+'SHA256SUMS.gpg', 1024*1024)]:
        if not (directory/filename).exists():
            download(url, directory/filename, limit)
    signature = verify_signature(directory)
    expected = checksum_for_image((directory/'SHA256SUMS').read_bytes())
    image = directory/IMAGE
    if image.exists():
        from lab.doctor import digest
        if image.is_symlink() or digest(image) != expected:
            raise ValueError('existing_image_integrity_mismatch')
        artifact = {'sha256': expected, 'bytes': image.stat().st_size}
    else:
        artifact = download(BASE+IMAGE, image, 8*1024**3, expected)
    record = {'family': 'Ubuntu 24.04 noble', 'release': RELEASE, 'url': BASE+IMAGE,
              'filename': IMAGE, **artifact, **signature, 'trusted_preparation': True,
              'VM_booted': False, 'guest_agents_present': False}
    (directory/'image-pin.json').write_text(json.dumps(record, indent=2)+'\n')
    return record
