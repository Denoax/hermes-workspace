"""Fixed native qualification and explicitly chosen 30-minute workspace window."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import select
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import platform
import re
sys.dont_write_bytecode=True

SELF=Path('/usr/local/lib/mani-vmlab-setup/workspace_acceptance.py')
INSTALL=Path('/usr/local/lib/mani-vmlab')
PUBLIC=Path('/var/lib/mani-vmlab-review')
ORIGIN='http://127.0.0.1:18791'
REQUIRED_PACK='7e841e74690f8ea55d36b89e27174c1cf85eb3ade8c76371f42de9b997887a34'
USER_ENV={'PATH':'/usr/bin:/bin','HOME':'/home/mani','USER':'mani','LOGNAME':'mani','LANG':'C.UTF-8',
    'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus',
    'XDG_CONFIG_HOME':'/home/mani/.config','XDG_DATA_HOME':'/home/mani/.local/share','XDG_CACHE_HOME':'/home/mani/.cache',
    'WAYLAND_DISPLAY':'wayland-1'}


def hardware():
    gpu=subprocess.check_output(['/usr/bin/nvidia-smi','--query-gpu=name,driver_version,memory.used,memory.total','--format=csv,noheader,nounits'],timeout=5).decode().strip().split(', ')
    driver=Path('/proc/driver/nvidia/version').read_text()
    if len(gpu)!=4 or gpu[1] not in driver or gpu[0]!='NVIDIA GeForce RTX 4070':raise RuntimeError('actual_GPU_or_loaded_driver_mismatch')
    memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemAvailable:','MemTotal:','SwapFree:','SwapTotal:'))}
    home=os.statvfs('/home/mani-vmlab-data');root=os.statvfs('/')
    if memory['MemAvailable']<12*1024**3 or home.f_bavail*home.f_frsize<16*1024**3 or root.f_bavail*root.f_frsize<512*1024**2 or not os.access('/dev/kvm',os.R_OK|os.W_OK):raise RuntimeError('current_hardware_headroom_or_KVM_gate_failed')
    return {'kernel':platform.release(),'CPU_threads':os.cpu_count(),'GPU':gpu[0],'loaded_and_userspace_driver':gpu[1],
        'device_aggregate_VRAM_MiB':int(gpu[2]),'device_total_VRAM_MiB':int(gpu[3]),'memory_bytes':memory,
        'root_available_bytes':root.f_bavail*root.f_frsize,'home_available_bytes':home.f_bavail*home.f_frsize,
        'KVM_access':True,'host_packages_changed':False}


def pinned(path):
    info=path.lstat()
    if info.st_uid!=0 or info.st_mode&0o022 or path.is_symlink():raise PermissionError('protected_acceptance_source_required')


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:raise SystemExit('fixed_protected_acceptance_only')
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['qualify','run']);operation=parser.parse_args().operation
    for path in [SELF,SELF.parent,INSTALL,Path('/etc/mani-vmlab/config.json')]:pinned(path)
    config=json.loads(Path('/etc/mani-vmlab/config.json').read_text())
    if config['source_pack_sha256']!=REQUIRED_PACK or config.get('workspace_api')!=1:raise RuntimeError('reviewed_workspace_runtime_required')
    sys.path.insert(0,str(SELF.parent));sys.path.insert(0,str(INSTALL))
    import supervisor,window
    from lab.state import atomic_json
    report=PUBLIC/('workspace-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'.json')
    record={'evidence_kind':'trusted_native_workspace_acceptance','source_pack_sha256':REQUIRED_PACK,
        'phases':[],'failures':[],'jobs':[],'compiler_probes':[],'cleanup':[],'window_opened':False}
    done=threading.Event();owner={'control':None,'run':None,'window':False}
    def save():atomic_json(report,record);report.chmod(0o644)
    def phase(text):record['phase']=text;record['phases'].append(text);save();print(text,flush=True)
    def beat():
        ticks=0
        while not done.wait(5):
            if owner['control'] and owner['run']:owner['control'].store.heartbeat(owner['run'])
            if owner['window']:window.beat()
            ticks+=1
            if ticks%2==0:print('Bounded acceptance healthy; '+record.get('phase','preparing'),flush=True)
    thread=threading.Thread(target=beat,daemon=True);thread.start()
    control=None
    try:
        if window.state().get('status') in ('active','opening','restoring','restore_failed'):raise RuntimeError('recover_existing_window_first')
        from recovery import NativeServices
        record['normal_before']=NativeServices().verify_normal_profile()
        record['actual_hardware_before']=hardware();save()
        if operation=='qualify':
            phase('Verifying actual copied model/backend byte pins before VM and compute tests.')
            import backend
            record['artifact_provenance']=backend.verify_artifacts();save()
            phase('Qualifying five current-source VM watchdog scenarios before inference.')
            watchdogs=subprocess.run(['/usr/bin/python3','-I',str(SELF.with_name('watchdog_probe.py')),'all'],capture_output=True,text=True,timeout=1250)
            if watchdogs.returncode:raise RuntimeError('current_VM_watchdog_gate_failed')
            record['watchdogs']=json.loads(watchdogs.stdout)
            if record['watchdogs']['all_passed'] is not True:raise RuntimeError('current_VM_watchdogs_not_proven')
            phase('Booting fresh no-agent workers for compiler and full registered recovery probes.')
            control=supervisor.Supervisor();owner['control']=control
            def created(run):owner['run']=run
            result=control.provision(on_created=created)
            if result['status']!='ok':raise RuntimeError('compiler_probe_boot_failed')
            run=result['run_id'];qualification=control.qualify(run)
            if qualification['status']!='ok':raise RuntimeError('compiler_probe_confinement_failed')
            record['qualification']=qualification
            cases=[('python','import json,sys\nv=json.load(sys.stdin)\nprint(json.dumps([min(100,max(0,x)) for x in v]))\n','[-10,0,5,101]','[0, 0, 5, 100]',True),
              ('python','print("[]")\n','[-10,0,5,101]','[0, 0, 5, 100]',False),
              ('cpp','#include <iostream>\nint main(){long long x;while(std::cin>>x)std::cout<<x*x<<" ";}\n','-5 0 7','25 0 49',True)]
            for language,text,stdin,expected,should_pass in cases:
                filename='program.py' if language=='python' else 'solution.cpp'
                response=control.ssh(run,'worker_b','validate',{'language':language,'stdin':stdin,'files':[{'path':filename,'text':text}]})
                actual=response.get('exit')==0 and response.get('stdout','').strip()==expected
                record['compiler_probes'].append({'language':language,'outside_passed':actual,'expected_pass':should_pass,
                    'result':response,'evidence_kind':'actual_fresh_guest_trusted_fixture_not_model_generation'})
                if actual!=should_pass:raise RuntimeError('independent_compiler_or_bad_candidate_gate_failed')
            phase('Qualifying actual pinned guest read/write/run semantics with a scripted no-model backend.')
            from protocol_probe import probe
            record['guest_protocol_fixture']=probe(control,run);save()
            if record['guest_protocol_fixture']['passed'] is not True:raise RuntimeError('pinned_guest_tool_wire_protocol_failed')
            phase('Testing complete registered update/removal ordering in the disposable worker.')
            record['disposable_recovery']=control.ssh(run,'worker_b','lifecycle_probe',{})
            checks=['drift_refused_before_mutation','all_owned_system_PIDs_zero','user_UI_PID_zero','normal_restore_hook_before_code_removal','pin_restored','copied_weights_retained','window_hook_retired','registered_update_measured','exact_accounts_retired','reinstall_services_started','thin_runtime_directories_and_symlinks_retired']
            if not all(record['disposable_recovery'].get(k) is True for k in checks):raise RuntimeError('disposable_complete_recovery_not_proven')
            record['cleanup'].append(control.cleanup(run));owner['run']=None
            if record['cleanup'][-1]['status']!='ok':raise RuntimeError('pre_inference_cleanup_not_proven')
            qualified_receipt={'source_pack_sha256':REQUIRED_PACK,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'report':str(report)}
            record['qualification_complete']=True
            phase('No-inference qualification complete; normal Qwen stayed available.')
            return
        receipt_path=Path('/var/lib/mani-vmlab-setup/workspace-qualified.json');pinned(receipt_path)
        receipt=json.loads(receipt_path.read_text());qualified_report=Path(receipt['report']);pinned(qualified_report)
        if not qualified_report.is_relative_to(PUBLIC) or receipt['source_pack_sha256']!=REQUIRED_PACK or receipt['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise RuntimeError('fresh_current_source_qualification_required')
        if hashlib.sha256(qualified_report.read_bytes()).hexdigest()!=receipt['report_sha256']:raise RuntimeError('qualification_receipt_drift')
        qualified=json.loads(qualified_report.read_text())
        if not qualified.get('qualification_complete') or qualified.get('failures'):raise RuntimeError('successful_compiler_recovery_and_watchdog_gates_required')
        record['pre_inference_qualification_report']=str(qualified_report);record['pre_inference_qualification_sha256']=hashlib.sha256(qualified_report.read_bytes()).hexdigest()
        import backend
        if not backend.artifacts_current():raise RuntimeError('verified_artifact_identity_drift_requalify_required')
        phase('Opening the explicitly selected 30-minute GPU window; normal Qwen will recover afterward.')
        window.command(['/usr/bin/systemctl','reset-failed',window.SERVICE])
        window.command(['/usr/bin/systemctl','start',window.SERVICE],timeout=30)
        if not window.active():raise RuntimeError('chosen_window_not_active')
        owner['window']=True;record['window_opened']=True;record['window_deadline']=window.state()['deadline']
        from guest.recovery import parent_fd
        cookie_path=Path('/home/mani/.local/state/hermes-workspace/client-cookie')
        with parent_fd(cookie_path) as (parent,name):
            descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(descriptor,'rb') as source:
            info=os.fstat(source.fileno())
            if info.st_uid!=1000 or not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_size>512:raise RuntimeError('bounded_owner_only_UI_cookie_required')
            key=source.read(513).decode().strip()
        req=urllib.request.Request(ORIGIN+'/hermes-workspace/api/bootstrap',headers={'Cookie':'hermes_session='+key})
        with urllib.request.urlopen(req,timeout=5) as r:csrf=json.load(r)['csrf']
        def rpc(method,fields):
            request=urllib.request.Request(ORIGIN+'/hermes-workspace/api/rpc',
                data=json.dumps({'version':1,'method':method,'fields':fields}).encode(),
                headers={'Cookie':'hermes_session='+key,'Origin':ORIGIN,'X-Hermes-CSRF':csrf,'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=20) as r:return json.load(r)['result']
        import backend
        from lab.process import identity,open_owned
        from model_probe import processing_log_after
        def wait_terminal(job):
            deadline=time.monotonic()+520
            while time.monotonic()<deadline:
                value=rpc('job.read',{'job_id':job})
                if value['state'] in ('review_ready','failed','cancelled','blocked'):return value
                if not window.active():raise RuntimeError('absolute_window_expired')
                time.sleep(.3)
            raise RuntimeError('actual_job_wait_deadline')
        phase('Proving actual UI Stop against a busy backend and exact VM identities.')
        cancel_project=rpc('workspace.create',{'label':'Owned actual Stop probe'})
        cancel_session=rpc('session.create',{'project_id':cancel_project['id'],'arm':'normal'})
        cancel_snapshot=rpc('workspace.files',{'project_id':cancel_project['id']})
        cancel_job=rpc('job.submit',{'session_id':cancel_session['id'],'client_job_id':uuid.uuid4().hex,
            'prompt':'Write a detailed 1500-word fictional story about synthetic characters in an imaginary village. Continue to the full requested length.',
            'snapshot_sha256':cancel_snapshot['snapshot_sha256'],'task_kind':'chat'})
        started=time.monotonic();deadline=started+450;busy=False;processing=[];backend_fd=None;fleet_fds=[]
        while time.monotonic()<deadline:
            value=rpc('job.read',{'job_id':cancel_job['id']})
            if value['state'] in ('failed','cancelled','blocked','review_ready'):raise RuntimeError('Stop_probe_finished_before_compute_observation')
            if value['state']=='running':
                try:
                    backend_pid=backend.resources()['backend_PID'];backend_fd=open_owned(identity(backend_pid))
                    busy=any(slot.get('is_processing') is True for slot in backend.get('/slots'))
                    raw=subprocess.check_output(['/usr/bin/journalctl','--boot','--no-pager','--output=json','--lines=32',
                        '_PID='+str(backend_pid),'_SYSTEMD_UNIT='+backend.UNIT,'--grep=launch_slot_.*processing task'],timeout=5)
                    busy=busy or processing_log_after(raw,started)
                    if busy:break
                    if backend_fd is not None:os.close(backend_fd);backend_fd=None
                except (OSError,RuntimeError,ValueError):pass
            time.sleep(.2)
        if not busy or backend_fd is None:raise RuntimeError('actual_busy_backend_required_for_Stop')
        manifest=json.loads((Path('/home/mani-vmlab-data/runs')/value['run_id']/'manifest.json').read_text())
        for process in manifest['processes']:
            if process['role'] in ('controller','worker_a','worker_b'):
                descriptor=open_owned(process)
                if descriptor is None:raise RuntimeError('live_exact_VM_identity_required')
                fleet_fds.append(descriptor)
        before=time.monotonic()
        try:
            browser=subprocess.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/python3','-I',
                '/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1/workspace/probe_stop.py',
                cancel_project['id'],cancel_session['id'],cancel_job['id']],capture_output=True,timeout=65,env=USER_ENV)
            if browser.returncode:rpc('job.cancel',{'job_id':cancel_job['id']});raise RuntimeError('actual_UI_Stop_control_failed')
            stopped=wait_terminal(cancel_job['id'])
            exited=bool(select.select([backend_fd],[],[],10)[0])
            vm_exit=[bool(select.select([fd],[],[],5)[0]) for fd in fleet_fds]
            record['actual_UI_Stop']={'browser':json.loads(browser.stdout),'busy_processing_observed':busy,
                'backend_PID':backend_pid,'exact_backend_exited':exited,'all_three_exact_VMs_exited':len(vm_exit)==3 and all(vm_exit),
                'wall_seconds_including_browser_boot':time.monotonic()-before,'job':stopped}
            if not exited or len(vm_exit)!=3 or not all(vm_exit) or stopped['state']!='cancelled' or stopped.get('cleanup',{}).get('status')!='ok':raise RuntimeError('actual_Stop_compute_and_cleanup_not_proven')
        finally:
            if backend_fd is not None:os.close(backend_fd)
            for descriptor in fleet_fds:os.close(descriptor)
        save()
        fixtures=[
            ('python','program.py','import json,sys\nprint(json.dumps([x for x in json.load(sys.stdin)]))\n',
             'Read program.py and fix it. It must read a JSON array of integers from stdin and print a JSON array with each value clamped to the inclusive range 0..100. Use the scoped tools and run it once to check.'),
            ('cpp','solution.cpp','#include <iostream>\nint main(){long long x;while(std::cin>>x)std::cout<<x*2<<" ";}\n',
             'Read solution.cpp and fix it. Read whitespace-separated integers from stdin and print their squares as whitespace-separated decimal integers. Use the scoped tools and run it once to check.')]
        selected_project=None
        for kind,filename,source,prompt in fixtures:
          for arm in ('normal','abliterated'):
              phase('Actual UI bridge → '+arm+' guest '+kind+' workspace task.')
              project=rpc('workspace.create',{'label':'Owned '+kind+' acceptance'})
              rpc('workspace.file.write',{'project_id':project['id'],'relative_path':filename,'text':source,'expected_sha256':None})
              session=rpc('session.create',{'project_id':project['id'],'arm':arm})
              snapshot=rpc('workspace.files',{'project_id':project['id']})
              job=rpc('job.submit',{'session_id':session['id'],'client_job_id':uuid.uuid4().hex,'prompt':prompt,
                      'snapshot_sha256':snapshot['snapshot_sha256'],'task_kind':kind})
              deadline=time.monotonic()+520
              while time.monotonic()<deadline:
                  result=rpc('job.read',{'job_id':job['id']})
                  if result['state'] in ('review_ready','failed','cancelled','blocked'):break
                  if not window.active():raise RuntimeError('absolute_window_expired')
                  time.sleep(2)
              record['jobs'].append(result);selected_project=project['id'];save()
              if result.get('state')!='review_ready' or result.get('validation',{}).get('passed') is not True:
                  record['failures'].append({'kind':'WorkerValidation','reason':arm+' '+kind+' did not pass its independent contract'})
                  save()
                  if result.get('state')!='review_ready':raise RuntimeError('actual_worker_runtime_failed')
        record['B08_new_profile']=[]
        cases=json.loads((INSTALL/'bench/cases.json').read_text())['cases']
        fixture=next(item for item in cases if item['case_id']=='B08')
        # The old wire omitted public expected_keys, while saying "requested
        # keys". Make that schema explicit only in this labelled new experiment.
        # No oracle values, grader or answer key are sent to the acting guest.
        b08=fixture['prompt']+'\nRequired public output schema: {"outputs": [four unsigned decimal integers]}. Use the available code tools to check the calculation.'
        record['B08_schema_diagnosis']={'old_wire_omitted_public_expected_keys':fixture['expected_keys'],
            'original_prompt_and_scorer_unchanged':True,'new_profile':'tool_assisted_explicit_public_schema','oracle_values_sent_to_guest':False}
        expected=[((x*3+7)&0xffffffff)^0x5a for x in (0,1,10,4294967295)]
        for arm in ('normal','abliterated'):
            phase('Matched B08 tool-assisted diagnostic: '+arm+'; original gate remains unchanged.')
            project=rpc('workspace.create',{'label':'B08 tool diagnostic '+arm})
            session=rpc('session.create',{'project_id':project['id'],'arm':arm})
            snapshot=rpc('workspace.files',{'project_id':project['id']})
            job=rpc('job.submit',{'session_id':session['id'],'client_job_id':uuid.uuid4().hex,'prompt':b08,
                'snapshot_sha256':snapshot['snapshot_sha256'],'task_kind':'diagnostic'})
            deadline=time.monotonic()+520
            while time.monotonic()<deadline:
                result=rpc('job.read',{'job_id':job['id']})
                if result['state'] in ('review_ready','failed','cancelled','blocked'):break
                if not window.active():raise RuntimeError('absolute_window_expired')
                time.sleep(2)
            answer=result.get('answer','')
            try:
                from starter.json_limits import bounded_json
                parsed=bounded_json(answer.encode(),max_bytes=32768)
                schema=type(parsed) is dict and set(parsed)=={'outputs'} and type(parsed['outputs']) is list and len(parsed['outputs'])==4 and all(type(x) is int and 0<=x<2**32 for x in parsed['outputs'])
                arithmetic=schema and parsed['outputs']==expected
            except ValueError:schema=False;arithmetic=False
            record['B08_new_profile'].append({'arm':arm,'profile':'guest_scoped_v1_tool_assisted_explicit_public_schema_new_experiment',
                'schema_passed':schema,'arithmetic_passed':arithmetic,'job':result,
                'original_no_tool_matrix_gate':'withheld_unchanged'});save()
        phase('Actual scoped router review through the same native broker.')
        router=subprocess.Popen(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
            '/home/mani/.local/bin/hermes-worker','lab','review','--project',selected_project,'--arm','normal'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=USER_ENV)
        output,error=router.communicate(b'Review the selected workspace files and identify their behavior. Do not change files or execute code. Return a concise evidence-based note.\n',timeout=520)
        if len(output)>131072 or len(error)>8192:raise RuntimeError('router_evidence_limit')
        record['router']={'exit':router.returncode,'output_records':[json.loads(line) for line in output.decode().splitlines()],
            'default_provider_changed':False,'host_candidate_execution':False}
        if router.returncode:raise RuntimeError('actual_scoped_router_review_failed')
        phase('Measuring router owner loss against a second busy owned guest job.')
        lost=subprocess.Popen(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
            '/home/mani/.local/bin/hermes-worker','lab','review','--project',selected_project,'--arm','normal'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=USER_ENV)
        lost.stdin.write(b'Write a detailed 1500-word fictional story about synthetic characters in an imaginary village. Continue to the full requested length.\n');lost.stdin.close()
        if not select.select([lost.stdout],[],[],20)[0]:lost.kill();lost.wait();raise RuntimeError('router_owner_probe_admission_deadline')
        admission=json.loads(lost.stdout.readline(4097));lost_id=admission['job_id']
        deadline=time.monotonic()+450;owner_started=time.monotonic();owner_busy=False
        descriptor=None;backend_descriptor=None
        try:
            while time.monotonic()<deadline:
                value=rpc('job.read',{'job_id':lost_id})
                if value['state'] in ('failed','cancelled','blocked','review_ready'):raise RuntimeError('owner_probe_not_busy')
                if value['state']=='running':
                    resources=backend.resources();pid=resources['backend_PID']
                    raw=subprocess.check_output(['/usr/bin/journalctl','--boot','--no-pager','--output=json','--lines=32',
                        '_PID='+str(pid),'_SYSTEMD_UNIT='+backend.UNIT,'--grep=launch_slot_.*processing task'],timeout=5)
                    if processing_log_after(raw,owner_started):owner_busy=True;break
                time.sleep(.2)
            if not owner_busy or value['outside_owner']['pid']!=lost.pid:raise RuntimeError('kernel_router_owner_and_busy_compute_required')
            descriptor=open_owned(value['outside_owner']);backend_descriptor=open_owned(identity(pid))
            if descriptor is None or backend_descriptor is None:raise RuntimeError('live_owner_and_backend_pidfds_required')
            started=time.monotonic();signal.pidfd_send_signal(descriptor,signal.SIGKILL);lost.wait(timeout=5)
            final=wait_terminal(lost_id)
            exited=bool(select.select([backend_descriptor],[],[],10)[0])
            record['actual_router_owner_loss']={'busy_processing_observed':True,'exact_owner_killed':True,
                'backend_compute_exited':exited,'wall_seconds':time.monotonic()-started,'job':final}
            if not exited or final['state']!='cancelled' or final.get('cleanup',{}).get('status')!='ok':raise RuntimeError('router_owner_loss_cleanup_not_proven')
        finally:
            for fd in (descriptor,backend_descriptor):
                if fd is not None:os.close(fd)
            if lost.poll() is None:lost.kill();lost.wait(timeout=5)
            lost.stdout.close();lost.stderr.close()
        save()
        phase('Ending this window through exact guard-owner loss and verifying normal recovery.')
        owner['window']=False
        recovery=subprocess.run(['/usr/bin/python3','-I',str(SELF.with_name('model_probe.py')),'window_owner_crash'],capture_output=True,text=True,timeout=240)
        if recovery.returncode:raise RuntimeError('actual_window_owner_recovery_not_proven')
        record['actual_window_owner_crash']=json.loads(recovery.stdout)
        phase('Workspace tasks complete; closing the chosen window and verifying normal recovery.')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        record['failures'].append({'kind':type(error).__name__,'reason':str(error)[:200]})
        print('Stopped at an evidence gate: '+str(error),flush=True)
    except KeyboardInterrupt:
        record['failures'].append({'kind':'KeyboardInterrupt','reason':'native_terminal_cancelled'})
    finally:
        owner['window']=False
        if owner['run'] and control:
            try:record['cleanup'].append(control.cleanup(owner['run']))
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:record['failures'].append({'kind':'Cleanup','reason':str(error)[:150]})
        if record['window_opened']:
            try:window.command(['/usr/bin/systemctl','stop',window.SERVICE],timeout=240)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:record['failures'].append({'kind':'WindowClose','reason':str(error)[:150]})
        record['window_restoration']=window.state()
        try:record['normal_after']=NativeServices().verify_normal_profile()
        except (OSError,ValueError,RuntimeError) as error:record['failures'].append({'kind':'NormalRecovery','reason':str(error)[:150]})
        done.set();thread.join(timeout=6)
        if control:
            try:control.firewall.close()
            except (OSError,RuntimeError,subprocess.SubprocessError) as error:record['failures'].append({'kind':'ObserverClose','reason':type(error).__name__})
        save()
        if operation=='qualify' and record.get('qualification_complete') and not record['failures']:
            qualified_receipt['report_sha256']=hashlib.sha256(report.read_bytes()).hexdigest()
            atomic_json(Path('/var/lib/mani-vmlab-setup/workspace-qualified.json'),qualified_receipt)
        print('Sanitized workspace evidence: '+str(report),flush=True)
    raise SystemExit(2 if record['failures'] else 0)


if __name__=='__main__':main()
