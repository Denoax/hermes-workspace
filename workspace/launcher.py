"""Native single-instance app launcher; cookie bootstrap uses a private CDP pipe."""
import fcntl
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import shlex
import subprocess
import sys
import time
import urllib.request

ORIGIN='http://127.0.0.1:18791'
STATE=Path.home()/'.local/state/hermes-workspace'
PROFILE=Path.home()/'.var/app/com.brave.Browser/config/hermes-workspace-browser'


def prepare_control_directory(parent=None):
    """Create the normal-user systemd control path required after login/reboot.

    The protected window unit validates this same operator-owned directory. This
    does not change native authority or fix a missing protected control socket.
    A parent override is only for isolated filesystem contract tests.
    """
    if os.getuid() != 1000 or os.geteuid() != 1000:
        raise RuntimeError('fixed_normal_user_control_directory_only')
    path = Path('/run/user/1000/systemd') if parent is None else Path(parent)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(path, flags)
    try:
        facts = os.fstat(descriptor)
        if facts.st_uid != 1000 or facts.st_mode & 0o022:
            raise RuntimeError('untrusted_user_control_parent')
        try:
            os.mkdir('user.control', 0o700, dir_fd=descriptor)
        except FileExistsError:
            pass
        child = os.open('user.control', flags, dir_fd=descriptor)
        try:
            facts = os.fstat(child)
            if facts.st_uid != 1000 or facts.st_mode & 0o022:
                raise RuntimeError('untrusted_user_control_directory')
        finally:
            os.close(child)
    finally:
        os.close(descriptor)


def owns_browser(pid):
    try:
        directory=Path('/proc')/str(pid)
        if directory.stat().st_uid!=os.getuid():return False
        arguments=[part for arg in (directory/'cmdline').read_text().split('\0') for part in shlex.split(arg)]
        return '--user-data-dir='+str(PROFILE) in arguments and not any(x.startswith('--type=') for x in arguments)
    except (OSError,ValueError):return False


def close_browser():
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit() or not owns_browser(directory.name):continue
        descriptor=None
        try:
            descriptor=os.pidfd_open(int(directory.name))
            if not owns_browser(directory.name):continue
            signal.pidfd_send_signal(descriptor,signal.SIGTERM)
            if not select.select([descriptor],[],[],10)[0]:
                signal.pidfd_send_signal(descriptor,signal.SIGKILL)
                if not select.select([descriptor],[],[],3)[0]:raise RuntimeError('owned_browser_did_not_exit')
        except ProcessLookupError:pass
        finally:
            if descriptor is not None:os.close(descriptor)


class Pipe:
    def __init__(self,read,write):self.read=read;self.write=write;self.buffer=b'';self.counter=0;self.on_event=None
    def call(self,method,params=None,session=None):
        self.counter+=1;request={'id':self.counter,'method':method,'params':params or {}}
        request_id=self.counter
        if session:request['sessionId']=session
        raw=json.dumps(request).encode()+b'\0'
        while raw:raw=raw[os.write(self.write,raw):]
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            while b'\0' in self.buffer:
                raw,self.buffer=self.buffer.split(b'\0',1);reply=json.loads(raw)
                if reply.get('id')==request_id:
                    if 'error' in reply:raise RuntimeError('browser_protocol_error')
                    return reply['result']
                if self.on_event and 'method' in reply:self.on_event(reply)
            if select.select([self.read],[],[],.25)[0]:
                chunk=os.read(self.read,65536)
                if not chunk:raise RuntimeError('browser_pipe_closed')
                self.buffer+=chunk
                if len(self.buffer)>2*1024*1024:raise RuntimeError('browser_reply_limit')
        raise TimeoutError('browser_boot_timeout')


def monitor_work_area(monitor):
    """Return compositor logical coordinates, accounting for scale and reserved edges."""
    scale = float(monitor.get('scale', 1))
    width, height = float(monitor['width']), float(monitor['height'])
    if not all(math.isfinite(value) and value > 0 for value in (scale, width, height)):
        raise ValueError('invalid_monitor_geometry')
    if int(monitor.get('transform', 0)) % 2:
        width, height = height, width
    width, height = width / scale, height / scale
    reserved = monitor.get('reserved', [0, 0, 0, 0])
    if len(reserved) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 for value in reserved):
        raise ValueError('invalid_monitor_reserved_edges')
    left, top, right, bottom = reserved
    x, y = float(monitor['x']) + left, float(monitor['y']) + top
    width, height = width - left - right, height - top - bottom
    if width < 1 or height < 1 or not math.isfinite(x) or not math.isfinite(y):
        raise ValueError('invalid_monitor_work_area')
    return x, y, width, height


