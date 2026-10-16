"""Actual-pin chat-only denials on known harmless A; no policy change/inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc
from scripts.probe_v6_geometry import load_case
from scripts.owned_v6_interactions import owned_row
from workspace.server import normal_profile_unchanged


def require(value, code):
    if not value:
        raise RuntimeError(code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owned-case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-production-probe', action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe or os.getuid() == 0:
        parser.error('explicit unprivileged production probe required')
    require(args.owned_case.is_file() and not any(p.is_symlink() for p in (args.owned_case,*args.owned_case.parents))
            and args.owned_case.stat().st_size <= 1024*1024, 'bounded_regular_owned_receipt_required')
    require(not args.output.exists() and not any(p.is_symlink() for p in (args.output,*args.output.parents)), 'new_regular_output_required')
    case = load_case(json.loads(args.owned_case.read_text()))
    sources = ('workspace/server.py','workspace/permissions.py','workspace/actions.py',
               'scripts/probe_v6_permission_denial.py','workspace/ui/dist/app.js','workspace/ui/dist/app.css')
    hashes = lambda: {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    report = {'status':'IN_PROGRESS','scope':'Actual existing pin18791 and protected authenticated RPC; no policy/model/view changes. One denied action is added only to positively owned A.',
              'case_receipt_sha256':hashlib.sha256(args.owned_case.read_bytes()).hexdigest(),
              'source_sha256_before':hashes(),'checks':{},'UI_approval_card_or_physical_microphone':'UNVERIFIED'}
    browser = ProductionPin()
    try:
        report['pin'] = browser.identity
        ready = rpc(browser,'readiness.read',{})
        require(ready['state']=='ready' and ready['control']['socket_uid']==ready['control']['parent_uid']==0, 'protected_production_admission_required')
        a = owned_row(case,'A',rpc(browser,'session.list',{}))
        sid = a['id']; project = a['project']
        before = {name:rpc(browser,name,fields) for name,fields in (
            ('view.read',{}),('draft.read',{'session_id':sid}),('chat.snapshot',{'session_id':sid}),
            ('workspace.files',{'project_id':project}))}
        policy = rpc(browser,'permissions.read',{'session_id':sid})
        require(policy['mode']=='chat_only' and not any(policy['capabilities'].values()) and not policy['grants'], 'existing_chat_only_policy_required')
        row = rpc(browser,'permissions.request',{'session_id':sid,'run_id':None,'request_id':uuid.uuid4().hex,
            'action':{'type':'workspace.write','path':'v6-denied-'+uuid.uuid4().hex+'.txt','text':'Harmless denied review payload.','expected_sha256':None}})
        require(row['state']=='denied', 'new_action_must_already_be_denied_before_dispatch_probe')
        report['checks']['chat_only_action_denied'] = True
        requests = (
            ('denied_action_dispatch','actions.execute',{'session_id':sid,'action_id':row['id']}),
            ('legacy_mutation_denied','workspace.file.write',{'project_id':project,'relative_path':'v6-denied-legacy.txt','text':'Never write.','expected_sha256':None}),
            ('microphone_admission_denied','recording.authorize',{'session_id':sid}))
        expected_errors = {'denied_action_dispatch':'action_not_approved_denied',
                           'legacy_mutation_denied':'scoped_action_required',
                           'microphone_admission_denied':'permission_required_microphone'}
        for label,method,fields in requests:
            try:
                rpc(browser,method,fields)
            except RuntimeError as error:
                require(expected_errors[label] in str(error), 'unexpected_error_is_not_denial_proof')
                report['checks'][label] = {'denied':True,'error_sha256':hashlib.sha256(str(error).encode()).hexdigest()}
            else:
                raise RuntimeError('protected_operation_unexpectedly_succeeded')
        require(rpc(browser,'permissions.read',{'session_id':sid})['mode']=='chat_only', 'policy_changed_during_denial_probe')
        for name,fields in (('view.read',{}),('draft.read',{'session_id':sid}),('chat.snapshot',{'session_id':sid}),('workspace.files',{'project_id':project})):
            require(rpc(browser,name,fields)==before[name], 'review_changed_existing_data')
        report['checks']['view_draft_history_workspace_unchanged'] = True
        report['status'] = 'PASS'
    except Exception as error:
        report.update(status='FAIL',error_category=type(error).__name__,error_sha256=hashlib.sha256(str(error).encode()).hexdigest())
    finally:
        browser.close()
        report['source_sha256_after'] = hashes()
        report['normal_configuration_unchanged'] = normal_profile_unchanged()
        if report['source_sha256_before']!=report['source_sha256_after'] or not report['normal_configuration_unchanged']:
            report['status']='FAIL'
        args.output.write_text(json.dumps(report,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps({'status':report['status'],'checks':len(report['checks'])}))
    if report['status']!='PASS':raise SystemExit(2)


if __name__=='__main__':main()
