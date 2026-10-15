"""Package inspected pinned runtime sources and locked wheels, without imports."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT.parent/'private-artifacts/guest-hermes'
REVISION = '63279301bcbdc185c1b07b98a9312eb0c862f26d'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    record = json.loads((ROOT/'results/continuation/guest_Hermes_artifact_preparation.json').read_text())
    output = PRIVATE/'runtime-media'
    output.mkdir(mode=0o700, exist_ok=True)
    members = {}
    included_roots = {'agent', 'hermes_cli', 'tools', 'hermes', 'providers', 'gateway',
                      'acp_adapter', 'cron', 'locales', 'plugins'}
    for path in sorted((PRIVATE/'source').rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(PRIVATE/'source')
        if len(rel.parts) == 1 and (path.suffix == '.py' or path.name in ('LICENSE', 'SOUL.md', 'cli-config.yaml.example')):
            members['hermes/'+str(rel)] = path.read_bytes()
        elif rel.parts[0] in included_roots and path.suffix in ('.py', '.json', '.yaml', '.yml'):
            members['hermes/'+str(rel)] = path.read_bytes()
    skipped = []
    for item in record['wheels']:
        path = PRIVATE/'wheels'/item['filename']
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('locked_wheel_bytes_changed:'+path.name)
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                name = PurePosixPath(entry.filename)
                if entry.is_dir():
                    continue
                if name.is_absolute() or '..' in name.parts or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('wheel_path_rejected')
                parts = name.parts
                if parts[0].endswith('.data'):
                    if len(parts) < 3 or parts[1] not in ('purelib', 'platlib'):
                        skipped.append(path.name+':'+entry.filename)
                        continue
                    parts = parts[2:]
                if parts[-1].endswith('.pth'):
                    skipped.append(path.name+':'+entry.filename)
                    continue
                target = 'hermes-deps/'+'/'.join(parts)
                raw = archive.read(entry)
                if target in members and members[target] != raw:
                    raise ValueError('wheel_collision:'+target)
                members[target] = raw
    with zipfile.ZipFile(output/'runtime.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(members.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, raw)
    iso = PRIVATE/'runtime.iso'
    subprocess.run(['/usr/bin/genisoimage', '-quiet', '-r', '-J', '-V', 'MANI_RUNTIME', '-o', str(iso), str(output)], check=True)
    iso.chmod(0o600)
    lock = {'Hermes_revision': REVISION, 'runtime_zip_sha256': digest(output/'runtime.zip'),
            'runtime_iso_sha256': digest(iso), 'runtime_iso_bytes': iso.stat().st_size,
            'source_files_and_dependency_members': len(members), 'wheel_count': len(record['wheels']),
            'skipped_wheel_members': skipped, 'host_agent_execution': False}
    (ROOT/'configs/guest-runtime.lock.json').write_text(json.dumps(lock, indent=2)+'\n')
    print(json.dumps(lock))


if __name__ == '__main__':
    main()
