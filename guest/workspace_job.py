"""Pinned Hermes with three scoped tools inside worker_a; never a host agent."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import uuid
sys.path.insert(0,'/opt/mani-vmlab')
from json_limits import bounded_json
from solve import configuration,HERMES_REVISION,RELAY


def name(value):
    if type(value) is not str or value.startswith('/') or '\\' in value or any(p in ('','.','..') or p.startswith('.') for p in value.split('/')):raise ValueError('workspace_path_denied')
    return value


def main():
    if os.geteuid()!=1000 or json.loads(Path('/etc/mani-vmlab/guest.json').read_text()).get('role')!='worker_a':raise RuntimeError('qualified_nonroot_worker_required')
    for path in ['workspace_job.py','solve.py','run_code.py','workspace_contract.py']:
        info=(Path('/opt/mani-vmlab')/path).lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or not stat.S_ISREG(info.st_mode):raise RuntimeError('immutable_guest_helpers_required')
    request=bounded_json(sys.stdin.buffer.read(65537),max_bytes=65536)
    if type(request) is not dict or set(request)!={'prompt','model','relay_token','files','authority'} or request['authority'] not in ('read','candidate'):raise ValueError('fixed_guest_job_schema')
    if type(request['prompt']) is not str or len(request['prompt'].encode())>8192:raise ValueError('prompt_limit')
    with tempfile.TemporaryDirectory(prefix='mani-workspace-') as directory,tempfile.TemporaryDirectory(prefix='mani-profile-') as home:
        root=Path(directory);events=[];remaining=12
        for item in request['files']:
            path=root/name(item['path']);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(item['text'])
        os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME=home,HERMES_HOME=home,LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1')
        os.chdir(root)
        config=configuration(request['model'],request['relay_token']);config['agent']['max_turns']=8
        path=Path(home)/'config.yaml';path.write_text(json.dumps(config));path.chmod(0o600)
        sys.path[:0]=['/opt/hermes','/opt/hermes-deps']
        with tempfile.TemporaryFile(mode='w+') as logs,contextlib.redirect_stdout(logs),contextlib.redirect_stderr(logs):
            from run_agent import AIAgent
            from tools.registry import registry
            from workspace_contract import TOOLS,READ_TOOLS
            def handle(tool,args):
                nonlocal remaining
                remaining-=1
                if remaining<0:raise ValueError('guest_action_budget_exhausted')
                started=time.monotonic()
                if type(args) is not dict:raise ValueError('tool_object_required')
                if tool=='lab_read_file':
                    if set(args)!={'path'}:raise ValueError('fixed_read_schema')
                    target=root/name(args['path'])
                    fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                    try:
                        info=os.fstat(fd)
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>16384:raise ValueError('tool_file_limit')
                        result={'text':os.read(fd,16385).decode()}
                    finally:os.close(fd)
                elif tool=='lab_write_file':
                    if set(args)!={'path','text'} or type(args['text']) is not str or len(args['text'].encode())>16384 or '\0' in args['text']:raise ValueError('fixed_write_schema')
                    target=root/name(args['path']);target.parent.mkdir(parents=True,exist_ok=True)
                    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'w') as output:output.write(args['text'])
                    result={'written':args['path']}
                else:
                    if set(args)!={'language','stdin'} or args['language'] not in ('python','cpp') or type(args['stdin']) is not str:raise ValueError('fixed_run_schema')
                    files=[]
                    for target in sorted(root.rglob('*')):
                        if target.is_file() and not target.is_symlink():files.append({'path':str(target.relative_to(root)),'text':target.read_text()})
                    data={'language':args['language'],'stdin':args['stdin'],'files':files}
                    process=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','-I','/opt/mani-vmlab/run_code.py'],input=json.dumps(data).encode(),capture_output=True,timeout=30)
                    if process.returncode:raise RuntimeError('guest_candidate_guardian_failed')
                    result=bounded_json(process.stdout,max_bytes=32768)
                events.append({'tool':tool,'wall_seconds':time.monotonic()-started,'result':result})
                return json.dumps(result)
            for schema in READ_TOOLS if request['authority']=='read' else TOOLS:
                tool=schema['function']['name']
                registry.register(name=tool,toolset='mani_lab',schema=schema['function'],handler=lambda args,tool=tool,**kwargs:handle(tool,args),max_result_size_chars=12000)
            agent=AIAgent(base_url=RELAY,api_key=request['relay_token'],provider='custom',model=request['model'],
                enabled_toolsets=['mani_lab'],max_iterations=8,max_tokens=1024,session_id=uuid.uuid4().hex,
                quiet_mode=True,verbose_logging=False,save_trajectories=False,skip_context_files=True,
                load_soul_identity=False,skip_memory=True,skip_background_review=True,fallback_model=None,
                run_budget_seconds=360,request_overrides={'max_tokens':1024,'temperature':0.0,'top_p':1.0,'seed':41,'parallel_tool_calls':False})
            filenames=[item['path'] for item in request['files']]
            system='Work only in this disposable workspace with the tools actually advertised. program.py reads JSON from stdin; solution.cpp reads integers from stdin. Do not access profiles, services, network, authority or other projects. Return a concise evidence-based final answer. Available files: '+json.dumps(filenames)
            try:answer=agent.run_conversation(request['prompt'],system_message=system)
            finally:agent.close()
        exported=[]
        for path in sorted(root.rglob('*')):
            if path.is_file() and not path.is_symlink():
                text=path.read_text();relative=str(path.relative_to(root));name(relative)
                if len(text.encode())>16384:raise ValueError('guest_export_file_limit')
                exported.append({'path':relative,'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'bytes':len(text.encode())})
        if len(exported)>16 or sum(x['bytes'] for x in exported)>32768:raise ValueError('guest_export_total_limit')
        final=answer.get('final_response')
        if type(final) is not str or len(final.encode())>32768:raise ValueError('guest_final_limit')
        print(json.dumps({'answer':final,'files':exported,'tool_events':events,'Hermes_revision':HERMES_REVISION,'tool_profile':'guest_scoped_v1','agent_uid':os.geteuid()}))


if __name__=='__main__':main()
