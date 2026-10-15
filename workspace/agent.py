"""One bounded model proposal per turn; approvals remain authenticated UI actions.

Only OpenAI function-call deltas enter this adapter. Ordinary model prose, tool
observations and uploaded content never enter the approval or policy APIs.
"""
import copy
import hashlib
import json

from workspace.actions import Actions, MODEL_FUNCTIONS, parse_model_tool
from workspace.catalog import identifier
from workspace.conversations import Conversations
from workspace.permissions import canonical, digest

MAX_TOOL_BYTES = 32768
MAX_OBSERVATION_BYTES = 12000
MAX_HISTORY_BYTES = 24000
MAX_HISTORY_ITEMS = 4
MAX_RUN_SECONDS = 360


def branch(kind, properties):
    return {'type':'object', 'properties':{'type':{'const':kind}, **properties},
            'required':['type', *properties], 'additionalProperties':False}


STRING = {'type':'string'}
TOOL_SPEC = {'type':'function', 'function':{
    'name':'hermes_action',
    'description':'Propose one supported action in the selected Hermes workspace. The server enforces permissions and may require a human approval. Never claim an action ran before its verified result.',
    'parameters':{'type':'object','oneOf':[
        branch('workspace.read', {'path':STRING}),
        branch('workspace.write', {'path':STRING,'text':STRING,
                                  'expected_sha256':{'type':['string','null']}}),
        branch('search.wikipedia', {'query':STRING}),
        branch('guest.submit', {'task_kind':{'type':'string','enum':['chat','python','cpp','diagnostic'],
                                           'description':'Fixed supported checks: python clamps a JSON integer array to 0..100; cpp squares input integers. Chat/diagnostic results need manual review.'},
                               'prompt':STRING,'snapshot_sha256':STRING}),
    ]}}}


def model_tool_specs():
    # A union-only parameter object produced empty arguments in real production
    # calls. Use conventional top-level properties for the pinned backend.
    # Flat function schemas adapt the wire format; domain policy stays tagged.
    result = []
    for variant in TOOL_SPEC['function']['parameters']['oneOf']:
        kind = variant['properties']['type']['const']
        name = next(name for name, action in MODEL_FUNCTIONS.items() if action == kind)
        result.append({'type':'function','function':{
            'name':name,
            'description':kind + '. ' + TOOL_SPEC['function']['description'],
            'parameters':{'type':'object',
                          'properties':{key:value for key,value in variant['properties'].items() if key != 'type'},
                          'required':[key for key in variant['required'] if key != 'type'],
                          'additionalProperties':False}}})
    return result


class ToolCalls:
    """Collect strict streamed fragments without interpreting partial JSON."""
    def __init__(self):
        self.call_id = ''
        self.name = ''
        self.arguments = ''
        self.bytes = 0
        self.seen = False

    def add(self, fragments):
        if type(fragments) is not list:
            raise ValueError('tool_call_fragments_must_be_a_list')
        for fragment in fragments:
            if type(fragment) is not dict or not set(fragment) <= {'index','id','type','function'}:
                raise ValueError('unknown_tool_call_delta_fields')
            if type(fragment.get('index')) is not int or fragment['index'] != 0:
                raise ValueError('one_model_action_per_turn')
            if fragment.get('type', 'function') not in ('function', None):
                raise ValueError('unsupported_tool_call_type')
            if 'id' in fragment and fragment['id'] is not None:
                if type(fragment['id']) is not str or not fragment['id'] or len(fragment['id']) > 128:
                    raise ValueError('invalid_tool_call_id')
                if self.call_id and self.call_id != fragment['id']:
                    raise ValueError('one_model_action_per_turn')
                self.call_id = fragment['id']
            function = fragment.get('function', {})
            if function is None:
                function = {}
            if type(function) is not dict or not set(function) <= {'name','arguments'}:
                raise ValueError('unknown_tool_function_delta_fields')
            for key in ('name','arguments'):
                value = function.get(key)
                if value is None:
                    continue
                if type(value) is not str:
                    raise ValueError('tool_fragments_must_be_strings')
                if key == 'name':
                    self.name += value
                    if len(self.name) > 128:
                        raise ValueError('tool_function_name_limit')
                else:
                    self.arguments += value
            self.bytes += len(canonical(fragment).encode())
            if self.bytes > MAX_TOOL_BYTES or len(self.arguments.encode()) > MAX_TOOL_BYTES:
                raise ValueError('model_tool_fragment_limit_32_KiB')
            self.seen = True

    def finish(self):
        if not self.seen:
            return None
        if not self.call_id or self.name not in ('hermes_action',*MODEL_FUNCTIONS):
            raise ValueError('incomplete_or_unsupported_model_tool')
        call = {'id':self.call_id,'type':'function','function':{
            'name':self.name,'arguments':self.arguments}}
        parse_model_tool(call)
        return call

    def schema_summary(self):
        """Expose structural rejection diagnostics without model/file contents."""
        try:
            value = json.loads(self.arguments)
        except ValueError:
            return {'shape':'invalid_json'}
        if type(value) is not dict:
            return {'shape':type(value).__name__}
        from workspace.actions import ACTION_FIELDS
        known = set().union(*ACTION_FIELDS.values())
        kind = value.get('type')
        return {'shape':'object',
                'action_type':kind if type(kind) is str and kind in ACTION_FIELDS else 'missing_or_unsupported',
                'known_argument_types':{key:type(item).__name__ for key,item in value.items() if key in known},
                'unknown_argument_count':sum(key not in known for key in value),
                'has_action_wrapper':type(value.get('action')) is dict}


