"""Committed public source and explicitly selected review evidence; no Git writes."""
import argparse
import hashlib
import json
import re
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

NAME = 'MANI_HERMES_V5_COMPLETE_REVIEW'
MAX_MEMBER = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_MEMBERS = 5000
DENIED_PARTS = {'.git', '.codex', '.hermes', '.aws', '.ssh', '.gnupg', '.venv', 'node_modules', '__pycache__',
                'private-state', 'private-originals', 'browser-profile', 'profiles', 'backups',
                'package-cache', 'model-cache', 'uploads', 'attachments', 'sessions', 'vm-disks',
                'runtime', 'runs', 'models', 'userdata', 'user-data', 'browser-profiles', 'profile', 'cache'}
DENIED_SUFFIXES = {'.sqlite', '.sqlite3', '.db', '.gguf', '.safetensors', '.bin', '.pt', '.pth', '.onnx', '.qcow2', '.raw', '.img', '.iso',
                   '.vmdk', '.vdi', '.pem', '.key', '.p12', '.pfx', '.zip'}
DENIED_NAMES = {'.env', 'client-cookie', 'secret.json', 'catalog.sqlite3', 'cookies', 'cookies.json', 'credentials.json'}
BINARY = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.wav', '.woff', '.woff2', '.ttf', '.otf', '.mp4', '.webm'}
STATUSES = ('PASS', 'PARTIAL', 'BLOCKED', 'UNVERIFIED')
STATUS_MAP = {'TODO': 'UNVERIFIED', 'IN_PROGRESS': 'PARTIAL', 'VERIFY': 'PARTIAL', 'BLOCKED': 'BLOCKED', 'DONE': 'PASS'}
LEDGER_FILES = ('requirements.json', 'state.json', 'PLAN.md', 'RESUME.md')


def encoded(value):return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
def digest(value):return hashlib.sha256(value).hexdigest()


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or any(ord(c) < 32 for c in name):
        raise ValueError('canonical_relative_member_required')
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or '..' in path.parts or path.as_posix() != name:
        raise ValueError('canonical_relative_member_required')
    if (any(part.lower() in DENIED_PARTS or part.lower() in DENIED_NAMES or part.lower().startswith('.env.') for part in path.parts)
            or path.suffix.lower() in DENIED_SUFFIXES):
        raise ValueError('private_or_runtime_member:' + name)
    return name


def checked(name, data):
    safe_name(name)
    if len(data) > MAX_MEMBER:raise ValueError('review_member_limit')
    if name.startswith('review/') and PurePosixPath(name).suffix.lower() == '.jsonl':
        raise ValueError('raw_CLI_event_stream_not_exportable')
    # Reuse the existing credential patterns; source literals describing their
    # syntax do not match actual token payloads. This is not semantic approval.
    patterns = (rb'-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----', rb'github_pat_[A-Za-z0-9_]{50,}',
                rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'sk-(?:proj-)?[A-Za-z0-9_-]{35,}')
    if any(re.search(pattern, data) for pattern in patterns):raise ValueError('credential_pattern:' + name)
    if PurePosixPath(name).suffix.lower() not in BINARY:data.decode('utf-8')


def read_scoped(root, name):
    safe_name(name)
    target = root / name
    for part in (target, *target.parents):
        if part == root:break
        if part.is_symlink():raise ValueError('symlink_member:' + name)
    if not target.is_file() or target.resolve().is_relative_to(root.resolve()) is False:
        raise ValueError('scoped_regular_file_required:' + name)
    data = target.read_bytes()
    checked(name, data)
    return data


def git(root, *args):return subprocess.check_output(['git', '-C', str(root), *args])


