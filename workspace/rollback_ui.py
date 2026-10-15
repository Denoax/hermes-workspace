"""Restore only hash-matched UI checkpoint bytes. Never opens user data."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

EXISTING = {'workspace/ui/index.html', 'workspace/ui/app.js', 'workspace/ui/style.css',
            'workspace/server.py', 'workspace/catalog.py'}
ASSETS = {'workspace/ui/fonts/' + n + '.ttf' for n in ['BebasNeue', 'DMSans', 'SixCaps']}
ASSETS |= {'workspace/ui/licenses/' + n + '-OFL.txt' for n in ['BebasNeue', 'DMSans', 'SixCaps']}
ASSETS.add('workspace/ui/CREDITS.md')


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def restore(project, checkpoint):
    project = Path(project).absolute(); checkpoint = Path(checkpoint).absolute()
    manifest = json.loads((checkpoint / 'manifest.json').read_text())
    entries = manifest['files']
    if set(entries) != EXISTING | ASSETS: raise ValueError('unexpected_checkpoint_scope')
    # Verify the whole transaction before writing any byte.
    for relative, item in entries.items():
        name = PurePosixPath(relative)
        if name.is_absolute() or '..' in name.parts: raise ValueError('unsafe_checkpoint_path')
        target = project / relative
        ancestor = target
        while ancestor != project.parent:
            if ancestor.is_symlink(): raise ValueError('source_symlink_changed')
            ancestor = ancestor.parent
        if not target.is_file() or digest(target) != item['after']: raise ValueError('unrelated_drift:' + relative)
        if item['before'] is not None:
            backup = checkpoint / 'before' / relative
            if backup.is_symlink() or digest(backup) != item['before']: raise ValueError('checkpoint_hash_mismatch')
    for relative, item in entries.items():
        target = project / relative
        if item['before'] is None:
            target.unlink()
        else:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.hermes-ui-rollback-', delete=False) as staged:
                staged.write((checkpoint / 'before' / relative).read_bytes()); staged.flush(); os.fsync(staged.fileno())
                name = Path(staged.name)
            name.chmod(item['mode']); os.replace(name, target)
    return {'restored_existing_files': len(EXISTING), 'removed_created_assets': len(ASSETS), 'user_data_opened': False}


def main():
    if os.geteuid() == 0: raise SystemExit('Use the normal user, without sudo.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--checkpoint', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.project, args.checkpoint), indent=2))


if __name__ == '__main__': main()
