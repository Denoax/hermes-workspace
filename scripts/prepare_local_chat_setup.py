"""Freeze the existing no-GPU workspace update and one-time text admission setup."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
 p=argparse.ArgumentParser();p.add_argument('state',type=Path);p.add_argument('--workspace-state',type=Path,required=True);p.add_argument('--previous-pack',required=True);args=p.parse_args()
 args.state.mkdir(mode=0o700,parents=True,exist_ok=True)
 if args.state.is_symlink() or args.state.stat().st_mode&0o077:raise ValueError('private_preparation_state_required')
 subprocess.run([sys.executable,str(ROOT/'scripts/prepare_workspace_setup.py'),str(args.workspace_state),'--previous-pack',args.previous_pack],check=True,capture_output=True)
 prepared=json.loads((args.workspace_state/'prepared-workspace.json').read_text());source=ROOT/'native/workspace_setup.py'
 unit=Path('/etc/systemd/system/mani-vmlab-inference-window.service')
 sys.path.insert(0,str(ROOT));from native.window import unit_text
 plan={'workspace_setup':{'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},'normal_configuration_sha256':json.loads((ROOT/'configs/normal-profile.lock.json').read_text()),'source_pack_sha256':prepared['source_pack_sha256'],'window_unit_before_sha256':hashlib.sha256(unit.read_bytes()).hexdigest(),'window_unit_after_sha256':hashlib.sha256(unit_text().encode()).hexdigest()}
 path=args.state/'local-chat-setup-plan.json';raw=(json.dumps(plan,indent=2)+'\n').encode();path.write_bytes(raw);path.chmod(0o600)
 helper=ROOT/'native/local_chat_setup.py';text=helper.read_text();text=re.sub(r"PLAN=Path\('[^']*'\)",'PLAN=Path('+repr(str(path))+')',text);text=re.sub(r"PLAN_SHA='[^']*'",'PLAN_SHA='+repr(hashlib.sha256(raw).hexdigest()),text);helper.write_text(text)
 result={'source_pack_sha256':prepared['source_pack_sha256'],'setup_helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),'plan_sha256':hashlib.sha256(raw).hexdigest(),'prepared_only':True,'GPU_window_opened':False};(args.state/'text-chat-preparation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
