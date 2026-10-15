"""Fixed guest-root guardian; compiler and candidate code always run as UID 1001."""
import fcntl
import json
import os
from pathlib import Path
import pwd
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,'/opt/mani-vmlab')
from json_limits import bounded_json


def limits(account):
    os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
    resource.setrlimit(resource.RLIMIT_CPU,(8,10))
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024))
    resource.setrlimit(resource.RLIMIT_NPROC,(32,32));resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))


def execute(argv,home,account,stdin=b''):
    with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
        process=subprocess.Popen(argv,cwd=home,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,
            start_new_session=True,preexec_fn=lambda:limits(account),
            env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C.UTF-8','TMPDIR':str(home)})
        try:process.communicate(stdin,timeout=12)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
            return {'exit':None,'error':'candidate_deadline','stdout':'','stderr':''}
        stdout.seek(0);stderr.seek(0)
        out=stdout.read(8193);err=stderr.read(4097)
        if len(out)>8192 or len(err)>4096:return {'exit':None,'error':'candidate_output_limit','stdout':'','stderr':''}
        return {'exit':process.returncode,'stdout':out.decode('utf-8',errors='replace'),'stderr':err.decode('utf-8',errors='replace')}


def retire_candidates(account):
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():continue
        descriptor=None
        try:
            descriptor=os.pidfd_open(int(directory.name))
            if directory.stat().st_uid==account.pw_uid:
                signal.pidfd_send_signal(descriptor,signal.SIGKILL)
        except (ProcessLookupError,FileNotFoundError):pass
        finally:
            if descriptor is not None:os.close(descriptor)


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=Path('/opt/mani-vmlab/run_code.py') or len(sys.argv)!=1:
        raise SystemExit('fixed_guest_guardian_only')
    marker=json.loads(Path('/etc/mani-vmlab/guest.json').read_text())
    if marker.get('role') not in ('worker_a','worker_b'):raise ValueError('worker_only')
    request=bounded_json(sys.stdin.buffer.read(65537),max_bytes=65536)
    if type(request) is not dict or set(request)!={'language','files','stdin'} or request['language'] not in ('python','cpp'):
        raise ValueError('fixed_guest_execution_schema')
    if type(request['stdin']) is not str or len(request['stdin'].encode())>8192:raise ValueError('candidate_input_limit')
    if type(request['files']) is not list or not 1<=len(request['files'])<=16:raise ValueError('candidate_file_count')
    account=pwd.getpwnam('mani-candidate')
    if account.pw_uid!=1001 or account.pw_uid==pwd.getpwnam('lab').pw_uid:raise ValueError('separate_candidate_identity_required')
    os.umask(0o077)
    with Path('/run/mani-code.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='mani-candidate-',dir='/tmp') as name:
            home=Path(name);os.chown(home,account.pw_uid,account.pw_gid);seen=set();total=0
            for item in request['files']:
                if type(item) is not dict or set(item)!={'path','text'}:raise ValueError('candidate_file_schema')
                relative=item['path']
                if type(relative) is not str or relative.startswith('/') or any(part in ('','.','..') or part.startswith('.') for part in relative.split('/')) or '\\' in relative:
                    raise ValueError('candidate_path_scope')
                if relative in seen or type(item['text']) is not str or '\0' in item['text']:raise ValueError('candidate_duplicate_or_binary')
                seen.add(relative);data=item['text'].encode();total+=len(data)
                if total>32768:raise ValueError('candidate_total_size')
                file=home/relative;file.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
                file.write_bytes(data);os.chown(file,account.pw_uid,account.pw_gid)
            try:
                if request['language']=='cpp':
                    compilation=execute(['/usr/bin/g++','-std=c++17','-O0','solution.cpp','-o','candidate'],home,account)
                    if compilation.get('exit')!=0:
                        print(json.dumps({'phase':'compile','candidate_uid':account.pw_uid,**compilation}));return
                    argv=[str(home/'candidate')]
                else:argv=['/usr/bin/python3','-I','program.py']
                result=execute(argv,home,account,request['stdin'].encode())
                print(json.dumps({'phase':'run','candidate_uid':account.pw_uid,**result}))
            finally:
                # Compilation failures and successful programs can both leave
                # descendants. This UID belongs only to this disposable VM job.
                retire_candidates(account)


if __name__=='__main__':main()