def requested_window_size(monitor, width=1320, height=900):
    _, _, available_width, available_height = monitor_work_area(monitor)
    return max(1, min(width, int(available_width - 32))), max(1, min(height, int(available_height - 32)))


def surface_inside_monitor(client, monitor):
    x, y, width, height = monitor_work_area(monitor)
    cx, cy = client['at']
    cw, ch = client['size']
    return cw > 0 and ch > 0 and cx >= x - 1 and cy >= y - 1 and cx + cw <= x + width + 1 and cy + ch <= y + height + 1


def position_browser_window(pipe, target, client):
    """Configure only this profile's window, then center AFTER Chromium's bounds."""
    address = client.get('address', '')
    if not re.fullmatch(r'0x[0-9a-f]+', address) or not owns_browser(client.get('pid')):
        raise RuntimeError('invalid_window_identity')
    monitors = json.loads(subprocess.check_output(['/usr/bin/hyprctl', 'monitors', '-j'], text=True))
    monitor = next((row for row in monitors if row['id'] == client['monitor']), None)
    if monitor is None:
        raise RuntimeError('owned_window_monitor_missing')
    width, height = requested_window_size(monitor)
    window = 'address:' + address
    def dispatch(command):
        subprocess.run(['/usr/bin/hyprctl', 'dispatch', command], capture_output=True, check=True, timeout=3)
    if client.get('fullscreen'):
        mode = 'maximized' if client['fullscreen'] == 1 else 'fullscreen'
        dispatch('hl.dsp.window.fullscreen({mode=' + json.dumps(mode) + ',action="toggle",window=' + json.dumps(window) + '})')
    if not client.get('floating'):
        dispatch('hl.dsp.window.float({action="toggle",window=' + json.dumps(window) + '})')
    dispatch('hl.dsp.window.resize({x=' + str(width) + ',y=' + str(height) + ',relative=false,window=' + json.dumps(window) + '})')
    window_id = pipe.call('Browser.getWindowForTarget', {'targetId': target})['windowId']
    pipe.call('Browser.setWindowBounds', {'windowId': window_id, 'bounds': {'width': width, 'height': height}})
    # On XWayland the Chromium configure can reset position after its reply.
    # Final compositor placement and repeated readback must follow that request.
    stable = 0
    for attempt in range(20):
        if attempt == 0 or stable == 0:
            dispatch('hl.dsp.window.center({window=' + json.dumps(window) + '})')
        time.sleep(.06)
        rows = json.loads(subprocess.check_output(['/usr/bin/hyprctl', 'clients', '-j'], text=True))
        current = next((row for row in rows if row.get('address') == address), None)
        if current is None or not owns_browser(current.get('pid')):
            raise RuntimeError('owned_window_identity_changed')
        monitors = json.loads(subprocess.check_output(['/usr/bin/hyprctl', 'monitors', '-j'], text=True))
        monitor = next((row for row in monitors if row['id'] == current['monitor']), None)
        stable = stable + 1 if monitor and surface_inside_monitor(current, monitor) else 0
        if stable >= 2:
            return
    raise RuntimeError('owned_window_remains_outside_monitor')


def focus():
    result=subprocess.run(['/usr/bin/hyprctl','clients','-j'],capture_output=True,text=True,timeout=4)
    if result.returncode:return False
    for client in json.loads(result.stdout):
        pid=client.get('pid')
        try:
            owned=owns_browser(pid)
        except (FileNotFoundError,PermissionError):owned=False
        if owned and client.get('title')=='Hermes Workspace':
            address=client.get('address','')
            if not re.fullmatch(r'0x[0-9a-f]+',address):raise RuntimeError('invalid_window_identity')
            command='hl.dsp.focus({window="address:'+address+'"})'
            subprocess.run(['/usr/bin/hyprctl','dispatch',command],capture_output=True,check=True,timeout=4)
            return True
    return False