def committed_source(root):
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('clean_committed_public_source_required')
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    tree = git(root, 'rev-parse', commit + '^{tree}').decode().strip()
    payload, modes = {}, {}
    for raw in git(root, 'ls-tree', '-r', '-z', commit).split(b'\0'):
        if not raw:continue
        metadata, name = raw.split(b'\t', 1)
        mode, kind, object_id = metadata.decode().split()
        name = name.decode()
        if kind != 'blob' or mode not in ('100644', '100755'):raise ValueError('regular_committed_source_required')
        data = git(root, 'cat-file', 'blob', object_id)
        checked(name, data)
        payload[name], modes[name] = data, mode
    if git(root, 'status', '--porcelain', '--untracked-files=all') or git(root, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('public_source_changed_during_snapshot')
    return {'commit': commit, 'tree': tree, 'files': payload, 'modes': modes}


def mutable_loop(name):
    return name in {'.agent/hermes-loop/state.json', '.agent/hermes-loop/PLAN.md', '.agent/hermes-loop/RESUME.md'} or name.startswith('.agent/hermes-loop/evidence/')


def publication(record, source):
    status = record.get('status')
    if status not in ('PUBLISHED', 'PENDING'):raise ValueError('explicit_publication_final_state_required')
    if record.get('commit') != source['commit'] or record.get('tree') != source['tree']:
        raise ValueError('publication_receipt_is_for_another_source')
    if status == 'PUBLISHED':
        if record.get('reason'):raise ValueError('published_receipt_cannot_carry_pending_reason')
        if (record.get('remote_commit') != source['commit'] or record.get('remote_tree') != source['tree']
                or not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', record.get('repository_url', ''))
                or not record.get('branch') or not record.get('verification_artifact')):
            raise ValueError('exact_remote_commit_tree_verification_required')
    elif not record.get('reason'):raise ValueError('pending_publication_needs_reason')
    fields = ('status', 'commit', 'tree', 'remote_commit', 'remote_tree', 'repository_url', 'branch', 'verification_artifact', 'reason')
    return {name: record[name] for name in fields if name in record}


def validate_acceptance(acceptance, source, payload):
    rows = acceptance['rows']
    counts = {status: sum(row['status'] == status for row in rows) for status in STATUSES}
    required = json.loads(payload['review/loop/requirements.json'])
    state = json.loads(payload['review/loop/state.json'])
    if (len(rows) != 36 or len({row['id'] for row in rows}) != 36 or sum(counts.values()) != 36
            or [row['id'] for row in rows] != [task['id'] for task in required['tasks']]
            or set(state['tasks']) != {row['id'] for row in rows}
            or state['requirements_sha256'] != digest(payload['review/loop/requirements.json'])):
        raise ValueError('canonical_exact_ledger_inventory_required')
    for row in rows:
        item = state['tasks'][row['id']]
        expected = item.get('acceptance_status', STATUS_MAP[item['status']])
        if expected not in STATUSES or expected == 'PASS' and item['status'] != 'DONE':
            raise ValueError('only_ledger_DONE_can_produce_PASS')
        if row['status'] != expected or row['ledger_status'] != item['status'] or row['evidence_ids'] != item.get('evidence', []):
            raise ValueError('canonical_row_differs_from_ledger')
    receipt_bytes = payload['review/publication.json']
    receipt = publication(json.loads(receipt_bytes), source)
    expected_publication = {**receipt, 'archive_path': 'review/publication.json', 'sha256': digest(receipt_bytes)}
    if receipt.get('verification_artifact'):
        path = 'review/' + safe_name(receipt['verification_artifact'])
        expected_publication.update(verification_archive_path=path, verification_sha256=digest(payload[path]))
    expected_summary = {'counts': counts, 'overall': 'PASS' if counts['PASS'] == 36 else 'PARTIAL',
                        'unfinished_ids': [row['id'] for row in rows if row['status'] != 'PASS'],
                        'publication_status': receipt['status']}
    manifest = {name: digest(data) for name, data in source['files'].items()}
    if (acceptance['summary'] != expected_summary or acceptance['source'] != {
            'commit': source['commit'], 'tree': source['tree'], 'files': manifest}
            or acceptance['publication'] != expected_publication):
        raise ValueError('canonical_source_publication_or_summary_mismatch')
    if set(acceptance['ledger_inputs']) != set(LEDGER_FILES):raise ValueError('complete_loop_snapshot_required')
    for name, record in acceptance['ledger_inputs'].items():
        if record['archive_path'] != 'review/loop/' + name or digest(payload[record['archive_path']]) != record['sha256']:
            raise ValueError('canonical_ledger_snapshot_changed')
    for evidence in acceptance['evidence'].values():
        name = evidence['archive_path']
        if name is None and evidence['actual_sha256'] is None:continue
        if name not in payload or digest(payload[name]) != evidence['actual_sha256']:
            raise ValueError('canonical_evidence_not_in_archive')


def export_source(live, public, selection, destination):
    baseline = committed_source(public)
    if set(selection) != {'add', 'remove'} or any(not isinstance(selection[key], list) for key in selection):
        raise ValueError('explicit_source_add_remove_selection_required')
    if any(len(values) != len(set(values)) for values in selection.values()):raise ValueError('unique_source_selection_required')
    added, removed = set(selection['add']), set(selection['remove'])
    if added & removed or added & set(baseline['files']) or not removed.issubset(baseline['files']):
        raise ValueError('unambiguous_source_selection_required')
    for name in added | removed:safe_name(name)
    if any(mutable_loop(name) for name in added):raise ValueError('mutable_loop_belongs_in_review')
    excluded = {name for name in baseline['files'] if mutable_loop(name)}
    names = (set(baseline['files']) | added) - removed - excluded
    payload = {name: read_scoped(live, name) for name in sorted(names)}
    manifest = {name: digest(data) for name, data in payload.items()}
    changes = []
    for name in sorted(set(baseline['files']) | set(payload)):
        old, new = baseline['files'].get(name), payload.get(name)
        if old != new:
            changes.append({'path': name, 'change': 'added' if old is None else 'deleted' if new is None else 'modified',
                            'before_sha256': digest(old) if old is not None else None,
                            'after_sha256': digest(new) if new is not None else None})
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, data in payload.items():
        target = destination / 'source' / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o700 if baseline['modes'].get(name) == '100755' else 0o600)
    record = {'baseline_commit': baseline['commit'], 'baseline_tree': baseline['tree'], 'source_files': manifest,
              'excluded_mutable_loop_paths': sorted(excluded), 'private_state_exported': False,
              'scope': 'Explicit reviewed projection of live files; not a commit or publication claim'}
    (destination / 'source-export.json').write_bytes(encoded(record))
    (destination / 'diff-manifest.json').write_bytes(encoded({'changes': changes}))
    return record


