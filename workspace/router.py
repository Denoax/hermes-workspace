"""Opt-in Codex router adapter: registered copies only; no host Hermes Lab path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.native_client import NativeClient,public_snapshot
from workspace.catalog import Catalog


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['scout','review','prototype','status'])
    parser.add_argument('--project')
    parser.add_argument('--arm',choices=['normal','abliterated'],default='normal')
    parser.add_argument('--profile',choices=['chat','python','cpp'],default='chat')
    parser.add_argument('--task-file',type=Path)
    args=parser.parse_args(argv)
    if os.geteuid()==0:raise SystemExit('router adapter must remain unprivileged')
    client=NativeClient(timeout=15)
    if args.mode=='status':print(json.dumps(client.call('status') if client.available() else public_snapshot()));return 0
    if not args.project:parser.error('--project must select an existing registered copy')
    if args.mode!='prototype' and args.profile!='chat':parser.error('read modes cannot request code-execution authority')
    prompt=args.task_file.read_text() if args.task_file else sys.stdin.read(8193)
    if not 1<=len(prompt.encode())<=8192:parser.error('task must be bounded UTF-8 input')
    c=Catalog(Path.home()/'HermesLab')
    try:
        snapshot=c.snapshot(args.project);session=c.session(args.project,args.arm);job=uuid.uuid4().hex
        payload={'version':1,'project_id':args.project,'session_id':session['id'],'job_id':job,'arm':args.arm,
                 'prompt':prompt,'task_kind':args.profile,'authority':'candidate' if args.mode=='prototype' else 'read',
                 'snapshot':snapshot['files'],'snapshot_sha256':snapshot['sha256']}
        result=client.call('workspace_submit',version=1,payload=payload)
        if result['status']!='ok':raise RuntimeError('scoped_native_admission_denied')
        record={'id':job,'state':'queued','snapshot':snapshot['files'],'snapshot_sha256':snapshot['sha256'],'router_mode':args.mode}
        with c.lock:c.db.execute('INSERT INTO jobs VALUES (?,?,?,?)',(job,session['id'],'queued',json.dumps(record)));c.db.commit()
        c.message(session['id'],'user',prompt,job)
        print(json.dumps({'job_id':job,'mode':args.mode,'authority':payload['authority'],'source':'native_VM_broker'}),flush=True)
        try:
            deadline=time.monotonic()+500
            while time.monotonic()<deadline:
                current=client.call('workspace_read',version=1,job_id=job)
                if current.get('state') in ('review_ready','cancelled','failed','blocked'):
                    from workspace.jobs import Jobs
                    Jobs(c).read(job)
                    print(json.dumps({key:value for key,value in current.items() if key not in ('files','tool_events','relay_events')}))
                    return 0 if current['state']=='review_ready' else 2
                time.sleep(1)
            client.call('workspace_cancel',version=1,job_id=job)
            raise TimeoutError('router_outside_wait_deadline')
        except KeyboardInterrupt:
            client.call('workspace_cancel',version=1,job_id=job);return 130
    finally:c.db.close()


if __name__=='__main__':raise SystemExit(main())
