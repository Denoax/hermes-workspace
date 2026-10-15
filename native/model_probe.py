#!/usr/bin/python3
"""Outside real-compute cancellation and selected-window recovery probes."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
sys.dont_write_bytecode = True
import threading
import time
import uuid

SELF=Path('/usr/local/lib/mani-vmlab-setup/model_probe.py')


def processing_log_after(raw,started):
    if len(raw)>65536:raise ValueError('bounded_processing_evidence_limit')
    return any(int(row.get('__MONOTONIC_TIMESTAMP',0))>=int(started*1000000)
        for row in (json.loads(line) for line in raw.splitlines()))


def main():
    if os.geteuid()!=0 or Path(__file__).absolute()!=SELF:
        raise SystemExit('fixed_outside_model_probe_only')
    sys.path.insert(0,'/usr/local/lib/mani-vmlab')
    import supervisor,backend,window
    supervisor.protected(SELF)
    supervisor.protected(SELF.parent)
    supervisor.initialize_imports()
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=('cancel','window_owner_crash','diagnose'))
    operation=parser.parse_args().operation
    if operation=='diagnose':
        raw=subprocess.check_output(['/usr/bin/journalctl','-u',backend.UNIT,'-n','80','--no-pager'],timeout=10)
        if len(raw)>65536:raise ValueError('bounded_backend_log_limit')
        p=Path('/var/lib/mani-vmlab-setup/backend-log.private.txt');p.write_bytes(raw);p.chmod(0o600)
        print(raw.decode(errors='replace')[-6000:])
        return
    if operation=='window_owner_crash':
        if not window.active():raise RuntimeError('selected_window_required')
        pid=int(subprocess.check_output(['/usr/bin/systemctl','show',window.SERVICE,'-p','MainPID','--value'],timeout=5))
        descriptor=os.pidfd_open(pid)
        try:
            if b'inference_window.py\0guard' not in Path(f'/proc/{pid}/cmdline').read_bytes():
                raise RuntimeError('fixed_window_owner_identity_required')
            signal.pidfd_send_signal(descriptor,signal.SIGKILL)
        finally:
            os.close(descriptor)
        started=time.monotonic()
        while time.monotonic()-started<210 and window.state().get('status') not in ('closed','restore_failed'):
            time.sleep(0.25)
        record=window.state()
        print(json.dumps({'owner_crash_injected':True,'outside_observer':True,'recovery_wall_seconds':time.monotonic()-started,
            'restored':record.get('restored_health') is True,'configuration_hashes_equal':record.get('configuration_hashes_equal'),
            'restored_PID':record.get('restored_PID')}))
        if record.get('restored_health') is not True:raise SystemExit(2)
        return
    control=supervisor.Supervisor()
    run_id=control.active_run()
    if not run_id:raise RuntimeError('qualified_live_fleet_required')
    proof=control.prepare_model(run_id,'normal')
    if proof['status']!='ok':raise RuntimeError('real_backend_preparation_failed:'+json.dumps(proof))
    from lab.relay import Relay
    pid=backend.resources()['backend_PID']
    descriptor=os.pidfd_open(pid)
    outside=Path('/proc/self/cgroup').read_text()!=Path(f'/proc/{pid}/cgroup').read_text()
    done=threading.Event();processing=[]
    def observe():
        while not done.wait(0.025):
            try:
                processing.append(any(slot.get('is_processing') is True for slot in backend.get('/slots')))
            except (OSError,RuntimeError,ValueError):
                pass
    thread=threading.Thread(target=observe,daemon=True);thread.start()
    cpu_before=int(subprocess.check_output(['/usr/bin/systemctl','show',backend.UNIT,'-p','CPUUsageNSec','--value'],timeout=5))
    relay=Relay(control.store,run_id,backend.ALIAS,18082,job_seconds=2,
        connection_factory=lambda seconds:backend.UnixHTTP(timeout=seconds),cancel_backend=backend.stop)
    started=time.monotonic();outcome=None
    try:
        relay.infer(json.dumps({'model':backend.ALIAS,'messages':[{'role':'user','content':
            'Write a detailed 1500-word fictional story about synthetic characters in an imaginary village. Continue to the full requested length.'}],
            'max_tokens':1024}).encode(),control.store.token(run_id),uuid.uuid4().hex)
    except (OSError,RuntimeError,ValueError) as error:
        outcome=type(error).__name__
    finally:
        done.set();thread.join(timeout=1)
    exited=bool(select.select([descriptor],[],[],10)[0]);os.close(descriptor)
    cpu_after=int(subprocess.check_output(['/usr/bin/systemctl','show',backend.UNIT,'-p','CPUUsageNSec','--value'],timeout=5))
    # A busy model scheduler may delay /slots until after the short deadline.
    # Its journal is collected outside the workload and fenced by boot, PID and
    # monotonic request start; cgroup CPU accounting corroborates execution.
    raw=subprocess.check_output(['/usr/bin/journalctl','--boot','--no-pager','--output=json','--lines=32',
        '_PID='+str(pid),'_SYSTEMD_UNIT='+backend.UNIT,'--grep=launch_slot_.*processing task'],timeout=5)
    journal_started=processing_log_after(raw,started)
    processing_observed=any(processing) or (journal_started and cpu_after>cpu_before)
    evidence={'outside_workload_cgroup':outside,'actual_backend_processing_observed':processing_observed,
        'processing_observation':{'slots_processing':any(processing),'PID_and_boot_fenced_processing_log':journal_started,
                                  'cgroup_CPU_delta_nanoseconds':cpu_after-cpu_before,'decoding_tokens_observed':False},
        'backend_compute_terminated':exited,'deadline_seconds':2,'wall_seconds':time.monotonic()-started,
        'outcome':outcome,'relay_events':relay.events,'loaded':proof['loaded'],'backend_confinement':proof['proof']}
    p=Path('/var/lib/mani-vmlab-setup/actual-compute-cancellation.json');p.write_text(json.dumps(evidence));p.chmod(0o600)
    print(json.dumps(evidence))
    if not outside or not processing_observed or not exited:raise SystemExit(2)


if __name__=='__main__':
    main()
