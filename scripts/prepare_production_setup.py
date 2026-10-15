"""Freeze a production repair plan; no privilege, service mutation or inference."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state', type=Path)
    args = parser.parse_args()
    state = args.state.expanduser()
    if not state.is_absolute() or '..' in state.parts:
        raise ValueError('absolute_private_preparation_directory_required')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = state.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('private_owned_preparation_directory_required')
    helper = ROOT / 'native/production_setup.py'
    spec = importlib.util.spec_from_file_location('production_setup_source', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.ROOT != ROOT or os.geteuid() == 0:
        raise RuntimeError('fixed_unprivileged_preparation_only')
    normal = json.loads((ROOT / 'configs/normal-profile.lock.json').read_text())
    if set(normal) != module.NORMAL_FILES:
        raise ValueError('four_fixed_normal_configuration_pins_required')
    for relative, digest in normal.items():
        module.read_pinned(Path('/home/mani') / relative, digest, owner=os.getuid())
    _, user = module.read_file(module.USER_UNIT, owner=os.getuid())
    _, recovery = module.read_file(module.RECOVERY, owner=0, protected=True)
    replacement = ROOT / 'native/recovery.py'
    plan = {'version': 1, 'units': module.unit_texts(), 'old_user_unit_sha256': user['sha256'], 'recovery_before_sha256': recovery['sha256'], 'recovery_source': {'path': str(replacement), 'sha256': hashlib.sha256(replacement.read_bytes()).hexdigest()}, 'normal_configuration_sha256': normal, 'application_sources': {str(ROOT / relative): hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in ('workspace/server.py', 'workspace/production_client.py')}}
    module.validate_plan(plan)
    raw = (json.dumps(plan, indent=2) + '\n').encode()
    path = state / 'production-plan.json'
    if path.exists() and path.read_bytes() != raw:
        raise RuntimeError('preserve_other_prepared_plan_use_new_private_directory')
    if not path.exists():
        with path.open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
    text = helper.read_text()
    text, n = re.subn(r"^PLAN = Path\('[^']*'\)$", 'PLAN = Path(' + repr(str(path)) + ')', text, flags=re.MULTILINE)
    text, m = re.subn(r"^PLAN_SHA = '[^']*'$", 'PLAN_SHA = ' + repr(hashlib.sha256(raw).hexdigest()), text, flags=re.MULTILINE)
    if (n, m) != (1, 1):
        raise RuntimeError('fixed_helper_plan_markers_required')
    helper.write_text(text)
    receipt = {'prepared_only': True, 'GPU_window_opened': False, 'models_loaded': False, 'plan_sha256': hashlib.sha256(raw).hexdigest(), 'helper_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(), 'helper': str(helper), 'plan': str(path)}
    output = state / 'production-preparation.json'
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
