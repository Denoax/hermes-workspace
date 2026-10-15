"""Outside VM job ledger and bounded queue. Inputs are data, never host code."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import select
import subprocess
import threading
import time

DATA=Path('/home/mani-vmlab-data/workspace-jobs')
TERMINAL={'review_ready','cancelled','failed','blocked'}


class Jobs:
    def __init__(self,control):
        self.control=control;self.lock=threading.RLock();self.queue=[];self.worker=None;self.cancelled=set();self.owners={}
        DATA.mkdir(mode=0o700,exist_ok=True)
        self.recovery_ready=True
        for path in DATA.glob('*.json'):
            record=self.read(path.stem)
            if record['state'] in TERMINAL:continue
            cleanup=control.cleanup(record['run_id']) if record.get('run_id') else {'status':'ok'}
            if cleanup['status']!='ok':self.recovery_ready=False
            record.update(state='cancelled' if cleanup['status']=='ok' else 'failed',cleanup=cleanup,
                          reason='outside_owner_lost_or_window_closed_before_reconnect')
            record['events'].append({'sequence':len(record['events'])+1,'state':record['state'],
                'detail':'Outside recovery reconciled this interrupted job; no automatic retry.', 'monotonic_seconds':time.monotonic()})
            self.save(record)

    def path(self,job):
        from lab.workspace_contract import canonical_id
        return DATA/(canonical_id(job)+'.json')

    def read(self,job):
        from supervisor import protected
        path=self.path(job);protected(path)
        record=json.loads(path.read_text())
        if record['operator_uid']!=1000:raise PermissionError('job_owner_mismatch')
        return record

    def save(self,record):
        from lab.state import atomic_json
        atomic_json(self.path(record['id']),record)

    def event(self,job,state,detail):
        with self.lock:
            record=self.read(job)
            if record['state'] in TERMINAL:raise RuntimeError('terminal_job_cannot_transition')
            record['state']=state
            record['events'].append({'sequence':len(record['events'])+1,'state':state,'detail':detail,'monotonic_seconds':time.monotonic()})
            self.save(record)
        return record

    def submit(self,payload,owner_pid):
        from lab.workspace_contract import submit
        import window
        payload=submit(payload)
        from lab.process import identity,open_owned
        owner=identity(owner_pid)
        descriptor=open_owned(owner)
        if descriptor is None:raise RuntimeError('live_outside_owner_required')
        with self.lock:
            try:
                if not self.recovery_ready:raise RuntimeError('registered_recovery_incomplete')
                if self.path(payload['job_id']).exists():raise ValueError('duplicate_workspace_job')
                if not window.active():raise RuntimeError('explicit_live_window_required')
                import backend
                if not backend.artifacts_current():raise RuntimeError('verified_pinned_artifacts_required')
                reserved=(len(self.owners)+1)*480
                if window.state()['deadline']-time.monotonic()<reserved:raise RuntimeError('job_cannot_fit_remaining_window')
                if len(self.queue)>=2:raise RuntimeError('bounded_queue_full')
            except BaseException:os.close(descriptor);raise
            record={'id':payload['job_id'],'project_id':payload['project_id'],'session_id':payload['session_id'],
                    'operator_uid':1000,'arm':payload['arm'],'state':'queued','events':[],
                    'snapshot_sha256':payload['snapshot_sha256'],'payload':payload,'profile':'guest_scoped_v1','run_id':None,'outside_owner':owner,
                    'submitted_monotonic_seconds':time.monotonic(),
                    'deadline':min(window.state()['deadline'],time.monotonic()+480)}
            try:self.save(record)
            except BaseException:os.close(descriptor);raise
            self.owners[record['id']]=descriptor
            self.queue.append(record['id'])
            if self.worker is None or not self.worker.is_alive():
                self.worker=threading.Thread(target=self.work,daemon=True);self.worker.start()
            return {'status':'ok','job_id':record['id'],'state':'queued'}

    def check_owners(self):
        with self.lock:
            for job,descriptor in list(self.owners.items()):
                if self.read(job)['state'] in TERMINAL:
                    os.close(descriptor);del self.owners[job]
                elif select.select([descriptor],[],[],0)[0] or time.monotonic()>=self.read(job)['deadline']:self.cancel(job)

    def public(self,job):
        record=self.read(job)
        return {'status':'ok',**{key:value for key,value in record.items() if key!='payload'}}

    def cancel(self,job):
        with self.lock:
            record=self.read(job)
            if record['state'] in TERMINAL:return self.public(job)
            self.cancelled.add(job)
            if record['state']=='queued':self.event(job,'cancelled','Cancelled before VM admission.')
            else:
                self.event(job,'cancelling','Revoking guest and backend work outside the UI.')
                if record['run_id']:self.control.store.revoke(record['run_id'],'workspace_user_cancel')
        return {'status':'ok','state':self.read(job)['state'],'job_id':job}

    def work(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.worker=None
                    return
                job=self.queue.pop(0)
            if self.read(job)['state'] in TERMINAL:continue
            self.execute(job)

    def execute(self,job):
        import backend,window
        from lab.relay import Relay
        from lab.workspace_contract import guest_result
        control=self.control;record=self.read(job);payload=record['payload'];run_id=None;beat_stop=threading.Event()
        def beat():
            while not beat_stop.wait(5):
                if run_id:control.store.heartbeat(run_id)
        thread=threading.Thread(target=beat,daemon=True);thread.start()
        outcome=None
        try:
            with self.lock:
                if self.read(job)['state'] in TERMINAL:return
                self.event(job,'starting','Booting fresh worker and independent validation overlays.')
            with control.mutation:
                if control.active_run():raise RuntimeError('existing_owned_fleet_busy')
                def created(value):
                    nonlocal run_id
                    run_id=value
                    control.store.mutate(run_id,lambda m:m.update(deadline=min(m['deadline'],self.read(job)['deadline'])))
                    with self.lock:
                        record=self.read(job);record['run_id']=run_id;self.save(record)
                    if job in self.cancelled:
                        control.store.revoke(run_id,'workspace_user_cancel')
                        raise RuntimeError('cancelled')
                result=control.provision(on_created=created)
                if result['status']!='ok':raise RuntimeError('fresh_fleet_boot_failed')
                run_id=result['run_id']
                with self.lock:
                    record=self.read(job);record['run_id']=run_id;self.save(record)
                control.store.mutate(run_id,lambda m:m.update(workspace_jobs={job:{'state':'starting','profile':'guest_scoped_v1'}}))
                qualified=control.qualify(run_id)
                if qualified['status']!='ok':raise RuntimeError('fresh_fleet_not_qualified')
                facts=control.state()['observed_facts']
                required=['VM_confinement_qualified','network_qualified','VM_watchdog_qualified','guest_Hermes_installed','host_firewall_qualified','inference_window_active']
                if not all(facts.get(key) for key in required):raise RuntimeError('current_outside_qualification_required')
                if job in self.cancelled:raise RuntimeError('cancelled')
                control.store.mutate(run_id,lambda m:m.update(owns_backend=True))
                self.event(job,'starting','Loading the committed '+payload['arm']+' artifact.')
                loaded=backend.start(payload['arm'],valid=lambda:not control.store.mutate(run_id,control.store.active))
                proof=backend.qualify(payload['arm'])
                if not proof['confined']:raise RuntimeError('model_backend_not_confined')
                control.backend_arm=payload['arm']
                control.store.mutate(run_id,lambda m:m.setdefault('backend_qualification',{}).update({payload['arm']:proof}))
                self.event(job,'running','Pinned guest Hermes is working inside worker_a.')
                control.store.mutate(run_id,lambda m:m['workspace_jobs'][job].update(state='running'))
                relay=Relay(control.store,run_id,backend.ALIAS,18082,job_seconds=360,
                    connection_factory=lambda seconds:backend.UnixHTTP(timeout=seconds),cancel_backend=backend.stop,tool_profile=payload['authority'])
                with relay_path(control,run_id,'worker_a',relay):
                    response=control.ssh(run_id,'worker_a','workspace',{'prompt':payload['prompt'],'model':backend.ALIAS,
                        'relay_token':control.store.token(run_id),'files':payload['snapshot'],'authority':payload['authority']})
                if job in self.cancelled:raise RuntimeError('cancelled')
                guest_result(response,payload['authority'])
                if payload['authority']=='read' and sorted(response['files'],key=lambda x:x['path'])!=sorted(payload['snapshot'],key=lambda x:x['path']):raise RuntimeError('read_authority_cannot_export_changes')
                if response['Hermes_revision']!=control.configuration['Hermes_revision'] or response['agent_uid']!=1000:
                    raise RuntimeError('pinned_nonroot_guest_identity_mismatch')
                if not any(event.get('outcome')=='completed' for event in relay.events):raise RuntimeError('actual_local_model_calls_missing')
                control.store.mutate(run_id,lambda m:m.update(Hermes_routing_qualified=True))
                validation={'passed':None,'kind':'manual_chat_review','reason':'No behavioral oracle for ordinary conversation.'}
                if payload['task_kind'] in ('python','cpp'):
                    self.event(job,'validating','Testing exported code in fresh independent worker_b.')
                    control.store.mutate(run_id,lambda m:m['workspace_jobs'][job].update(state='validating'))
                    values=[secrets.randbelow(501)-200 for _ in range(12)]
                    stdin=json.dumps(values) if payload['task_kind']=='python' else ' '.join(map(str,values))
                    result=control.ssh(run_id,'worker_b','validate',{'language':payload['task_kind'],
                        'files':[{'path':x['path'],'text':x['text']} for x in response['files']],'stdin':stdin})
                    expected=[min(100,max(0,x)) for x in values] if payload['task_kind']=='python' else [x*x for x in values]
                    try:
                        actual=json.loads(result['stdout']) if payload['task_kind']=='python' else [int(x) for x in result['stdout'].split()]
                        passed=result['exit']==0 and type(actual) is list and len(actual)==len(expected) and all(type(a) is int and a==b for a,b in zip(actual,expected))
                    except (ValueError,KeyError):passed=False
                    validation={'passed':passed,'kind':'outside_randomized_owned_contract','language':payload['task_kind'],
                        'validator_VM_UUID':control.store.read(run_id)['vm_uuids']['worker_b'],
                        'candidate_uid':result.get('candidate_uid'),'compile_run_exit':result.get('exit'),
                        'inputs_sha256':hashlib.sha256(stdin.encode()).hexdigest(),'sample_size':len(values),
                        'reason':'Passed owned contract' if passed else 'Candidate failed independent owned contract'}
                with self.lock:
                    record=self.read(job);record.update(answer=response['answer'],files=response['files'],tool_events=response['tool_events'],
                        relay_events=list(relay.events),validation=validation,loaded=loaded,backend_proof=proof,
                        source_pack_sha256=control.configuration['source_pack_sha256'],Hermes_revision=response['Hermes_revision'],
                        evidence_kind='actual_guest_Hermes_workspace_job',backend_resources=backend.resources(),
                        model_sha256=json.loads(Path('/usr/local/lib/mani-vmlab-setup/backend-artifacts.lock.json').read_text())['models'][payload['arm']]['sha256']);self.save(record)
                outcome='review_ready'
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            with self.lock:
                record=self.read(job);record['error']=str(error)[:200] if type(error) is RuntimeError else type(error).__name__;self.save(record)
            outcome='cancelled' if job in self.cancelled or not window.active() else 'failed'
        finally:
            if run_id:
                try:
                    stop=control.stop(run_id,'workspace_job_finished');cleanup=control.cleanup(run_id)
                    with self.lock:
                        record=self.read(job);record.update(stop=stop,cleanup=cleanup);self.save(record)
                    if stop['status']!='ok' or cleanup['status']!='ok':
                        outcome='failed';self.recovery_ready=False
                except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                    outcome='failed';self.recovery_ready=False
            beat_stop.set();thread.join(timeout=6)
            with self.lock:
                if self.read(job)['state'] not in TERMINAL:
                    if job in self.cancelled and outcome!='failed':outcome='cancelled'
                    record=self.read(job)
                    record['wall_seconds']=time.monotonic()-record['submitted_monotonic_seconds']
                    record['usage']={key:sum(event.get('usage',{}).get(key,0) for event in record.get('relay_events',[]) if isinstance(event.get('usage'),dict)) for key in ('prompt_tokens','completion_tokens','total_tokens')}
                    self.save(record)
                    self.event(job,outcome or 'failed','Owned workload cleanup finished; inspect the recorded cleanup outcome.')


@contextmanager
def relay_path(control,run_id,vm_id,relay):
    server=relay.server();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    directory=control.store.directory(run_id)
    proxy=f'/usr/bin/python3 -I /usr/local/lib/mani-vmlab/proxy.py {directory}/{vm_id}-control/ssh.sock'
    argv=['/usr/bin/ssh','-F','/dev/null','-T','-N','-o','BatchMode=yes','-o','IdentitiesOnly=yes',
        '-o','StrictHostKeyChecking=yes','-o','ForwardAgent=no','-o','HostKeyAlias=mani-vmlab-'+vm_id,
        '-o','UserKnownHostsFile='+str(directory/(vm_id+'.known_hosts')),'-o','GlobalKnownHostsFile=/dev/null',
        '-o','ExitOnForwardFailure=yes','-o','ProxyCommand='+proxy,'-i',str(directory/(vm_id+'.key')),
        '-R',f'127.0.0.1:18081:127.0.0.1:{server.server_port}','lab@localhost']
    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        time.sleep(.25)
        if process.poll() is not None:raise RuntimeError('owned_worker_relay_tunnel_failed')
        yield
    finally:
        process.terminate()
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        server.shutdown();server.server_close();thread.join(timeout=2)
