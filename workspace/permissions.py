"""Server-owned, conversation-scoped policies and single-use action approvals.

A policy is not native admission. This ledger never creates a shell, changes a
native peer identity, or treats model text as permission. The authenticated UI
alone calls update/decide; model tools can only request normalized actions.
"""
import hashlib
import json
import os
import time
import uuid

from workspace.catalog import identifier

CAPABILITIES = ('read', 'write', 'guest', 'search', 'microphone')
PRESETS = {
    'chat_only': dict.fromkeys(CAPABILITIES, False),
    'ask': dict.fromkeys(CAPABILITIES, False),
    'workspace_agent': {name: name in ('read', 'write', 'guest') for name in CAPABILITIES},
}
ACTION_CAPABILITY = {'workspace.read': 'read', 'workspace.write': 'write',
                     'search.wikipedia': 'search', 'guest.submit': 'guest', 'host.apply': 'host_apply'}
TERMINAL = {'completed', 'failed', 'denied', 'revoked', 'expired', 'unavailable'}
TTL = 300
MAX_ACTIONS_PER_RUN = 12


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Permissions:
    def __init__(self, catalog, clock=time.time):
        self.c = catalog
        self.clock = clock
        self.uid = os.getuid()
        with self.c.lock, self.c.db:
            self.c.db.executescript('''
              CREATE TABLE IF NOT EXISTS permission_policies (
                session TEXT PRIMARY KEY, uid INTEGER NOT NULL, project TEXT,
                version INTEGER NOT NULL, mode TEXT NOT NULL, capabilities TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS permission_actions (
                id TEXT PRIMARY KEY, uid INTEGER NOT NULL, session TEXT NOT NULL,
                project TEXT, run TEXT, request_id TEXT NOT NULL, version INTEGER NOT NULL,
                action_hash TEXT NOT NULL, scope_hash TEXT NOT NULL, action TEXT NOT NULL,
                state TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
                result TEXT, error TEXT, authorization TEXT, UNIQUE(session, request_id));
              CREATE TABLE IF NOT EXISTS permission_grants (
                id TEXT PRIMARY KEY, session TEXT NOT NULL, version INTEGER NOT NULL,
                scope_hash TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS permission_audit (
                seq INTEGER PRIMARY KEY, at REAL NOT NULL, session TEXT NOT NULL,
                action_id TEXT, event TEXT NOT NULL, action_type TEXT,
                resource_hash TEXT, policy_version INTEGER NOT NULL);
            ''')
            columns = {row[1] for row in self.c.db.execute('PRAGMA table_info(permission_actions)')}
            if 'authorization' not in columns:
                self.c.db.execute('ALTER TABLE permission_actions ADD COLUMN authorization TEXT')

    def _audit(self, session, version, event, action=None):
        self.c.db.execute('INSERT INTO permission_audit(at,session,action_id,event,action_type,resource_hash,policy_version) VALUES (?,?,?,?,?,?,?)',
                          (self.clock(), session, action['id'] if action else None, event,
                           action['action']['type'] if action else None,
                           action['scope_hash'] if action else None, version))

    def _policy(self, session):
        record = self.c.session_record(session)
        project = record['project']
        row = self.c.db.execute('SELECT uid,project,version,mode,capabilities FROM permission_policies WHERE session=?', (session,)).fetchone()
        if row is None:
            self.c.db.execute('INSERT INTO permission_policies VALUES (?,?,?,?,?,?)',
                              (session, self.uid, project, 1, 'chat_only', canonical(PRESETS['chat_only'])))
            row = (self.uid, project, 1, 'chat_only', canonical(PRESETS['chat_only']))
        if row[0] != self.uid:
            raise PermissionError('permission_owner_mismatch')
        if row[1] != project:
            # Moving a conversation cannot carry a grant into a different tree.
            version = row[2] + 1
            self._invalidate(session)
            self.c.db.execute('UPDATE permission_policies SET project=?,version=?,mode=?,capabilities=? WHERE session=?',
                              (project, version, 'chat_only', canonical(PRESETS['chat_only']), session))
            self._audit(session, version, 'workspace_changed_policy_reset')
            row = (self.uid, project, version, 'chat_only', canonical(PRESETS['chat_only']))
        return {'session_id': session, 'project_id': row[1], 'version': row[2],
                'mode': row[3], 'capabilities': json.loads(row[4])}

    def _invalidate(self, session):
        self.c.db.execute("UPDATE permission_actions SET state='revoked',error='policy_changed' WHERE session=? AND state IN ('pending','allowed')", (session,))
        self.c.db.execute("UPDATE permission_actions SET state='cancelling',error='policy_changed_after_dispatch_started' WHERE session=? AND state='executing'", (session,))
        self.c.db.execute('DELETE FROM permission_grants WHERE session=?', (session,))

    def read(self, session):
        if session is None:
            return {'session_id': None, 'project_id': None, 'version': 0, 'mode': 'chat_only',
                    'capabilities': dict(PRESETS['chat_only']), 'pending': [], 'grants': []}
        with self.c.lock, self.c.db:
            policy = self._policy(session)
            self._expire(session)
            policy['pending'] = [self._public(self._get(row[0], session)) for row in self.c.db.execute(
                "SELECT id FROM permission_actions WHERE session=? AND state IN ('pending','allowed') ORDER BY created", (session,)).fetchall()]
            policy['grants'] = [{'id': row[0], 'scope_hash': row[1], 'expires': row[2]} for row in self.c.db.execute(
                'SELECT id,scope_hash,expires FROM permission_grants WHERE session=? AND version=? AND expires>?',
                (session, policy['version'], self.clock())).fetchall()]
            return policy

    def update(self, session, expected_version, mode, capabilities):
        if type(mode) is not str or mode not in (*PRESETS, 'custom') or type(capabilities) is not dict or set(capabilities) != set(CAPABILITIES) or any(type(v) is not bool for v in capabilities.values()):
            raise ValueError('invalid_permission_policy')
        if mode != 'custom' and capabilities != PRESETS[mode]:
            raise ValueError('preset_capabilities_mismatch')
        if type(expected_version) is not int:
            raise ValueError('policy_version_required')
        with self.c.lock, self.c.db:
            policy = self._policy(session)
            if policy['version'] != expected_version:
                raise ValueError('permission_policy_changed_reload_required')
            version = policy['version'] + 1
            self._invalidate(session)
            self.c.db.execute('UPDATE permission_policies SET version=?,mode=?,capabilities=? WHERE session=?',
                              (version, mode, canonical(capabilities), session))
            self._audit(session, version, 'policy_changed')
            return self.read(session)

    def revoke(self, session):
        policy = self.read(session)
        return self.update(session, policy['version'], 'chat_only', dict(PRESETS['chat_only']))

    def require(self, session, capability):
        if capability not in CAPABILITIES:
            raise ValueError('unknown_capability')
        with self.c.lock, self.c.db:
            policy = self._policy(session)
            if not policy['capabilities'][capability]:
                raise PermissionError('permission_required_' + capability)
            return policy

    def _expire(self, session):
        self.c.db.execute("UPDATE permission_actions SET state='expired',error='approval_expired' WHERE session=? AND state IN ('pending','allowed') AND expires<=?", (session, self.clock()))
        self.c.db.execute('DELETE FROM permission_grants WHERE expires<=?', (self.clock(),))

    def _get(self, action_id, session):
        identifier(action_id)
        row = self.c.db.execute('SELECT id,uid,session,project,run,request_id,version,action_hash,scope_hash,action,state,created,expires,result,error,authorization FROM permission_actions WHERE id=? AND session=?', (action_id, session)).fetchone()
        if not row or row[1] != self.uid:
            raise ValueError('unknown_owned_action')
        item = dict(zip(('id','uid','session_id','project_id','run_id','request_id','policy_version','action_hash','scope_hash','action','state','created','expires','result','error','authorization'), row))
        item['action'] = json.loads(item['action'])
        item['result'] = json.loads(item['result']) if item['result'] else None
        return item

    def _public(self, item):
        action = item['action']
        resource = action.get('path') or action.get('query') or action.get('task_kind') or 'reviewed original file'
        return {name: item[name] for name in ('id','session_id','project_id','run_id','policy_version','state','created','expires','result','error')} | {
            'ticket_id': item['id'], 'type': action['type'], 'resource': resource,
            'action': action, 'summary': action['type'] + ': ' + resource,
            'diff': action.get('diff'), 'completed_effects_reversible': False}

    def list(self, session):
        with self.c.lock, self.c.db:
            self._policy(session)
            self._expire(session)
            rows = self.c.db.execute('SELECT id FROM permission_actions WHERE session=? ORDER BY created DESC LIMIT 100', (session,)).fetchall()
            return [self._public(self._get(row[0], session)) for row in rows]

    def request(self, session, run_id, request_id, action, scope, available=True, reason=None):
        """Accept only dispatcher-normalized actions; this is not an RPC endpoint."""
        identifier(request_id)
        with self.c.lock, self.c.db:
            policy = self._policy(session)
            self._expire(session)
            if run_id is not None:
                identifier(run_id)
                row = self.c.db.execute('SELECT session,created FROM chat_runs WHERE id=?', (run_id,)).fetchone()
                if not row or row[0] != session:
                    raise ValueError('action_run_conversation_mismatch')
                if self.clock() - row[1] > 360:
                    raise ValueError('action_run_time_budget_exceeded')
            binding = {'uid': self.uid, 'session': session, 'project': policy['project_id'],
                       'run': run_id, 'version': policy['version'], 'action': action}
            action_hash = digest(binding)
            old = self.c.db.execute('SELECT id FROM permission_actions WHERE session=? AND request_id=?', (session, request_id)).fetchone()
            if old:
                item = self._get(old[0], session)
                if item['action_hash'] != action_hash:
                    raise ValueError('action_idempotency_conflict')
                return self._public(item)
            if run_id and self.c.db.execute('SELECT COUNT(*) FROM permission_actions WHERE run=? AND session=?', (run_id, session)).fetchone()[0] >= MAX_ACTIONS_PER_RUN:
                raise ValueError('action_step_budget_exceeded')
            if self.c.db.execute("SELECT COUNT(*) FROM permission_actions WHERE session=? AND state IN ('pending','allowed')", (session,)).fetchone()[0] >= 32:
                raise ValueError('pending_action_limit')
            capability = ACTION_CAPABILITY[action['type']]
            scope_hash = digest({'project': policy['project_id'], 'capability': capability, 'scope': scope})
            denied = self.c.db.execute("SELECT 1 FROM permission_actions WHERE session=? AND version=? AND action=? AND state='denied'",
                                       (session, policy['version'], canonical(action))).fetchone()
            grant = self.c.db.execute('SELECT 1 FROM permission_grants WHERE session=? AND version=? AND scope_hash=? AND expires>?', (session, policy['version'], scope_hash, self.clock())).fetchone()
            if not available:
                state = 'unavailable'
            elif denied:
                state = 'denied'
            elif capability != 'host_apply' and (policy['capabilities'].get(capability) or grant):
                state = 'allowed'
            elif policy['mode'] == 'chat_only':
                state = 'denied'
            else:
                state = 'pending'
            action_id = uuid.uuid4().hex
            authorization = ('policy' if policy['capabilities'].get(capability) else 'session') if state == 'allowed' else None
            self.c.db.execute('INSERT INTO permission_actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (action_id, self.uid, session, policy['project_id'], run_id, request_id, policy['version'], action_hash, scope_hash,
                 canonical(action), state, self.clock(), self.clock()+TTL, None, reason if not available else None, authorization))
            item = self._get(action_id, session)
            self._audit(session, policy['version'], 'requested', item)
            self._audit(session, policy['version'], state, item)
            return self._public(item)

    def decide(self, session, ticket_id, decision):
        if decision not in ('allow_once', 'session', 'deny'):
            raise ValueError('invalid_permission_decision')
        with self.c.lock, self.c.db:
            policy = self._policy(session)
            self._expire(session)
            item = self._get(ticket_id, session)
            if item['policy_version'] != policy['version'] or item['state'] != 'pending':
                raise ValueError('approval_not_pending_or_policy_changed')
            if decision == 'session' and item['action']['type'] == 'host.apply':
                raise ValueError('original_host_diff_requires_allow_once')
            state = 'denied' if decision == 'deny' else 'allowed'
            self.c.db.execute('UPDATE permission_actions SET state=?,authorization=? WHERE id=?',
                              (state, 'once' if decision == 'allow_once' else 'session' if decision == 'session' else None, ticket_id))
            if decision == 'session':
                self.c.db.execute('INSERT INTO permission_grants VALUES (?,?,?,?,?,?)',
                                  (uuid.uuid4().hex, session, policy['version'], item['scope_hash'], self.clock(), self.clock()+1800))
            self._audit(session, policy['version'], decision, item)
            return self._public(self._get(ticket_id, session))

    def validate_execution(self, item):
        session = item['session_id']
        policy = self._policy(session)
        if item['expires'] <= self.clock():
            raise PermissionError('action_approval_expired')
        if item['policy_version'] != policy['version'] or item['project_id'] != policy['project_id']:
            raise PermissionError('action_policy_or_workspace_changed')
        expected = digest({'uid': self.uid, 'session': session, 'project': policy['project_id'],
                           'run': item['run_id'], 'version': policy['version'], 'action': item['action']})
        if expected != item['action_hash']:
            raise PermissionError('action_binding_mismatch')
        if item['run_id']:
            run = self.c.db.execute('SELECT session,created,state FROM chat_runs WHERE id=?', (item['run_id'],)).fetchone()
            if not run or run[0] != session or self.clock()-run[1] > 360 or run[2] in ('cancelling','cancelled','failed'):
                raise PermissionError('action_model_run_expired_or_mismatched')
        capability = ACTION_CAPABILITY[item['action']['type']]
        if item['authorization'] == 'policy':
            if not policy['capabilities'].get(capability):
                raise PermissionError('action_capability_revoked')
        elif item['authorization'] == 'session':
            grant = self.c.db.execute('SELECT 1 FROM permission_grants WHERE session=? AND version=? AND scope_hash=? AND expires>?',
                                      (session, policy['version'], item['scope_hash'], self.clock())).fetchone()
            if not grant:
                raise PermissionError('action_session_grant_expired_or_revoked')
        elif item['authorization'] != 'once':
            raise PermissionError('action_authorization_missing')
        return policy

    def claim(self, session, action_id):
        """Caller holds catalog lock through final validation and synchronous effect."""
        self._expire(session)
        item = self._get(action_id, session)
        if item['state'] in ('completed', 'failed'):
            return item, False
        if item['state'] != 'allowed':
            raise PermissionError('action_not_approved_' + item['state'])
        policy = self.validate_execution(item)
        changed = self.c.db.execute("UPDATE permission_actions SET state='executing' WHERE id=? AND state='allowed'", (action_id,)).rowcount
        if changed != 1:
            raise PermissionError('action_already_consumed')
        self._audit(session, policy['version'], 'executing', item)
        return item, True

    def cancel_action(self, session, action_id):
        with self.c.lock, self.c.db:
            item = self._get(action_id,session)
            state = 'cancelling' if item['state'] == 'executing' else 'revoked'
            if item['state'] in ('pending','allowed','executing'):
                self.c.db.execute('UPDATE permission_actions SET state=?,error=? WHERE id=?',
                                  (state,'owned_action_cancelled',action_id))
                self._audit(session,item['policy_version'],'cancel_requested',item)
            return self._public(self._get(action_id,session))

    def finish_revoked(self, item, result=None):
        self.c.db.execute("UPDATE permission_actions SET state='revoked',result=?,error=? WHERE id=?",
                          (canonical(result) if result is not None else None,
                           'permission_revoked_after_dispatch_started',item['id']))
        self._audit(item['session_id'],item['policy_version'],'revoked',item)
        return self._public(self._get(item['id'],item['session_id']))

    def finish(self, item, result=None, error=None):
        state = 'failed' if error else 'completed'
        self.c.db.execute('UPDATE permission_actions SET state=?,result=?,error=? WHERE id=?',
                          (state, canonical(result) if result is not None else None, error, item['id']))
        self._audit(item['session_id'], item['policy_version'], state, item)
        return self._public(self._get(item['id'], item['session_id']))
