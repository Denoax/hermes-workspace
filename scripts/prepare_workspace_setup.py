"""Freeze reviewed workspace source/helpers and fixed no-GPU setup inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
PREVIOUS='7dd20b4588af216d0b3bf8cdee2629a1b3f28f45cf5efaab47e1e499d84069c8'


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('state',type=Path);parser.add_argument('--previous-pack',default=PREVIOUS);args=parser.parse_args()
    state=args.state.absolute()
    if state.is_symlink() or not re.fullmatch('[0-9a-f]{64}',args.previous_pack):raise ValueError('owned_private_setup_state_and_previous_pin_required')
    state.mkdir(mode=0o700,parents=True,exist_ok=True)
    if state.stat().st_mode&0o077:raise ValueError('private_setup_state_required')
    pack=state/('workspace-source-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'.zip')
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/prepare_native_runtime.py'),str(pack)],check=True,capture_output=True)
    pack_sha=digest(pack)
    helper=ROOT/'native/workspace_acceptance.py';text=helper.read_text()
    text=re.sub(r"REQUIRED_PACK='[^']+'",'REQUIRED_PACK='+repr(pack_sha),text);helper.write_text(text)
    roles={'installer':ROOT/'native/install_runtime.py','updater':ROOT/'native/update_runtime.py','recovery':ROOT/'native/recovery.py',
        'recovery_entry':ROOT/'native/workspace_recovery.py','acceptance':helper,'watchdogs':ROOT/'native/watchdog_probe.py',
        'protocol':ROOT/'native/protocol_probe.py','normal_profile':ROOT/'configs/normal-profile.lock.json',
        'source_pack':pack,'runtime_iso':state/'workspace-runtime.iso','pin_backup':state/'sidebar-before.qml','router_backup':state/'hermes-worker-before'}
    baseline=json.loads((state/'baseline.json').read_text());router=json.loads((state/'router-update.json').read_text())
    artifacts=json.loads((state/'workspace-artifacts.json').read_text())
    plan={'files':{name:{'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size} for name,path in roles.items()},
        'source_pack_sha256':pack_sha,'compiler_zip_sha256':artifacts['compiler_zip_sha256'],'runtime_iso_sha256':artifacts['runtime_iso_sha256'],
        'pin_before_sha256':baseline['/home/mani/.config/quickshell/kona/sidebar/shell.qml']['sha256'],
        'router_before_sha256':router['before_sha256'],'pin_before_mode':baseline['/home/mani/.config/quickshell/kona/sidebar/shell.qml']['mode'],
        'router_before_mode':router['mode']}
    if plan['files']['runtime_iso']['sha256']!=plan['runtime_iso_sha256'] or plan['files']['pin_backup']['sha256']!=plan['pin_before_sha256'] or plan['files']['router_backup']['sha256']!=plan['router_before_sha256']:raise ValueError('prepared_media_or_rollback_pin_drift')
    output=state/'workspace-setup-input.json';raw=(json.dumps(plan,indent=2)+'\n').encode();output.write_bytes(raw);output.chmod(0o600)
    (ROOT/'configs/workspace-setup-input.json').write_bytes(raw)
    setup=ROOT/'native/workspace_setup.py';text=setup.read_text()
    text=re.sub(r"INPUT_SHA='[^']+'",'INPUT_SHA='+repr(hashlib.sha256(raw).hexdigest()),text)
    text=re.sub(r"PREVIOUS_PACK='[^']+'",'PREVIOUS_PACK='+repr(args.previous_pack),text)
    text=re.sub(r"INPUT=Path\('[^']+'\)",'INPUT=Path('+repr(str(output))+')',text);setup.write_text(text)
    record={'source_pack_sha256':pack_sha,'input_sha256':hashlib.sha256(raw).hexdigest(),'setup_helper_sha256':digest(setup),
        'previous_pack':args.previous_pack,'prepared_only':True,'GPU_window_opened':False,'native_installed':False}
    (state/'prepared-workspace.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))


if __name__=='__main__':main()
