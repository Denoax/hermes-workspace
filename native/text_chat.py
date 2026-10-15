"""Trusted text-only resource admission; model bytes never enter the supervisor.

The operator receives a connected fixed backend descriptor using SCM_RIGHTS.
Keeping one duplicate lets the independent watchdog cancel the actual transport.
This grants no VM, filesystem, shell or model-directed tool authority.
"""
import http.client
import json
import os
import select
import socket
import subprocess
import threading
import time


class TextChat:
    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.lock = threading.RLock()
        self.current = None
        self.last = None

    def owner(self, job_id, pid):
        r = self.current
        if r is None or r['job_id'] != job_id or r['pid'] != pid:
            raise ValueError('text_run_owner_mismatch')
        return r

    def admit(self, job_id, arm, pid):
        import backend
        import window
        with self.lock, self.supervisor.mutation:
            if self.current or self.supervisor.active_run():
                raise RuntimeError('trusted_resource_owner_busy')
            if arm == 'normal' and window.active():
                raise RuntimeError('lab_window_owns_GPU_wait_for_normal_recovery')
            owner = os.pidfd_open(pid)
            record = {'job_id': job_id, 'pid': pid, 'owner': owner, 'arm': arm,
                      'deadline': time.monotonic() + 300, 'heartbeat': time.monotonic(),
                      'transport': None, 'window': False}
            self.current = record
            try:
                if arm == 'abliterated':
                    if not backend.artifacts_current():
                        raise RuntimeError('native_artifact_verification_required')
                    if not window.active():
                        subprocess.run(['/usr/bin/systemctl', 'start', window.SERVICE],
                                       check=True, timeout=180, capture_output=True)
                    if not window.active():
                        raise RuntimeError('bounded_window_not_active')
                    record['window'] = True
                    # Loading is outside the global lock so heartbeats and cancellation
                    # can reach this admitted owner. The backend checks the lease too.
                    self.lock.release()
                    try:
                        loaded = backend.start(arm, valid=lambda: self.valid(record))
                        qualification = backend.qualify(arm)
                    finally:
                        self.lock.acquire()
                    if not qualification['confined'] or not self.valid(record):
                        raise RuntimeError('text_backend_confinement_failed')
                    transport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    transport.connect(str(backend.SOCKET))
                    proof = {'model_alias': backend.ALIAS, 'context': 8192,
                             'arm': arm, 'confined': True, 'loaded': loaded,
                             'model_sha256':next(item['sha256'] for path,item in backend.artifact_inventory() if path.stem==arm)}
                else:
                    transport = socket.create_connection(('127.0.0.1', 8080), timeout=3)
                    record['transport'] = transport
                    c = http.client.HTTPConnection('127.0.0.1', 8080, timeout=3)
                    try:
                        c.request('GET', '/props'); response = c.getresponse()
                        props = json.loads(response.read(262144))
                        if response.status != 200 or props.get('model_alias') != 'qwen3.6-35b-a3b-q4' or props.get('default_generation_settings', {}).get('n_ctx') != 65536:
                            raise RuntimeError('normal_runtime_identity_changed')
                        c.request('GET', '/slots'); response = c.getresponse()
                        slots = json.loads(response.read(65536))
                        if response.status != 200 or any(s.get('is_processing') is not False for s in slots):
                            raise RuntimeError('normal_inference_in_progress')
                    finally:
                        c.close()
                    proof = {'model_alias': 'qwen3.6-35b-a3b-q4', 'context': 65536,
                             'arm': arm, 'source': 'existing_normal_service'}
                record['transport'] = transport
                return {'status': 'ok', 'job_id': job_id, 'identity': proof,
                        'lease_seconds_remaining': max(0, int(record['deadline'] - time.monotonic())),
                        '_backend_fd': transport.fileno()}
            except BaseException:
                if self.current is record:self.finish(record, cancelled=True)
                raise

    def valid(self, record):
        import window
        return (self.current is record and time.monotonic() < record['deadline']
                and time.monotonic() - record['heartbeat'] < 30
                and not select.select([record['owner']], [], [], 0)[0]
                and (not record['window'] or window.active()))

    def beat(self, job_id, pid):
        import window
        with self.lock:
            r = self.owner(job_id, pid)
            if not self.valid(r):
                raise RuntimeError('text_lease_expired')
            r['heartbeat'] = time.monotonic()
            if r['window']:
                window.beat()
            return {'status': 'ok'}

    def finish(self, record, cancelled=False, defer_restore=False):
        import backend
        import window
        transport = record.get('transport')
        if transport:
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            transport.close()
        acknowledged = False
        if record['window']:
            backend.stop()
            acknowledged = True
            # A client release sends its acknowledgement before stopping this
            # supervisor. Watchdog recovery has no client reply to preserve.
            if not defer_restore:
                subprocess.run(['/usr/bin/systemctl', '--no-block', 'stop', window.SERVICE],
                               check=True, timeout=5, capture_output=True)
        else:
            end = time.monotonic() + 8
            while time.monotonic() < end:
                c = http.client.HTTPConnection('127.0.0.1', 8080, timeout=1)
                try:
                    c.request('GET', '/slots'); response = c.getresponse()
                    slots = json.loads(response.read(65536))
                    if response.status == 200 and all(s.get('is_processing') is False for s in slots):
                        acknowledged = True
                        break
                except (OSError, ValueError, http.client.HTTPException):
                    pass
                finally:
                    c.close()
                time.sleep(.1)
        os.close(record['owner'])
        self.current = None
        self.last = {'status': 'ok' if acknowledged else 'failed',
                     'job_id': record['job_id'], 'compute_idle_acknowledged': acknowledged,
                     'terminal': 'cancelled' if cancelled else 'completed'}
        if not acknowledged:
            self.last['error'] = 'compute_release_not_acknowledged'
        return {**self.last, **({'_restore_window': True} if record['window'] and defer_restore else {})}

    def release(self, job_id, pid, cancelled=False):
        with self.lock:
            if self.current is None and self.last and self.last['job_id'] == job_id:
                return self.last
            return self.finish(self.owner(job_id, pid), cancelled, defer_restore=True)

    def check(self):
        # A long systemd admission must not block the supervisor watchdog tick.
        if not self.lock.acquire(blocking=False):return
        try:
            if self.current and not self.valid(self.current):
                self.finish(self.current, cancelled=True)
        finally:self.lock.release()
