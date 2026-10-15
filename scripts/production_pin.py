"""Observe the actual desktop pin through its existing owner-only CDP pipe.

The pin starts its normal service, dedicated browser profile and authentication.
Only its polling launcher is paused while the reviewer owns the pipe; neither
the browser nor the service is paused. No replacement catalog/server or cookie
bootstrap is supplied. Closing this harness always resumes its exact child.
"""
import json
import fcntl
import stat
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workspace import launcher
from workspace.parity_browser import Browser


class ProductionPin(Browser):
    def __init__(self):
        if subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'hyprlock'], capture_output=True).returncode == 0:
            raise RuntimeError('production_pin_blocked_by_screen_lock')
        # Review begins only after a deliberate fresh launch of the real pin.
        if any(p.name.isdigit() and launcher.owns_browser(p.name) for p in Path('/proc').iterdir()):
            raise RuntimeError('close_existing_Hermes_pin_before_fresh_launch')
        self.audio_module = None
        self.process = subprocess.Popen([str(Path.home()/'.local/bin/hermes-workspace')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.owner = os.pidfd_open(self.process.pid)
        self.paused = False
        self.pipe = None
        try:
            deadline = time.monotonic()+25
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('actual_pin_launcher_exited')
                descriptors = {}
                for p in (Path('/proc')/str(self.process.pid)/'fd').iterdir():
                    try:
                        name = os.readlink(p)
                        if '/hermes-pipe-' in name and name.endswith('/out (deleted)'): descriptors['read'] = p
                        if '/hermes-pipe-' in name and name.endswith('/in (deleted)'): descriptors['write'] = p
                    except FileNotFoundError:
                        pass
                if len(descriptors) == 2:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('actual_pin_private_pipe_unavailable')
            # browser() runs while the launcher's exclusive startup lock is
            # held. Wait for its release, rather than racing cookie/geometry
            # setup with a fixed delay, before taking the polling pipe owner.
            lock = os.open(launcher.STATE/'launcher.lock', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                facts = os.fstat(lock)
                if facts.st_uid != os.getuid() or not stat.S_ISREG(facts.st_mode) or facts.st_mode & 0o022:
                    raise RuntimeError('untrusted_actual_pin_startup_lock')
                deadline = time.monotonic() + 25
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        if self.process.poll() is not None:
                            raise RuntimeError('actual_pin_launcher_exited_during_startup')
                        if time.monotonic() >= deadline:
                            raise RuntimeError('actual_pin_startup_lock_timeout')
                        time.sleep(.05)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)
                        break
            finally:
                os.close(lock)
            # These are the exact launcher's own authenticated FIFOs, after its
            # configuration completed and only its idle poller remains.
            signal.pidfd_send_signal(self.owner, signal.SIGSTOP)
            self.paused = True
            incoming = os.open(descriptors['read'], os.O_RDWR | os.O_NONBLOCK)
            outgoing = os.open(descriptors['write'], os.O_WRONLY | os.O_NONBLOCK)
            os.set_blocking(incoming, True)
            os.set_blocking(outgoing, True)
            self.pipe = launcher.Pipe(incoming, outgoing)
            self.pipe.counter = 1000000
            self.pipe.call('Browser.getVersion')
            targets = self.pipe.call('Target.getTargets')['targetInfos']
            self.target = next(t['targetId'] for t in targets if t.get('type') == 'page' and t.get('url') == launcher.ORIGIN+'/hermes-workspace')
            self.session = self.pipe.call('Target.attachToTarget', {'targetId': self.target, 'flatten': True})['sessionId']
            self.call('Runtime.enable')
            self.call('Page.enable')
            self.wait("document.getElementById('connection')?.textContent==='Connected'")
            self.identity = self.evaluate('({url:location.href,viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,zoom:visualViewport.scale})')
            self.identity.update({'launcher': str(Path.home()/'.local/bin/hermes-workspace'), 'profile': 'existing Hermes pin profile', 'catalog': 'production', 'isolated_server': False, 'startup_handshake': 'exclusive launcher startup lock released before poller pause'})
        except BaseException:
            self.close()
            raise

    def reload_ready(self, timeout=20):
        """Wait for a new document and hydrated input, rather than the old DOM."""
        before = self.evaluate('performance.timeOrigin')
        self.call('Page.reload')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ready = self.evaluate('performance.timeOrigin!==' + json.dumps(before) +
                    '&&document.getElementById("connection")?.textContent==="Connected"'
                    '&&!!document.querySelector("#prompt")&&!document.querySelector("#prompt").disabled')
            except RuntimeError as error:
                # Navigation can retire the evaluation context between request
                # and response. Other application/evaluation errors stay fatal.
                if str(error) != 'browser_protocol_error':
                    raise
            else:
                if ready:
                    return
            time.sleep(.025)
        raise TimeoutError('fresh_production_document_not_hydrated')

    def detach_preserving_document(self):
        """Release observation without closing a document containing user input."""
        self.detached = True
        try:
            if self.pipe:
                self.pipe.call('Target.detachFromTarget', {'sessionId': self.session})
        finally:
            if self.pipe:
                for fd in (self.pipe.read, self.pipe.write):
                    try: os.close(fd)
                    except OSError: pass
                self.pipe = None
            if self.paused:
                try: signal.pidfd_send_signal(self.owner, signal.SIGCONT)
                except ProcessLookupError: pass
                self.paused = False
            if self.owner is not None:
                os.close(self.owner)
                self.owner = None

    def close(self):
        if getattr(self, 'detached', False):
            return
        if self.pipe:
            try: self.pipe.call('Browser.close')
            except (OSError, RuntimeError, TimeoutError): pass
            for fd in (self.pipe.read, self.pipe.write):
                try: os.close(fd)
                except OSError: pass
            self.pipe = None
        if self.paused:
            try: signal.pidfd_send_signal(self.owner, signal.SIGCONT)
            except ProcessLookupError: pass
            self.paused = False
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired: self.process.terminate(); self.process.wait(timeout=5)
        if self.owner is not None:
            os.close(self.owner)
            self.owner = None