def bounded_text(value, characters):
    return value.encode('utf-8',errors='replace')[:characters].decode('utf-8',errors='ignore') if type(value) is str else ''


def observation(action, result):
    """Keep real observations useful and bounded; no unrestricted file dumps."""
    kind = action['type']
    if kind == 'workspace.read':
        value = {'path':result.get('path'), 'sha256':result.get('sha256'),
                 'bytes':result.get('bytes'), 'text':bounded_text(result.get('text'), 7000)}
        value['truncated'] = len(result.get('text','')) > len(value['text'])
    elif kind == 'workspace.write':
        value = {key:result.get(key) for key in ('path','sha256','bytes','original_host_files_changed')}
    elif kind == 'search.wikipedia':
        value = {'provider':'Wikipedia','query':result.get('query'), 'sources':[
            {key:bounded_text(source.get(key), 800 if key == 'text' else 300)
             for key in ('title','url','text')} for source in result.get('sources', [])[:4]]}
        if result.get('attachment'):
            value['attachment_id'] = result['attachment']['id']
    elif kind == 'guest.submit':
        value = {'job':result.get('job'), 'asynchronous':True,
                 'execution_boundary':result.get('execution_boundary')}
    else:
        raise ValueError('unsupported_model_observation')
    if len(canonical(value).encode()) > MAX_OBSERVATION_BYTES:
        raise ValueError('model_observation_limit')
    return value


