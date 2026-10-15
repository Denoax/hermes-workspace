"""Reference schema/lease gate. No VM, network, process or command execution.

Caller supplies trusted host-monotonic time and immutable approved inventory.
Local Codex must add/test the actual transport, watchdog and outside enforcement.
"""
from dataclasses import dataclass
import math
import re
import secrets
import threading
from starter.json_limits import bounded_json

ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z')
TOKEN = re.compile(r'[A-Za-z0-9_-]{16,128}\Z')
REQUIRED = frozenset({'run_id', 'vm_id', 'case_id', 'action', 'job_id', 'lease_token'})
ACTIONS = frozenset({'inspect_case', 'write_candidate', 'evaluate_case'})
MAX_WIRE_BYTES = 65536

@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str

def decode_request(raw):
    value = bounded_json(raw,max_bytes=MAX_WIRE_BYTES)
    if type(value) is not dict:
        raise ValueError('request_must_be_object')
    return value

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

class LeaseGate:
    def __init__(self, run_id, vm_ids, case_ids, issued_at, ttl_seconds=480,
                 heartbeat_timeout=45, max_actions=24, max_candidate_bytes=32768,
                 token=None):
        if not isinstance(run_id,str) or not ID.fullmatch(run_id) or not number(issued_at) or issued_at < 0:
            raise ValueError('invalid_trusted_run_configuration')
        self.vm_ids = frozenset(vm_ids)
        self.case_ids = frozenset(case_ids)
        if not self.vm_ids or not self.case_ids or any(not isinstance(v,str) or not ID.fullmatch(v) for v in self.vm_ids|self.case_ids):
            raise ValueError('invalid_trusted_inventory')
        if not number(ttl_seconds) or not 0 < ttl_seconds <= 5400 or not number(heartbeat_timeout) or not 0 < heartbeat_timeout <= ttl_seconds:
            raise ValueError('invalid_deadline')
        if type(max_actions) is not int or max_actions <= 0 or type(max_candidate_bytes) is not int or not 0 < max_candidate_bytes <= 32768:
            raise ValueError('invalid_budget')
        self.run_id = run_id
        self.token = token or secrets.token_urlsafe(32)
        if not TOKEN.fullmatch(self.token):
            raise ValueError('invalid_trusted_token')
        self.issued_at = issued_at
        self.expires_at = issued_at + ttl_seconds
        if not number(self.expires_at) or self.expires_at <= issued_at:
            raise ValueError('unrepresentable_deadline')
        self.heartbeat_timeout = heartbeat_timeout
        self.last_heartbeat = issued_at
        self.last_clock = issued_at
        self.max_actions = max_actions
        self.max_candidate_bytes = max_candidate_bytes
        self.used_actions = 0
        self.seen_jobs = set()
        self.revoked_reason = None
        self._lock = threading.Lock()

    def _state(self, now):
        if self.revoked_reason:
            return self.revoked_reason
        if not number(now) or now < self.last_clock:
            self.revoked_reason = 'invalid_or_regressed_host_clock'
            return self.revoked_reason
        self.last_clock = now
        if now >= self.expires_at:
            self.revoked_reason = 'absolute_expiry'
        elif now - self.last_heartbeat >= self.heartbeat_timeout:
            self.revoked_reason = 'heartbeat_lost'
        return self.revoked_reason

    def heartbeat(self, now):
        """Only the trusted authenticated health-monitor adapter may call this."""
        with self._lock:
            if self._state(now):
                return False
            self.last_heartbeat = now
            return True

    def tick(self, now):
        """Reference health/deadline result; does not stop a VM by itself."""
        with self._lock:
            reason = self._state(now)
            return Decision(not reason, reason or 'active')

    def revoke(self, reason='operator_revoked'):
        with self._lock:
            self.revoked_reason = reason

    def authorize(self, request, now):
        with self._lock:
            reason = self._state(now)
            if reason:
                return Decision(False, reason)
            if type(request) is not dict or set(request) - (REQUIRED|{'payload'}) or not REQUIRED <= set(request):
                return Decision(False, 'invalid_schema')
            if any(type(request[k]) is not str for k in REQUIRED):
                return Decision(False, 'invalid_field_type')
            if not TOKEN.fullmatch(request['lease_token']) or not secrets.compare_digest(self.token,request['lease_token']):
                return Decision(False, 'invalid_token')
            if request['run_id'] != self.run_id:
                return Decision(False, 'wrong_run')
            if request['vm_id'] not in self.vm_ids:
                return Decision(False, 'unknown_target')
            if request['case_id'] not in self.case_ids:
                return Decision(False, 'unknown_case')
            if request['action'] not in ACTIONS:
                return Decision(False, 'unknown_action')
            if not ID.fullmatch(request['job_id']):
                return Decision(False, 'invalid_job_id')
            if request['job_id'] in self.seen_jobs:
                return Decision(False, 'reject_duplicate')
            if self.used_actions >= self.max_actions:
                return Decision(False, 'action_budget_exhausted')
            if request['action'] == 'write_candidate':
                if type(request.get('payload')) is not str:
                    return Decision(False, 'candidate_required')
                try:
                    size = len(request['payload'].encode('utf-8', errors='strict'))
                except UnicodeError:
                    return Decision(False, 'invalid_candidate_encoding')
                if size > self.max_candidate_bytes:
                    return Decision(False, 'candidate_too_large')
            elif 'payload' in request:
                return Decision(False, 'unexpected_payload')
            self.seen_jobs.add(request['job_id'])
            self.used_actions += 1
            return Decision(True, 'authorized_guest_action')
