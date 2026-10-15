"""Hash-bound rollback for this UI change. Never restores a private catalog."""
import argparse,hashlib,json,os,stat,tempfile,urllib.request
from pathlib import Path,PurePosixPath

ALLOWED={'workspace/server.py','workspace/launcher.py','workspace/parity_browser.py','workspace/rollback_parity.py',
 'workspace/probe_pointer_parity.py','workspace/probe_parity_motion.py','workspace/probe_parity_native.py','workspace/probe_parity_reference.py','workspace/probe_parity_cost.py',
 'tests/test_portfolio_assets.py','tests/test_portfolio_ui.mjs','tests/fixtures/navConnection.ts','tests/test_parity_rollback.py',
 'scripts/build_portfolio_ports.py','scripts/package_parity_review.py'}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def safe(path,root):
 current=path
 while current!=root.parent:
  if current.is_symlink():raise ValueError('symlink_refused')
  current=current.parent

def appearance(values):
 # Only supported appearance fields are changed, after reading the current view.
 # Credentials are read privately, never printed, serialized or returned.
 if set(values)!={'theme','motion'}or values['theme']not in {'dark','light'}or values['motion']not in {'system','reduced'}:raise ValueError('appearance_scope')
 origin='http://127.0.0.1:18791';credential=(Path.home()/'.local/state/hermes-workspace/client-cookie').read_text().strip()
 headers={'Cookie':'hermes_session='+credential,'Origin':origin,'Content-Type':'application/json'}
 with urllib.request.urlopen(urllib.request.Request(origin+'/hermes-workspace/api/bootstrap',headers=headers),timeout=3)as response:headers['X-Hermes-CSRF']=json.load(response)['csrf']
 def rpc(method,fields):
  data=json.dumps({'version':1,'method':method,'fields':fields}).encode()
  with urllib.request.urlopen(urllib.request.Request(origin+'/hermes-workspace/api/rpc',headers=headers,data=data),timeout=3)as response:return json.load(response)['result']
 state=rpc('view.read',{})
 if state is not None:state.update(values);rpc('view.write',{'state':state})

def restore(project,checkpoint,desktop_entry=None,restore_appearance=False):
 project=Path(project).absolute();checkpoint=Path(checkpoint).absolute();manifest=json.loads((checkpoint/'manifest.json').read_text());entries=manifest['files']
 if not 1<=len(entries)<=100:raise ValueError('checkpoint_scope')
 targets=[]
 for relative,item in entries.items():
  name=PurePosixPath(relative)
  if name.is_absolute()or'..'in name.parts or not(relative in ALLOWED or relative.startswith('workspace/ui/')):raise ValueError('checkpoint_scope')
  target=project/relative;safe(target,project)
  if not target.is_file()or digest(target)!=item['after']:raise ValueError('unrelated_drift:'+relative)
  backup=checkpoint/'before'/relative
  if item['before']is not None:
   safe(backup,checkpoint)
   if not backup.is_file()or digest(backup)!=item['before']:raise ValueError('checkpoint_hash')
  targets.append((target,backup,item))
 if desktop_entry:
  target=Path(desktop_entry).absolute();item=manifest['desktop']
  if target.name!='hermes-workspace.desktop':raise ValueError('desktop_scope')
  safe(target,target.parent)
  backup=checkpoint/'desktop-entry.before'
  safe(backup,checkpoint)
  if not target.is_file()or digest(target)!=item['after']or digest(backup)!=item['before']:raise ValueError('desktop_drift')
  targets.append((target,backup,item))
 # Verify the entire transaction before any write, including supported appearance.
 if restore_appearance:appearance(manifest['appearance_before'])
 for target,backup,item in targets:
  if item['before']is None:target.unlink();continue
  with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.hermes-parity-rollback-',delete=False)as staged:
   staged.write(backup.read_bytes());staged.flush();os.fsync(staged.fileno());temporary=Path(staged.name)
  temporary.chmod(item['mode']);os.replace(temporary,target)
 return {'files_restored':len(targets),'catalog_or_transcript_restored':False,'appearance_restored':restore_appearance}

if __name__=='__main__':
 if os.geteuid()==0:raise SystemExit('Run as the normal user, without sudo.')
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project',type=Path,required=True);parser.add_argument('--checkpoint',type=Path,required=True);parser.add_argument('--desktop-entry',type=Path);parser.add_argument('--restore-appearance',action='store_true');args=parser.parse_args()
 print(json.dumps(restore(args.project,args.checkpoint,args.desktop_entry,args.restore_appearance),indent=2))
