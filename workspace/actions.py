"""Fixed, permissioned action dispatcher. No host command execution fallback."""
import difflib
import hashlib
import json
import os
import re

from workspace.catalog import identifier
from workspace.files import Files, MAX_FILE, parts
from workspace.permissions import Permissions, digest

SHA = re.compile(r'[0-9a-f]{64}')
ACTION_FIELDS = {
    'workspace.read': {'type', 'path'},
    'workspace.write': {'type', 'path', 'text', 'expected_sha256'},
    'search.wikipedia': {'type', 'query'},
    'guest.submit': {'type', 'task_kind', 'prompt', 'snapshot_sha256'},
    'host.apply': {'type', 'review_ticket'},
}
MODEL_FUNCTIONS = {
    'workspace_read': 'workspace.read',
    'workspace_write': 'workspace.write',
    'search_wikipedia': 'search.wikipedia',
    'guest_submit': 'guest.submit',
}


def sha(value, nullable=False):
    if value is None and nullable:
        return value
    if type(value) is not str or not SHA.fullmatch(value):
        raise ValueError('sha256_required')
    return value


class Actions:
    def __init__(self, catalog, permissions=None):
        self.c = catalog
        self.permissions = permissions or Permissions(catalog)

    def available(self, session):
        project = self.c.session_record(session)['project'] if session else None
        guest = {'available': False, 'reason': 'A qualified, bounded native Lab window is required; permissions cannot open it.'}
        try:
            from lab.native_client import NativeClient
            client = NativeClient(timeout=2)
            state = client.call('status') if client.available() else {}
            facts = state.get('observed_facts', {})
            required = ('protected_supervisor', 'signed_base_image', 'installed_confinement',
                        'host_firewall_qualified', 'VM_watchdog_qualified',
                        'pinned_model_and_backend_artifacts_current', 'inference_window_active')
            missing = [name for name in required if facts.get(name) is not True]
            if state.get('tool_profile') == 'guest_scoped_v1' and not missing and state.get('remaining_seconds', 0) >= 480:
                guest = {'available': True, 'reason': 'Fixed Python/C++/diagnostic tasks in fresh disposable guests; confinement and network are requalified before execution.'}
            elif missing:
                guest['reason'] = 'Guest execution unavailable: ' + ', '.join(missing) + '. No host shell fallback.'
        except (OSError, ValueError, RuntimeError, PermissionError):
            pass
        return {
            'read': {'available': bool(project), 'reason': None if project else 'Select a project workspace.'},
            'write': {'available': bool(project), 'reason': None if project else 'Select a project workspace.'},
            'guest': guest if project else {'available': False, 'reason': 'Select a project workspace and open a qualified native Lab window.'},
            'search': {'available': True, 'reason': 'Wikipedia only; no arbitrary URLs or network access.'},
            'microphone': {'available': True, 'reason': 'App consent plus browser device permission are both required.'},
            'host_apply': {'available': bool(project), 'reason': 'A separate validated, unexpired original-file diff approval is always required.'},
        }

    def read(self, session):
        return {**self.permissions.read(session), 'available': self.available(session),
                'actions': self.permissions.list(session) if session else []}

    def _snapshot(self, project):
        if not project:
            raise ValueError('selected_workspace_required')
        return self.c.snapshot(project)

    def normalize(self, session, action):
        if type(action) is not dict or type(action.get('type')) is not str or action['type'] not in ACTION_FIELDS or set(action) != ACTION_FIELDS[action['type']]:
            raise ValueError('unsupported_action_schema')
        record = self.c.session_record(session)
        project = record['project']
        kind = action['type']
        if kind.startswith('workspace.'):
            if not project:
                raise ValueError('selected_workspace_required')
            path = '/'.join(parts(action['path']))
            fs = self.c.files(project)
            try:
                try:
                    before = fs.read(path)
                except FileNotFoundError:
                    if kind == 'workspace.read':
                        raise
                    before = None
            finally:
                fs.close()
            base = before['sha256'] if before else None
            if kind == 'workspace.read':
                if len(json.dumps(before).encode()) > 64000:
                    raise ValueError('action_read_result_limit_64_KiB')
                return {'type': kind, 'path': path, 'base_sha256': base}, {'path': path}
            text = action['text']
            if type(text) is not str or '\0' in text or len(text.encode()) > MAX_FILE:
                raise ValueError('bounded_UTF8_text_required')
            if sha(action['expected_sha256'], nullable=True) != base:
                raise ValueError('file_drift')
            diff = ''.join(difflib.unified_diff((before['text'] if before else '').splitlines(keepends=True), text.splitlines(keepends=True), fromfile=path, tofile=path))
            if len(diff.encode()) > 65536:
                raise ValueError('review_diff_limit_64_KiB')
            return {'type': kind, 'path': path, 'text': text, 'base_sha256': base,
                    'candidate_sha256': hashlib.sha256(text.encode()).hexdigest(), 'diff': diff}, {'path': path}
        if kind == 'search.wikipedia':
            query = action['query']
            if type(query) is not str or not 1 <= len(query.strip()) <= 200 or any(ord(c) < 32 for c in query):
                raise ValueError('bounded_explicit_search_query_required')
            return {'type': kind, 'query': query.strip(), 'provider': 'Wikipedia'}, {'provider': 'Wikipedia', 'query': query.strip()}
        if kind == 'guest.submit':
            if action['task_kind'] not in ('chat', 'python', 'cpp', 'diagnostic'):
                raise ValueError('unsupported_fixed_guest_task')
            if type(action['prompt']) is not str or not 1 <= len(action['prompt'].encode()) <= 8192:
                raise ValueError('guest_prompt_limit')
            snapshot = self._snapshot(project)
            if sha(action['snapshot_sha256']) != snapshot['sha256']:
                raise ValueError('workspace_changed_before_admission')
            normalized = {**action, 'arm': record['arm']}
            return normalized, {'task_kind': action['task_kind'], 'snapshot_sha256': snapshot['sha256'],
                                'prompt_sha256': hashlib.sha256(action['prompt'].encode()).hexdigest(), 'arm': record['arm']}
        ticket = identifier(action['review_ticket'])
        with self.c.lock:
            row = self.c.db.execute('SELECT job,project,record,expires FROM reviews WHERE id=?', (ticket,)).fetchone()
            if not row or row[1] != project or row[3] <= self.permissions.clock():
                raise ValueError('review_ticket_expired_or_wrong_workspace')
            job = self.c.db.execute('SELECT session FROM jobs WHERE id=?', (row[0],)).fetchone()
            if not job or job[0] != session:
                raise ValueError('review_ticket_conversation_mismatch')
        plan = json.loads(row[2])
        original = Files(plan['source'])
        try:
            info = os.fstat(original.fd)
            before = original.read(plan['path'])
            if (info.st_dev, info.st_ino) != (plan['device'], plan['inode']) or before['sha256'] != plan['expected']:
                raise ValueError('original_repository_drift')
        finally:
            original.close()
        diff = ''.join(difflib.unified_diff(before['text'].splitlines(keepends=True), plan['text'].splitlines(keepends=True), fromfile=plan['path'], tofile=plan['path']))
        if len(diff.encode()) > 65536:
            raise ValueError('review_diff_limit_64_KiB')
        return {'type': kind, 'review_ticket': ticket, 'plan_sha256': digest(plan),
                'path': plan['path'], 'base_sha256': plan['expected'], 'candidate_sha256': plan['candidate'], 'diff': diff}, {'review_ticket': ticket, 'plan_sha256': digest(plan)}

    def _input_action(self, normalized):
        kind = normalized['type']
        if kind == 'workspace.write':
            return {key:normalized[key] for key in ('type','path','text')} | {'expected_sha256':normalized['base_sha256']}
        return {key:normalized[key] for key in ACTION_FIELDS[kind]}

    def request(self, session, run_id, request_id, action):
        identifier(request_id)
        if type(action) is not dict or type(action.get('type')) is not str or action['type'] not in ACTION_FIELDS or set(action) != ACTION_FIELDS[action['type']]:
            raise ValueError('unsupported_action_schema')
        self.c.session_record(session)
        # Reconnect retries return the immutable prior result even after a write
        # changed its own base. A changed argument can never reuse the key.
        with self.c.lock, self.c.db:
            row = self.c.db.execute('SELECT id FROM permission_actions WHERE session=? AND request_id=?', (session,request_id)).fetchone()
            if row:
                self.permissions._policy(session)
                self.permissions._expire(session)
                old = self.permissions._get(row[0],session)
                candidate = dict(action)
                if candidate['type'] == 'search.wikipedia' and type(candidate['query']) is str:
                    candidate['query'] = candidate['query'].strip()
                if self._input_action(old['action']) != candidate or old['run_id'] != run_id:
                    raise ValueError('action_idempotency_conflict')
                return self.permissions._public(old)
        # Normalize under the same lock as policy admission. Models never supply
        # roots, native authority, backend URLs or the normalized base hashes.
        with self.c.lock:
            normalized, scope = self.normalize(session, action)
            capability = {'workspace.read':'read', 'workspace.write':'write', 'search.wikipedia':'search',
                          'guest.submit':'guest', 'host.apply':'host_apply'}[normalized['type']]
        availability = self.available(session)[capability]
        return self.permissions.request(session, run_id, request_id, normalized, scope,
                                        availability['available'], availability['reason'])

    @staticmethod
    def _error(error):
        # Do not return exception strings containing private absolute paths.
        return str(error) if re.fullmatch(r'[A-Za-z0-9_ .:-]{1,180}',str(error)) else type(error).__name__

    def execute(self, session, action_id):
        with self.c.lock, self.c.db:
            item, fresh = self.permissions.claim(session,action_id)
            if not fresh:
                return self.permissions._public(item)
            # Consumption is durable before an external effect. A crash cannot
            # replay an already sent request or an already written host file.
            self.c.db.commit()
            if item['action']['type'] not in ('search.wikipedia','guest.submit'):
                self.c.db.execute('BEGIN IMMEDIATE')
                try:
                    self.permissions.validate_execution(item)
                    result = self._dispatch(item)
                    if len(json.dumps(result).encode()) > 65536:
                        raise ValueError('action_result_limit_64_KiB')
                except (OSError,ValueError,RuntimeError) as error:
                    return self.permissions.finish(item,error=self._error(error))
                return self.permissions.finish(item,result=result)
            self.permissions.validate_execution(item)
        # Native admission and the provider have bounded I/O. Neither holds the
        # catalog lock: policy revocation/cancellation remains responsive while
        # they are in flight. Started effects cannot be retroactively undone.
        result = None
        error = None
        try:
            result = self._dispatch(item)
            if len(json.dumps(result).encode()) > 65536:
                raise ValueError('action_result_limit_64_KiB')
        except (OSError,ValueError,RuntimeError) as failure:
            error = self._error(failure)
        with self.c.lock, self.c.db:
            current = self.permissions._get(action_id,session)
            try:
                self.permissions.validate_execution(item)
                revoked = current['state'] != 'executing'
            except (ValueError,PermissionError):
                revoked = True
            if not revoked:
                return self.permissions.finish(item,result=result,error=error)
        cancellation = self._cancel_guests(session,only=action_id) if item['action']['type'] == 'guest.submit' else []
        with self.c.lock,self.c.db:
            receipt = {'cancelled_work':cancellation,
                       'effects_notice':'Revocation cannot undo a request already sent. Native admission is cancelled after its acknowledgement; watchdog limits remain in force.'}
            return self.permissions.finish_revoked(item,result=receipt)

    def _dispatch(self, item):
        action = item['action']
        kind = action['type']
        if kind.startswith('workspace.'):
            fs = self.c.files(item['project_id'])
            try:
                if kind == 'workspace.read':
                    result = fs.read(action['path'])
                    if result['sha256'] != action['base_sha256']:
                        raise ValueError('file_drift')
                    return {'path': action['path'], **result}
                result = fs.write(action['path'], action['text'], action['base_sha256'])
                if result['sha256'] != action['candidate_sha256']:
                    raise ValueError('workspace_write_hash_mismatch')
                return {'path': action['path'], 'sha256':result['sha256'], 'bytes':result['bytes'], 'original_host_files_changed': False}
            finally:
                fs.close()
        if kind == 'search.wikipedia':
            import io
            from workspace.search import search
            from workspace.attachments import Attachments
            result = search(action['query'])
            with self.c.lock,self.c.db:
                self.permissions.validate_execution(item)
                if self.permissions._get(item['id'],item['session_id'])['state'] != 'executing':
                    raise PermissionError('action_cancelled_during_search')
                return self._search_context(result)
        from workspace.jobs import Jobs
        jobs = Jobs(self.c)
        if kind == 'guest.submit':
            availability = self.available(item['session_id'])['guest']
            if not availability['available']:
                raise RuntimeError('qualified_guest_unavailable_no_host_fallback')
            with self.c.lock,self.c.db:
                self.permissions.validate_execution(item)
                if self.permissions._get(item['id'],item['session_id'])['state'] != 'executing':
                    raise PermissionError('action_cancelled_before_guest_admission')
                session = self.c.session_record(item['session_id'])
                if session['arm'] != action['arm']:
                    raise ValueError('guest_model_changed_since_approval')
            result = jobs.call('job.submit', {'session_id':item['session_id'], 'client_job_id':item['id'],
                'prompt':action['prompt'], 'snapshot_sha256':action['snapshot_sha256'], 'task_kind':action['task_kind']})
            return {'job': result, 'asynchronous': True, 'execution_boundary': 'qualified_disposable_guest'}
        if kind == 'host.apply':
            row = self.c.db.execute('SELECT record,project,expires FROM reviews WHERE id=?', (action['review_ticket'],)).fetchone()
            if not row or row[1] != item['project_id'] or row[2] <= self.permissions.clock() or digest(json.loads(row[0])) != action['plan_sha256']:
                raise ValueError('review_plan_changed_or_expired')
            return jobs.call('patch.apply', {'review_ticket':action['review_ticket']})
        raise ValueError('unsupported_action')

    def _search_context(self,result):
            import io
            from workspace.attachments import Attachments
            if not result['sources']:
                return result
            text = 'Search query: ' + result['query'] + '\n\n' + '\n\n'.join(
                '[' + str(index+1) + '] ' + source['title'] + '\n' + source['url'] + '\n' + source['text']
                for index, source in enumerate(result['sources']))
            raw = text.encode()
            attachment = Attachments(self.c).upload(io.BytesIO(raw),len(raw),'Wikipedia search.txt','text/plain')
            self.c.db.execute('UPDATE attachments SET metadata=? WHERE id=?',
                              (json.dumps({'search':result}),attachment['id']))
            return {**result,'attachment':{**attachment,'metadata':{'search':result}}}

    def _cancel_guests(self, session, only=None):
        from workspace.jobs import Jobs
        outcomes = []
        with self.c.lock:
            rows = self.c.db.execute("SELECT id,action,result FROM permission_actions WHERE session=? AND state IN ('executing','cancelling','completed')", (session,)).fetchall()
        for action_id, raw_action, raw_result in rows:
            if (only is not None and action_id != only) or json.loads(raw_action)['type'] != 'guest.submit':
                continue
            result = json.loads(raw_result) if raw_result else {}
            job_id = result.get('job',{}).get('id') or action_id
            try:
                owned, record = Jobs(self.c).local(job_id)
                if owned['id'] != session:
                    raise ValueError('owned_guest_job_mismatch')
                if record.get('state') not in ('review_ready','failed','cancelled'):
                    response = Jobs(self.c).call('job.cancel', {'job_id':job_id})
                    outcomes.append({'action_id':action_id, 'job_id':job_id, 'cancel_requested':response.get('status') == 'ok'})
            except (OSError, ValueError, RuntimeError, PermissionError):
                outcomes.append({'action_id':action_id, 'job_id':job_id, 'cancel_requested':False,
                                 'reason':'native_cancellation_unavailable_watchdog_still_applies'})
        return outcomes

    def cancel(self, session, action_id):
        item = self.permissions.cancel_action(session,action_id)
        cancellation = self._cancel_guests(session,only=action_id)
        return {**item,'cancelled_work':cancellation,
                'effects_notice':'Completed effects cannot be undone; an in-flight native admission is cancelled after its acknowledgement.'}

    def update(self, session, expected_version, mode, capabilities):
        result = self.permissions.update(session, expected_version, mode, capabilities)
        return {**result, 'available':self.available(session), 'cancelled_work':self._cancel_guests(session),
                'effects_notice':'Completed effects cannot be undone by revoking permission.'}

    def revoke(self, session):
        result = self.permissions.revoke(session)
        return {**result, 'available':self.available(session), 'cancelled_work':self._cancel_guests(session),
                'effects_notice':'Completed effects cannot be undone by revoking permission.'}