class Agent:
    def __init__(self, catalog, actions=None):
        self.c = catalog
        self.actions = actions or Actions(catalog)
        self.clock = self.actions.permissions.clock
        self.store = Conversations(catalog)
        with self.c.lock, self.c.db:
            self.c.db.execute('''CREATE TABLE IF NOT EXISTS agent_actions (
                run TEXT PRIMARY KEY, session TEXT NOT NULL, call_id TEXT NOT NULL,
                call_hash TEXT NOT NULL, action_id TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, observed_state TEXT)''')

    def tools(self, session):
        # Model choice does not select or broaden the conversation's policy.
        if self.actions.permissions.read(session)['mode'] == 'chat_only':
            return []
        return copy.deepcopy(model_tool_specs())

    def _owned_run(self, session, run_id):
        self.c.session_record(session)
        identifier(run_id)
        run = self.store.run(run_id)
        if run['session'] != session:
            raise ValueError('model_action_run_conversation_mismatch')
        if self.clock() - run['created'] > MAX_RUN_SECONDS:
            raise ValueError('model_action_run_time_budget_exceeded')
        if run['state'] in ('cancelling','cancelled','failed'):
            raise ValueError('model_action_run_is_terminal')
        return run

    def _safe(self, item):
        answer = {'action_id':item['id'],'state':item['state'], 'type':item['type']}
        if item['state'] == 'completed':
            answer['observation'] = observation(item['action'],item['result'])
        elif item['state'] == 'pending':
            answer['message'] = 'Approval required in Hermes. No action has run.'
        elif item['state'] == 'unavailable':
            answer['message'] = 'This execution boundary is unavailable. No host fallback exists.'
        elif item['state'] in ('denied','revoked','expired'):
            answer['message'] = 'The action is not permitted. Do not retry it.'
        else:
            answer['message'] = item.get('error') or 'The action did not complete.'
        return answer

    def _record_event(self, row, item):
        if row[7] == item['state']:
            return
        event = {'type':'action','action_id':item['id'],'action_type':item['type'],
                 'state':item['state'], 'label':{
                     'pending':'Action needs approval','allowed':'Action approved',
                     'completed':'Action completed','denied':'Action denied',
                     'unavailable':'Execution unavailable','failed':'Action failed',
                     'revoked':'Action revoked','expired':'Approval expired'}.get(item['state'],'Action status')}
        if item['type'] == 'guest.submit' and item['state'] == 'completed':
            # The ledger completes admission, not the asynchronous guest work.
            # job.read owns execution progress and its final measured result.
            event['label'] = 'Guest task dispatched'
            event['job_state'] = (item.get('result') or {}).get('job', {}).get('state', 'queued')
        # This event describes a real ledger transition, never staged progress.
        self.store._event(row[0],event)
        self.c.db.execute('UPDATE agent_actions SET state=?,observed_state=? WHERE run=?',
                          (item['state'],item['state'],row[0]))

    def finish(self, session, run_id, calls):
        call = calls.finish() if isinstance(calls,ToolCalls) else calls
        if call is None:
            return None
        action = parse_model_tool(call)
        with self.c.lock:
            self._owned_run(session,run_id)
            if not self.tools(session):
                raise PermissionError('chat_only_has_no_model_tools')
            call_hash = digest(call)
            row = self.c.db.execute('SELECT run,session,call_id,call_hash,action_id,state,created,observed_state FROM agent_actions WHERE run=?',(run_id,)).fetchone()
            if row:
                if row[1] != session or row[2] != call['id'] or row[3] != call_hash:
                    raise ValueError('one_model_action_per_turn')
                with self.c.db:
                    self.actions.permissions._expire(session)
                    item = self.actions.permissions._public(self.actions.permissions._get(row[4],session))
            else:
                request_id = hashlib.sha256((run_id+'\0'+call['id']).encode()).hexdigest()[:32]
                item = self.actions.request(session,run_id,request_id,action)
                with self.c.db:
                    self.c.db.execute('INSERT INTO agent_actions VALUES (?,?,?,?,?,?,?,NULL)',
                                      (run_id,session,call['id'],call_hash,item['id'],item['state'],self.clock()))
        # External dispatch must not inherit this adapter's catalog lock.
        # Revocation and the ordinary Cancel action can run during provider or
        # native admission waits; the dispatcher rechecks before publishing.
        if item['state'] == 'allowed':
            item = self.actions.execute(session,item['id'])
        with self.c.lock,self.c.db:
            row = self.c.db.execute('SELECT run,session,call_id,call_hash,action_id,state,created,observed_state FROM agent_actions WHERE run=?',(run_id,)).fetchone()
            self._record_event(row,item)
        return self._safe(item)

    def cancel_run(self, run_id):
        with self.c.lock:
            row=self.c.db.execute('SELECT session,action_id FROM agent_actions WHERE run=?',(run_id,)).fetchone()
        return self.actions.cancel(row[0],row[1]) if row else None

    def history(self, session):
        """Return completed, server-held observations as inert data, never prompts.

        Chat must mark these observations as untrusted tool data. Pending action
        arguments/diffs are intentionally absent. Reading history never executes
        or approves an action, and never polls or starts a native guest.
        """
        self.c.session_record(session)
        result = []
        size = 0
        with self.c.lock, self.c.db:
            rows = self.c.db.execute('SELECT run,session,call_id,call_hash,action_id,state,created,observed_state FROM agent_actions WHERE session=? ORDER BY created DESC LIMIT 16',(session,)).fetchall()
            for row in rows:
                item = self.actions.permissions._public(self.actions.permissions._get(row[4],session))
                self._record_event(row,item)
                if item['state'] != 'completed':
                    continue
                value = self._safe(item)
                value['run_id'] = row[0]
                if item['type'] == 'guest.submit':
                    # job.read owns native polling; include only the locally
                    # persisted receipt, never infer success from queueing.
                    job = value['observation'].get('job',{})
                    local = self.c.db.execute('SELECT state,record FROM jobs WHERE id=? AND session=?',(job.get('id'),session)).fetchone()
                    if local:
                        record = json.loads(local[1])
                        value['observation']['job'] = {'id':job.get('id'),'state':local[0]}
                        if local[0] == 'review_ready':
                            value['observation']['answer'] = bounded_text(record.get('answer'),4000)
                            value['observation']['validation_passed'] = record.get('validation',{}).get('passed') is True
                bytes_needed = len(canonical(value).encode())
                if size + bytes_needed > MAX_HISTORY_BYTES or len(result) >= MAX_HISTORY_ITEMS:
                    break
                size += bytes_needed
                result.append(value)
        return list(reversed(result))
