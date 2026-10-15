#!/usr/bin/python3
"""Fixed trusted smoke orchestration. Hermes and model parsing remain nonroot.

No supplied executable, path, prompt or command is accepted. Answers are JSON
data for the outside grader, never host code. The independent window/VM services
own deadline recovery if this helper or its native terminal disappears.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
sys.dont_write_bytecode=True
import threading
import time

SELF=Path('/usr/local/lib/mani-vmlab-setup/run_smoke.py')
KEYS=Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1/bench/answer_keys.json')
KEY_SHA='07af8fe07c06305bbdd8c61852d41276f3c6fba744ff9f56f03999e14acf9369'
PUBLIC=Path('/var/lib/mani-vmlab-review')


def strict_equal(actual,expected):
    if type(actual)!=type(expected):return False
    if isinstance(expected,dict):return set(actual)==set(expected) and all(strict_equal(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list):return len(actual)==len(expected) and all(strict_equal(a,b) for a,b in zip(actual,expected))
    return actual==expected


def retry_deadline(previous,boot_id,now,fresh_window=False):
    if previous.get('status')=='restore_failed':raise RuntimeError('normal_recovery_unconfirmed')
    if fresh_window:return None
    if previous.get('status')=='closed' and previous.get('boot_id')==boot_id and 'deadline' in previous:
        if previous['deadline']<=now:raise RuntimeError('chosen_window_expired_select_new_window')
        return previous['deadline']
    return None


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:
        raise SystemExit('Use the installed protected fixed smoke helper.')
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=('run','run-new-window'))
    operation=parser.parse_args().operation
    sys.path.insert(0,'/usr/local/lib/mani-vmlab')
    import supervisor,window
    from lab.state import atomic_json
    from starter.json_limits import bounded_json
    supervisor.protected(SELF);supervisor.protected(SELF.parent);supervisor.initialize_imports()
    descriptor=os.open(KEYS,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>65536:raise ValueError('frozen_answer_inventory_required')
        raw=source.read(65537)
    if hashlib.sha256(raw).hexdigest()!=KEY_SHA:raise ValueError('outside_answer_inventory_changed')
    answers=bounded_json(raw,max_bytes=65536)['answers']
    PUBLIC.mkdir(mode=0o755,exist_ok=True);supervisor.protected(PUBLIC)
    report=PUBLIC/('smoke-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'.json')
    record={'evidence_kind':'trusted_native_control_receipt','smoke':[],'matrix':[],
            'source_pack_sha256':json.loads(Path('/etc/mani-vmlab/config.json').read_text())['source_pack_sha256'],
            'normal_configuration_changed':False,'toolsets':[],'failures':[]}
    control=supervisor.Supervisor();done=threading.Event();owner={'run':None}
    def save():
        atomic_json(report,record);report.chmod(0o644)
    def heartbeat():
        ticks=0
        while not done.wait(5):
            try:
                window.beat()
                if owner['run']:control.store.heartbeat(owner['run'])
                ticks+=1
                if ticks%2==0:
                    print('Lab lease healthy; current phase: '+record.get('phase','setup'),flush=True)
            except (OSError,RuntimeError,ValueError):return
    def provision():
        record['phase']='booting and qualifying fresh VMs (normally about 45 seconds)'
        save()
        before={p.name for p in control.store.root.iterdir() if p.is_dir()}
        try:
            result=control.provision();record.setdefault('provisioning',[]).append(result)
        finally:
            created=[p.name for p in control.store.root.iterdir() if p.is_dir() and p.name not in before]
            if len(created)==1:owner['run']=created[0]
        if result['status']!='ok':raise RuntimeError('owned_VM_provision_failed')
        owner['run']=result['run_id']
        result=control.qualify(owner['run']);record.setdefault('qualification',[]).append(result)
        save()
        if result['status']!='ok':raise RuntimeError('fresh_VM_qualification_failed')
    def teardown():
        if owner['run']:
            stop=control.stop(owner['run']);clean=control.cleanup(owner['run'])
            record.setdefault('cleanup',[]).append({'stop':stop,'cleanup':clean})
            if stop['status']!='ok' or clean['status']!='ok':raise RuntimeError('owned_cleanup_unconfirmed')
            owner['run']=None
    def trials(label,cases,arms):
        probes={}
        for arm in arms:
            prepared=control.prepare_model(owner['run'],arm);record.setdefault('backend_preparation',[]).append(prepared)
            if prepared['status']!='ok':raise RuntimeError('pinned_backend_not_qualified')
            probes[arm]=prepared['proof']['effective_tokenizer_probe']
            if len(probes)==2 and probes['normal']!=probes['abliterated']:
                raise RuntimeError('effective_tokenizer_difference')
            for case in cases:
                response=control.run_case(owner['run'],case,arm)
                row={'case_id':case,'arm':arm,**response,'passed':None,'category':'unscored'}
                if response['status']=='ok':
                    try:
                        actual=bounded_json(response['answer'].encode(),max_bytes=32768)
                        row['passed']=strict_equal(actual,answers[case]);row['category']='correct' if row['passed'] else 'incorrect'
                    except (ValueError,UnicodeError,TypeError):row.update(passed=False,category='parse_error')
                record[label].append(row);save()
                print(json.dumps({'stage':label,'case_id':case,'arm':arm,'status':response['status'],'passed':row['passed']}),flush=True)
    save()
    opened=False;thread=None
    previous=window.state()
    try:
        remaining_deadline=retry_deadline(previous,Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            time.monotonic(),fresh_window=operation=='run-new-window')
        record['window_selection']=operation
        window.command(['/usr/bin/systemctl','start','mani-vmlab-supervisor.service'])
        if control.active_run():raise RuntimeError('preserve_existing_active_lab_run')
        for directory in control.store.root.iterdir():
            if directory.is_dir():
                recovered=control.cleanup(directory.name)
                if recovered['status']!='ok':raise RuntimeError('previous_registered_cleanup_incomplete')
        record['phase']='opening bounded inference window'
        window.command(['/usr/bin/systemctl','start',window.SERVICE],timeout=240)
        if remaining_deadline is not None:
            window.mutate(lambda r:r.update(deadline=min(r['deadline'],remaining_deadline)))
        opened=window.active()
        if not opened:raise RuntimeError('bounded_window_not_active')
        print('Selected 30-minute inference window opened.',flush=True)
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        provision()
        record['phase']='loading normal model for real compute cancellation'
        save()
        probe=subprocess.run(['/usr/bin/python3','-I',str(SELF.with_name('model_probe.py')),'cancel'],
                             capture_output=True,text=True,timeout=360)
        record['compute_cancellation']=bounded_json(probe.stdout.encode(),max_bytes=65536) if probe.stdout else {'exit':probe.returncode}
        if probe.returncode:
            private=Path('/var/lib/mani-vmlab-setup/cancellation-failure.private.txt')
            private.write_text(probe.stderr);private.chmod(0o600)
        save()
        if probe.returncode:raise RuntimeError('actual_compute_stop_not_proven')
        print('Actual compute cancellation passed.',flush=True)
        teardown();provision()
        record['phase']='paired smoke: one model at a time'
        trials('smoke',['B01','B04','B08'],('normal','abliterated'));teardown()
        if len(record['smoke'])==6 and all(r['passed'] is True for r in record['smoke']):
            # Fresh fleets must establish the normal Hermes routing gate first.
            # Record this fixed arm order; it is not counterbalanced evidence.
            provision();trials('matrix',[f'B{i:02}' for i in range(1,13)],('normal','abliterated'));teardown()
    except KeyboardInterrupt:
        record['failures'].append({'kind':'KeyboardInterrupt','reason':'native_terminal_interrupted'})
        print('Native terminal interrupted; stopping owned workloads and restoring normal Qwen.',flush=True)
    except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as error:
        record['failures'].append({'kind':type(error).__name__,'reason':str(error)[:2000]})
        print('Stopped at an evidence gate: '+str(error),flush=True)
    finally:
        try:
            teardown()
        except (OSError,RuntimeError,ValueError) as error:
            record['failures'].append({'cleanup_error':str(error)})
        if opened and window.active():
            probe=subprocess.run(['/usr/bin/python3','-I',str(SELF.with_name('model_probe.py')),'window_owner_crash'],
                                 capture_output=True,text=True,timeout=240)
            record['outside_window_owner_crash_recovery']=bounded_json(probe.stdout.encode(),max_bytes=65536) if probe.stdout else {'exit':probe.returncode}
        done.set()
        if thread:thread.join(timeout=6)
        if window.state().get('status') in ('opening','active','restoring'):
            window.command(['/usr/bin/systemctl','stop',window.SERVICE],timeout=240)
        record['window_restoration']=window.state();save()
        print('Sanitized actual evidence: '+str(report),flush=True)
    if len(record['smoke'])!=6 or not all(r['status']=='ok' for r in record['smoke']) or record['failures']:
        raise SystemExit(2)


if __name__=='__main__':main()