def browser(headless=False, audio_sink=None):
    if audio_sink is not None and not re.fullmatch(r"hermes_parity_[a-z0-9_]+", audio_sink):raise ValueError("invalid_review_audio_sink")
    credential=(STATE/'client-cookie').read_text().strip()
    PROFILE.mkdir(mode=0o700,parents=True,exist_ok=True)
    # flatpak run does not forward arbitrary descriptors. Owner-only FIFOs in
    # this app's private config connect to Chromium's inherited 3/4 pipe ends.
    channel=PROFILE.parent/('hermes-pipe-'+os.urandom(12).hex())
    channel.mkdir(mode=0o700)
    incoming=channel/'in';outgoing=channel/'out'
    os.mkfifo(incoming,0o600);os.mkfifo(outgoing,0o600)
    boot=channel/'boot.sh'
    # The native picker attests its parent through XRes, so select X11 explicitly.
    browser_args=['/app/bin/brave','--ozone-platform=x11','--remote-debugging-pipe','--user-data-dir='+str(PROFILE),
                  '--class=HermesWorkspace','--no-first-run','--no-default-browser-check','--disable-background-mode','--app='+ORIGIN+'/hermes-workspace']
    if headless:browser_args.append('--headless=new')
    boot.write_text('#!/bin/sh\nexec 3<'+shlex.quote(str(incoming))+'\nexec 4>'+shlex.quote(str(outgoing))+
                    '\nexec '+shlex.join(browser_args)+'\n');boot.chmod(0o700)
    receive_parent=os.open(outgoing,os.O_RDWR|os.O_NONBLOCK)
    with (STATE/'browser.log').open('ab') as log:
        process=subprocess.Popen(['/usr/bin/flatpak','run',*(['--env=PULSE_SINK='+audio_sink] if audio_sink else []),'--command=/bin/sh','com.brave.Browser',str(boot)],
                                 stdin=subprocess.DEVNULL,stdout=log,stderr=log)
    deadline=time.monotonic()+20
    while True:
        try:send_parent=os.open(incoming,os.O_WRONLY|os.O_NONBLOCK);break
        except OSError:
            if process.poll() is not None or time.monotonic()>deadline:
                os.close(receive_parent);raise RuntimeError('workspace_browser_unavailable')
            time.sleep(.1)
    os.set_blocking(receive_parent,True);os.set_blocking(send_parent,True)
    pipe=Pipe(receive_parent,send_parent)
    try:
        pipe.call('Browser.getVersion')
        pipe.call('Storage.clearCookies')
        pipe.call('Storage.setCookies',{'cookies':[{'name':'hermes_session','value':credential,
            'domain':'127.0.0.1','path':'/hermes-workspace','httpOnly':True,'secure':False,'sameSite':'Strict'}]})
        targets=pipe.call('Target.getTargets')['targetInfos']
        for target in targets:
            if target.get('type')=='page' and target.get('url','').startswith(ORIGIN):
                session=pipe.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True})['sessionId']
                pipe.call('Page.reload',{},session)
                deadline=time.monotonic()+5
                while not headless and time.monotonic()<deadline:
                    clients=json.loads(subprocess.check_output(['/usr/bin/hyprctl','clients','-j'],text=True))
                    matches=[x for x in clients if x.get('title')=='Hermes Workspace' and owns_browser(x.get('pid'))]
                    if matches:
                        position_browser_window(pipe, target['targetId'], matches[0])
                        break
                    time.sleep(.1)
        return pipe,process
    except BaseException:
        os.close(receive_parent);os.close(send_parent);raise
    finally:
        incoming.unlink();outgoing.unlink();boot.unlink();channel.rmdir()


def main():
    if os.geteuid()==0 or sys.argv[1:] not in ([],['--close']):raise SystemExit('fixed_normal_user_launcher_only')
    if sys.argv[1:]==['--close']:close_browser();return
    os.umask(0o077);STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    owned=None
    with (STATE/'launcher.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        prepare_control_directory()
        subprocess.run(['/usr/bin/systemctl','--user','start','hermes-workspace.service'],check=True,timeout=10)
        deadline=time.monotonic()+8
        while True:
            try:
                with urllib.request.urlopen(ORIGIN+'/health',timeout=.5) as response:
                    if json.load(response).get('application')!='hermes-workspace':raise RuntimeError('port_collision')
                break
            except OSError:
                if time.monotonic()>deadline:raise RuntimeError('workspace_service_unavailable')
                time.sleep(.15)
        if not focus():owned=browser()
    if owned:
        pipe,process=owned
        try:
            while any(target.get('type')=='page' and target.get('url','').startswith(ORIGIN)
                      for target in pipe.call('Target.getTargets')['targetInfos']):
                time.sleep(2)
        except (RuntimeError,TimeoutError):pass
        finally:os.close(pipe.read);os.close(pipe.write)


if __name__=='__main__':main()