def parse_model_tool(call):
    """Parse one explicit function call, never prose or a JSON-looking reply."""
    if type(call) is not dict or set(call) != {'id','type','function'} or call['type'] != 'function' or type(call['id']) is not str or not 1 <= len(call['id']) <= 128:
        raise ValueError('invalid_action_tool_call')
    function = call['function']
    if type(function) is not dict or set(function) != {'name','arguments'} or type(function['name']) is not str or function['name'] not in ('hermes_action',*MODEL_FUNCTIONS) or type(function['arguments']) is not str or len(function['arguments'].encode()) > 32768:
        raise ValueError('unsupported_action_tool')
    # Duplicate JSON keys cannot override a validated field.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate_action_argument')
            result[key] = value
        return result
    action = json.loads(function['arguments'], object_pairs_hook=unique)
    if function['name'] in MODEL_FUNCTIONS:
        if type(action) is not dict or 'type' in action:
            raise ValueError('unsupported_action_schema')
        action = {'type':MODEL_FUNCTIONS[function['name']], **action}
    if type(action) is not dict or type(action.get('type')) is not str or action['type'] not in ACTION_FIELDS or set(action) != ACTION_FIELDS[action['type']]:
        raise ValueError('unsupported_action_schema')
    if action['type'] == 'host.apply':
        raise ValueError('model_cannot_request_original_host_apply')
    return action
