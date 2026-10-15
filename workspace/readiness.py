"""Cheap, root-attested admission readiness; never loads a model or repairs the OS."""
import stat
import threading
import time

from lab.native_client import CONTROL, NativeClient


class AdmissionUnavailable(RuntimeError):
    def __init__(self, readiness):
        super().__init__('local_model_connection_needs_repair')
        self.readiness = readiness


def control_metadata():
    try:
        item, parent = CONTROL.lstat(), CONTROL.parent.lstat()
        trusted = (stat.S_ISSOCK(item.st_mode) and item.st_uid == 0
                   and stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
                   and not parent.st_mode & 0o022)
        code = 'trusted_metadata' if trusted else ('root_identity_not_visible' if item.st_uid == 65534 else 'untrusted_control_metadata')
        return {'trusted': trusted, 'code': code, 'socket_uid': item.st_uid, 'parent_uid': parent.st_uid}
    except FileNotFoundError:
        return {'trusted': False, 'code': 'control_socket_missing'}
    except OSError:
        return {'trusted': False, 'code': 'control_metadata_unreadable'}


class Readiness:
    def __init__(self, catalog=None, client_factory=None, clock=time.monotonic):
        self.catalog = catalog
        self.client_factory = client_factory or (lambda: NativeClient(timeout=3))
        self.clock = clock
        self.lock = threading.Lock()
        self.cached = None
        self.until = 0

    def read(self, fresh=False):
        with self.lock:
            if not fresh and self.cached is not None and self.clock() < self.until:
                return self.cached
            control = control_metadata()
            result = {'state': 'repair_required', 'control': control,
                      'admission': {'available': False, 'code': control['code']},
                      'detail': 'Local model connection needs repair. The trusted native control channel is unavailable.',
                      'retryable': True}
            pinned_artifacts_current = False
            if control['trusted']:
                try:
                    native = self.client_factory().call('status')
                    if native.get('status') != 'ok':
                        raise RuntimeError('native_status_not_ready')
                    facts = native.get('observed_facts', {})
                    pinned_artifacts_current = facts.get('pinned_model_and_backend_artifacts_current') is True
                    busy = bool(facts.get('owned_fleet_active') or facts.get('inference_window_active'))
                    recovering = native.get('window_status') in ('opening', 'restoring', 'restore_failed')
                    result.update(state='busy' if busy or recovering else 'ready',
                                  admission={'available': not (busy or recovering), 'code': 'normal_recovery_pending' if recovering else 'resource_owner_busy' if busy else 'root_peer_attested'},
                                  detail='Waiting for the current resource owner and normal Qwen recovery.' if busy or recovering else 'Protected local connection is ready.')
                except (OSError, ValueError, RuntimeError):
                    result['admission']['code'] = 'native_peer_or_status_unavailable'
                    result['detail'] = 'Local model connection needs repair. The protected native service did not answer its safe status probe.'
            result['models'] = {
                model: {**result['admission'], 'detail': result['detail']}
                for model in ('normal', 'abliterated')
            }
            # The normal model has its own identity check at admission. The
            # candidate additionally requires the native boot-bound artifact
            # receipt; a working control socket cannot stand in for that proof.
            if result['admission']['available'] and not pinned_artifacts_current:
                result['models']['abliterated'] = {
                    'available': False,
                    'code': 'native_artifact_verification_required',
                    'detail': 'Abliterated Qwen needs protected artifact verification for this boot. Normal Qwen remains available.',
                }
            self.cached, self.until = result, self.clock()+2
            return result

    def require(self):
        result = self.read(fresh=True)
        if not result['admission']['available']:
            raise AdmissionUnavailable(result)
        return result
