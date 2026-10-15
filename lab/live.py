"""Unprivileged orchestration of qualified fixed native operations."""
import json
from pathlib import Path
import threading
from lab.execution import execute_matrix
from lab.report import write_results


def paired(client, case_ids, directory, arms=('normal','abliterated'), run_id=None):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    if not client.call('status')['observed_facts'].get('inference_window_active'):
        raise RuntimeError('chosen_native_inference_window_required')
    done=threading.Event();owner={'run_id':run_id};errors=[];rows=[];operations=[]
    def heartbeat():
        while not done.wait(5):
            try:
                client.call('window_heartbeat')
                if owner['run_id']:client.call('heartbeat',run_id=owner['run_id'])
            except (OSError,ValueError,RuntimeError) as error:
                errors.append(str(error));done.set()
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        if not owner['run_id']:
            provision=client.call('provision');operations.append(provision)
            if provision['status']!='ok':raise RuntimeError('native_provision_failed')
            owner['run_id']=provision['run_id']
        qualified=client.call('qualify',run_id=owner['run_id']);operations.append(qualified)
        if qualified['status']!='ok':raise RuntimeError('fresh_VM_qualification_failed')
        probes={}
        for arm in arms:
            if errors:raise RuntimeError('operator_heartbeat_failed:'+errors[0])
            prepared=client.call('prepare_model',run_id=owner['run_id'],arm=arm);operations.append(prepared)
            if prepared['status']!='ok':raise RuntimeError('pinned_backend_not_qualified:'+json.dumps(prepared))
            probes[arm]=prepared['proof']['effective_tokenizer_probe']
            if len(probes)==2 and probes['normal']!=probes['abliterated']:
                raise RuntimeError('effective_runtime_tokenizer_differs')
            arm_rows=execute_matrix(client,owner['run_id'],case_ids,arms=(arm,),cleanup=False)
            if len(arms)>1:
                for row in arm_rows:
                    if row['status']=='completed':row['execution_kind']='paired_guest_Hermes'
            rows.extend(arm_rows)
            write_results(directory,rows)
        return rows
    finally:
        if owner['run_id']:
            operations.append(client.call('stop',run_id=owner['run_id']))
            operations.append(client.call('cleanup',run_id=owner['run_id']))
        done.set();thread.join(timeout=6)
        (directory/'native_operations.json').write_text(json.dumps(operations,indent=2)+'\n')
        if rows:write_results(directory,rows)