def verify(archive, destination):
    # Validate names, types, sizes, payload hashes and sanitization before any
    # extraction. A fresh destination prevents preexisting symlink traversal.
    with zipfile.ZipFile(archive) as source:
        items = source.infolist()
        names = [item.filename for item in items]
        if len(items) > MAX_MEMBERS or len(names) != len(set(names)):raise ValueError('bounded_unique_members_required')
        if sum(item.file_size for item in items) > MAX_TOTAL:raise ValueError('review_total_limit')
        payload, modes = {}, {}
        for item in items:
            if not item.filename.startswith(NAME + '/') or item.is_dir() or item.flag_bits & 1:
                raise ValueError('fixed_regular_archive_root_required')
            name = item.filename.removeprefix(NAME + '/')
            safe_name(name)
            mode = item.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or item.file_size > MAX_MEMBER:
                raise ValueError('bounded_regular_archive_member_required')
            data = source.read(item)
            checked(name, data)
            payload[name], modes[name] = data, mode
    if 'SHA256SUMS.txt' not in payload:raise ValueError('checksum_inventory_required')
    checksums = payload.pop('SHA256SUMS.txt').decode('utf-8').splitlines()
    expected = {}
    for line in checksums:
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if match is None:raise ValueError('invalid_checksum_record')
        wanted, name = match.groups()
        safe_name(name)
        if name in expected:raise ValueError('duplicate_checksum_record')
        expected[name] = wanted
    if list(expected) != sorted(expected) or set(expected) != set(payload):raise ValueError('exact_sorted_checksum_inventory_required')
    if any(digest(data) != expected[name] for name, data in payload.items()):raise ValueError('payload_hash_failure')
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = destination / NAME
    for name, data in {**payload, 'SHA256SUMS.txt': ('\n'.join(checksums) + '\n').encode()}.items():
        target = root / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open('xb') as stream:stream.write(data)
        target.chmod(0o700 if modes[name] & 0o111 else 0o600)
    return root, len(payload)


def package(public, review, review_files, output):
    source = committed_source(public)
    if not isinstance(review_files, list) or len(review_files) != len(set(review_files)):
        raise ValueError('explicit_unique_review_inventory_required')
    required = {'acceptance.json', 'rollback.md', 'source-export.json', 'diff-manifest.json', 'publication.json', 'source-export-recipe.md'}
    if not required.issubset(review_files):raise ValueError('required_final_review_documents_missing')
    payload = {'source/' + name: data for name, data in source['files'].items()}
    for name in sorted(review_files):
        if PurePosixPath(name).suffix.lower() == '.jsonl':raise ValueError('raw_CLI_event_stream_not_exportable')
        payload['review/' + name] = read_scoped(review, name)
    manifest = {name: digest(data) for name, data in source['files'].items()}
    export = json.loads(payload['review/source-export.json'])
    if export['source_files'] != manifest:raise ValueError('committed_source_differs_from_reviewed_export')
    acceptance = json.loads(payload['review/acceptance.json'])
    validate_acceptance(acceptance, source, payload)
    payload['implementation.json'] = encoded({'commit': source['commit'], 'tree': source['tree'], 'source_files': manifest,
                                             'private_backups_included': False, 'canonical_acceptance': 'review/acceptance.json'})
    for name, data in payload.items():checked(name, data)
    if len(payload) >= MAX_MEMBERS or sum(map(len, payload.values())) > MAX_TOTAL:raise ValueError('review_total_limit')
    payload['SHA256SUMS.txt'] = ''.join(digest(data) + '  ' + name + '\n' for name, data in sorted(payload.items())).encode()
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            item = zipfile.ZipInfo(NAME + '/' + name)
            executable = name.startswith('source/') and source['modes'][name.removeprefix('source/')] == '100755'
            item.external_attr = (stat.S_IFREG | (0o700 if executable else 0o600)) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    output.chmod(0o600)
    with tempfile.TemporaryDirectory(prefix='hermes-v5-verify-') as directory:
        _root, count = verify(output, Path(directory) / 'clean')
    return {'bytes': output.stat().st_size, 'sha256': digest(output.read_bytes()),
            'payloads_verified': count, 'commit': source['commit'], 'tree': source['tree']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    for name in ('live', 'public', 'selection', 'destination'):export.add_argument('--' + name, type=Path, required=True)
    bundle = commands.add_parser('package')
    for name in ('public', 'review', 'review-files', 'output'):bundle.add_argument('--' + name, type=Path, required=True)
    audit = commands.add_parser('verify')
    audit.add_argument('archive', type=Path); audit.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'export':
        result = export_source(args.live, args.public, json.loads(args.selection.read_text()), args.destination)
    elif args.command == 'package':
        result = package(args.public, args.review, json.loads(args.review_files.read_text()), args.output)
    else:
        root, count = verify(args.archive, args.destination)
        result = {'root': str(root), 'payloads_verified': count}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':main()
