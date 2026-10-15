"""Explicit linked-artifact inventory. Listing never hashes weights or loads models."""
import hashlib
import json
import os
from pathlib import Path
import stat
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
STATE=Path.home()/'.local/state/hermes-workspace'
LABELS={'normal':'Qwen3.6 · Normal','abliterated':'Qwen3.6 · Abliterated'}
_runner_pin=None


def identity(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


class Inventory:
    def __init__(self,lock=None,cache=None):
        self.lock=Path(lock or ROOT/'configs/backend-artifacts.lock.json')
        self.cache=Path(cache or STATE/'model-inventory.json')

    def entries(self):
        try:
            linked=json.loads(self.lock.read_text())['models'];cached=json.loads(self.cache.read_text())
        except (OSError,ValueError,KeyError):return []
        result=[]
        try:reasoning=json.loads((self.cache.parent/'reasoning-capabilities.json').read_text())
        except (OSError,ValueError):reasoning={}
        for arm in LABELS:
            try:
                item=linked[arm];proof=cached[arm];path=Path(item['source']);info=path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or proof['identity']!=identity(info) or proof['sha256']!=item['sha256'] or info.st_size!=item['bytes'] or proof['path']!=str(path):continue
                result.append({'id':arm,'label':LABELS[arm],'state':'installed_unloaded',
                               'sha256':item['sha256'],'vision':False,'audio':False,
                               'reasoning':['off','on'] if reasoning.get(arm)==item['sha256'] else [],'context':65536 if arm=='normal' else 8192})
            except (OSError,ValueError,KeyError):continue
        return result

    def require(self,arm):
        entry=next((r for r in self.entries() if r['id']==arm),None)
        if entry is None:raise ValueError('model_not_verified_and_linked')
        return entry

    def verify(self):
        """Explicit preparation operation; cache invalidates on any file drift."""
        linked=json.loads(self.lock.read_text())['models'];rows={}
        for arm,item in linked.items():
            path=Path(item['source']);before=path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid():raise ValueError('owned_regular_model_required')
            with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
            if identity(before)!=identity(path.lstat()) or digest!=item['sha256'] or before.st_size!=item['bytes']:raise ValueError('model_pin_changed')
            rows[arm]={'identity':identity(before),'sha256':digest,'path':str(path),'verified':True}
        self.cache.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        temporary=self.cache.with_suffix('.tmp');temporary.write_text(json.dumps(rows));temporary.chmod(0o600);temporary.replace(self.cache)
        return self.entries()


def normal_identity():
    """The loaded alias alone is insufficient: check the owning process and model."""
    import subprocess
    from workspace.server import normal_profile_unchanged
    if not normal_profile_unchanged():raise RuntimeError('normal_configuration_drift')
    pid=int(subprocess.check_output(['/usr/bin/systemctl','--user','show','manibot-llama.service','-p','MainPID','--value'],timeout=3))
    proc=Path('/proc')/str(pid)
    args=(proc/'cmdline').read_bytes().decode().split('\0')
    linked=json.loads((ROOT/'configs/backend-artifacts.lock.json').read_text())
    expected=linked['models']['normal']['source']
    executable=Path(linked['backend_directory'])/'llama-server'
    # Verify the fixed service and runner, rather than trusting an alias supplied
    # by whichever server happens to answer the normal loopback port.
    if '--model' not in args or args[args.index('--model')+1]!=expected or args[0]!=str(executable):
        raise RuntimeError('normal_loaded_process_identity_changed')
    global _runner_pin
    info=executable.lstat();expected_runner=next(r for r in linked['backend_files'] if r['name']=='llama-server')
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():raise RuntimeError('normal_runner_file_changed')
    if _runner_pin is None or _runner_pin[0]!=identity(info):
        with executable.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        if identity(info)!=identity(executable.lstat()):raise RuntimeError('normal_runner_changed_during_verification')
        _runner_pin=(identity(info),digest)
    if _runner_pin[1]!=expected_runner['sha256']:raise RuntimeError('normal_runner_hash_changed')
    with urllib.request.urlopen('http://127.0.0.1:8080/props',timeout=2) as response:props=json.load(response)
    if props.get('model_alias')!='qwen3.6-35b-a3b-q4' or props.get('default_generation_settings',{}).get('n_ctx')!=65536:
        raise RuntimeError('normal_loaded_alias_or_context_changed')
    return {'alias':props['model_alias'],'context':65536,'build':props.get('build_info'),
            'thinking_template': 'enable_thinking' in props.get('chat_template',''),
            'process_link':'four_pinned_service_configurations_MainPID_exec_argv_and_runner_hash'}
