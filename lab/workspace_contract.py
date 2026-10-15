"""Versioned bounded data contract shared by UI, router, root and guest tools."""
import hashlib
import json
import re
import math
from pathlib import PurePosixPath

VERSION=1
MAX_SNAPSHOT=32768
IDENTIFIER=re.compile(r'[0-9a-f]{32}')


def canonical_id(value):
    if type(value) is not str or not IDENTIFIER.fullmatch(value):raise ValueError('invalid_workspace_identifier')
    return value


def relative(name):
    if type(name) is not str or not name or len(name.encode())>256 or '\\' in name or any(ord(c)<32 or ord(c)==127 for c in name):raise ValueError('invalid_workspace_path')
    p=PurePosixPath(name)
    if p.is_absolute() or any(x in ('','..','.') or x.startswith('.') for x in name.split('/')):
        raise ValueError('invalid_workspace_path')
    if p.name in ('answer_keys.json','grading.py','scoring.py','credentials.json'):raise ValueError('authority_file_denied')
    return name


def snapshot_files(files):
    if type(files) is not list or len(files)>16:raise ValueError('bounded_snapshot_required')
    seen=set();total=0
    for item in files:
        if type(item) is not dict or set(item)!={'path','text','sha256','bytes'}:raise ValueError('invalid_snapshot_file')
        path=relative(item['path'])
        if path in seen:raise ValueError('duplicate_snapshot_path')
        seen.add(path)
        if type(item['text']) is not str or '\0' in item['text']:raise ValueError('text_snapshot_required')
        data=item['text'].encode();total+=len(data)
        if type(item['bytes']) is not int or item['bytes']!=len(data) or hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise ValueError('snapshot_hash_or_size_mismatch')
    if total>MAX_SNAPSHOT:raise ValueError('snapshot_size_limit')
    return files


def submit(data):
    if type(data) is not dict or set(data)!={'version','project_id','session_id','job_id','arm','prompt','task_kind','authority','snapshot','snapshot_sha256'}:
        raise ValueError('fixed_workspace_submit_contract_required')
    if type(data['version']) is not int or data['version']!=VERSION:raise ValueError('unsupported_workspace_version')
    for name in ['project_id','session_id','job_id']:canonical_id(data[name])
    if data['arm'] not in ('normal','abliterated') or data['task_kind'] not in ('chat','python','cpp','diagnostic'):
        raise ValueError('unknown_model_or_task_profile')
    if data['authority'] not in ('read','candidate') or (data['task_kind'] in ('python','cpp','diagnostic') and data['authority']!='candidate'):
        raise ValueError('unsupported_authority_intersection')
    if type(data['prompt']) is not str or not 1<=len(data['prompt'].encode())<=8192:raise ValueError('prompt_limit')
    snapshot_files(data['snapshot'])
    digest=hashlib.sha256(json.dumps(data['snapshot'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=data['snapshot_sha256']:raise ValueError('snapshot_digest_mismatch')
    return data


def guest_result(data,authority):
    required={'answer','files','tool_events','Hermes_revision','tool_profile','agent_uid'}
    if type(data) is not dict or set(data)!=required:raise ValueError('fixed_guest_result_required')
    if type(data['answer']) is not str or len(data['answer'].encode())>32768:raise ValueError('guest_answer_limit')
    snapshot_files(data['files'])
    if data['tool_profile']!='guest_scoped_v1' or type(data['agent_uid']) is not int or data['agent_uid']!=1000:
        raise ValueError('guest_profile_or_identity_mismatch')
    if type(data['Hermes_revision']) is not str or not re.fullmatch('[0-9a-f]{40}',data['Hermes_revision']):raise ValueError('guest_revision_required')
    events=data['tool_events']
    if type(events) is not list or len(events)>12:raise ValueError('guest_tool_event_limit')
    allowed={'lab_read_file'} if authority=='read' else TOOL_NAMES
    for event in events:
        if type(event) is not dict or set(event)!={'tool','wall_seconds','result'} or event['tool'] not in allowed or type(event['result']) is not dict:raise ValueError('guest_tool_event_schema')
        duration=event['wall_seconds']
        if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<=duration<=360:raise ValueError('guest_tool_event_duration')
    return data


def tool(name,description,properties,required):
    return {'type':'function','function':{'name':name,'description':description,
        'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}


TOOLS=[tool('lab_read_file','Read a UTF-8 file in this disposable job workspace.',{'path':{'type':'string'}},['path']),
       tool('lab_write_file','Write a UTF-8 file in this disposable job workspace.',{'path':{'type':'string'},'text':{'type':'string'}},['path','text']),
       tool('lab_run','Run program.py or compile/run solution.cpp as the separate candidate user in this VM.',
            {'language':{'type':'string','enum':['python','cpp']},'stdin':{'type':'string'}},['language','stdin'])]
TOOL_NAMES={t['function']['name'] for t in TOOLS}
TOOLS.sort(key=lambda item:item['function']['name'])
READ_TOOLS=[item for item in TOOLS if item['function']['name']=='lab_read_file']


def tool_call(call,allowed=TOOL_NAMES):
    if type(call) is not dict or set(call)!={'id','type','function'} or call['type']!='function':raise ValueError('invalid_tool_call')
    if type(call['id']) is not str or not 1<=len(call['id'])<=128:raise ValueError('tool_call_id')
    function=call['function']
    if type(function) is not dict or set(function)!={'name','arguments'} or type(function['name']) is not str or function['name'] not in allowed:
        raise ValueError('unqualified_tool_name')
    if type(function['arguments']) is not str or len(function['arguments'].encode())>20000:raise ValueError('tool_arguments_limit')
    return call
