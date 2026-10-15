"""Operator-assisted native review of one verified fresh server-owned kdialog.

Lift only this disposable chooser above the floating review app, then refuse
focus drift. No global rules, clipboard, process launch or import API bypass.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time

CAPTION = 'Select files to copy into Hermes Lab'


def process_identity(pid):
    root = Path('/proc') / str(pid)
    values = dict(line.split(':', 1) for line in (root / 'status').read_text().splitlines() if ':' in line)
    return {'pid': pid, 'uids': [int(value) for value in values['Uid'].split()],
            'parent': int(values['PPid']), 'start': (root / 'stat').read_text().rsplit(')', 1)[1].split()[19],
            'argv': [value.decode() for value in (root / 'cmdline').read_bytes().split(b'\0') if value]}


def path_keys(path):
    if not isinstance(path, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]{1,179}', path) or '..' in Path(path).parts:
        raise ValueError('bounded_ASCII_owned_fixture_path_required')
    result = []
    for char in path:
        if char in '/-.':result.append(('', {'/': 'slash', '-': 'minus', '.': 'period'}[char]))
        elif char == '_':result.append(('SHIFT', 'minus'))
        elif char.isupper():result.append(('SHIFT', char.lower()))
        else:result.append(('', char))
    return result


def chooser_identity(client, process, server, uid):
    expected = ['/usr/bin/kdialog', '--getexistingdirectory', str(Path.home()), CAPTION]
    if (client.get('pid') != process['pid'] or process['parent'] != server['pid']
            or process['uids'] != [uid] * 4 or process['argv'] != expected
            or client.get('class') not in ('kdialog', 'org.kde.kdialog')
            or not (client.get('title', '').startswith(CAPTION) or client.get('title') == 'KDialog')
            or not re.fullmatch(r'0x[0-9a-f]+', client.get('address', ''))):
        raise RuntimeError('exact_owned_native_chooser_required')
    return {'pid': process['pid'], 'start': process['start'], 'address': client['address'],
            'xwayland': bool(client.get('xwayland')), 'server_pid': server['pid']}


class NativePickerDriver:
    def __init__(self, server_pid, server_source, command=None, process_reader=process_identity, clock=time.monotonic, sleep=time.sleep):
        self.process_reader, self.clock, self.sleep = process_reader, clock, sleep
        self.command = command or self._command
        self.uid = os.getuid(); self.server_source = str(Path(server_source).resolve())
        self.server = self.process_reader(server_pid)
        if self.uid == 0 or self.server['uids'] != [self.uid] * 4 or self.server_source not in self.server['argv']:
            raise RuntimeError('actual_unprivileged_production_server_required')
        self.seen = set(); self.target = None
        if self._candidates():raise RuntimeError('preserve_preexisting_native_chooser')

    @staticmethod
    def _command(args):
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3, check=True)
        if len(result.stdout) > 256 * 1024:raise RuntimeError('bounded_native_metadata_required')
        return result.stdout

    def _clients(self):return json.loads(self.command(['/usr/bin/hyprctl', 'clients', '-j']))

    def _server_current(self):
        current = self.process_reader(self.server['pid'])
        if current != self.server:raise RuntimeError('production_server_identity_changed')

    def _candidates(self):
        self._server_current()
        result = []
        for client in self._clients():
            if client.get('class') not in ('kdialog', 'org.kde.kdialog'):continue
            try:process = self.process_reader(client['pid'])
            except (OSError, ValueError, KeyError):continue
            if process['parent'] != self.server['pid']:continue
            result.append(chooser_identity(client, process, self.server, self.uid))
        return result

    def _current(self):
        choices = self._candidates()
        if len(choices) != 1 or choices[0] != self.target:raise RuntimeError('native_chooser_target_changed')

    def _target_client(self):
        self._current()
        clients = [row for row in self._clients() if row.get('address') == self.target['address']]
        if len(clients) != 1 or chooser_identity(clients[0], self.process_reader(self.target['pid']), self.server, self.uid) != self.target:
            raise RuntimeError('native_chooser_target_changed')
        return clients[0]

    def _active(self):
        active = json.loads(self.command(['/usr/bin/hyprctl', 'activewindow', '-j']))
        if active.get('pid') != self.target['pid'] or active.get('address') != self.target['address']:
            raise RuntimeError('native_chooser_focus_changed')

    def _window_dispatch(self, code):
        if self.clock() > self.deadline:raise TimeoutError('bounded_native_picker_deadline')
        self._current()
        response = self.command(['/usr/bin/hyprctl', 'dispatch', code]).strip()
        if response != 'ok':raise RuntimeError('owned_native_window_dispatch_not_acknowledged')

    def _lift_once(self):
        client = self._target_client()
        if type(client.get('floating')) is not bool:raise RuntimeError('native_chooser_floating_state_unknown')
        was_floating = client['floating']
        window = json.dumps('address:' + self.target['address'])
        if not was_floating:
            self._window_dispatch('hl.dsp.window.float({action="on",window=' + window + '})')
            if self._target_client().get('floating') is not True:raise RuntimeError('owned_chooser_did_not_float')
        self._window_dispatch('hl.dsp.focus({window=' + window + '})')
        self._current(); self._active()
        return {'floating_before': was_floating, 'float_applied': not was_floating, 'addressed_focus_applied': True,
                'scope': 'Operator-only lift of this verified disposable chooser; unassisted production dialog parenting remains unverified.'}

    def _key(self, mods, key, allow_exit=False):
        if self.clock() > self.deadline:raise TimeoutError('bounded_native_picker_deadline')
        self._current(); self._active()
        code = 'hl.dsp.send_shortcut({mods=' + json.dumps(mods) + ',key=' + json.dumps(key) + ',window=' + json.dumps('address:' + self.target['address']) + '})'
        response = self.command(['/usr/bin/hyprctl', 'dispatch', code]).strip()
        if response != 'ok':raise RuntimeError('targeted_native_shortcut_not_acknowledged')
        self.keys += 1
        self.sleep(.025)
        if allow_exit and not self._candidates():return False
        self._current(); return True

    def __call__(self, phase, source):
        if phase not in ('cancel_picker', 'preview_cancel', 'commit'):raise ValueError('fixed_picker_phase_required')
        keys = path_keys(source)
        self.deadline = self.clock() + 25; self.keys = 0
        while self.clock() < self.deadline:
            choices = self._candidates()
            if len(choices) > 1:raise RuntimeError('unique_owned_native_chooser_required')
            if choices:
                self.target = choices[0]
                if (self.target['pid'], self.target['start']) in self.seen:raise RuntimeError('fresh_native_chooser_required')
                break
            self.sleep(.1)
        else:raise TimeoutError('actual_native_chooser_not_observed')
        self.seen.add((self.target['pid'], self.target['start']))
        try:
            lift = self._lift_once()
            if phase == 'cancel_picker':self._key('', 'Escape', allow_exit=True)
            else:
                self._key('CTRL', 'l')
                self._key('CTRL', 'a')
                for mods, key in keys:self._key(mods, key)
                still_open = self._key('', 'Return', allow_exit=True)
                if still_open:
                    self.sleep(.25)
                    self._key('', 'Return', allow_exit=True)
            while self.clock() < self.deadline and self._candidates():self.sleep(.1)
            if self._candidates():raise TimeoutError('native_chooser_did_not_finish')
            return {'actual_native_chooser': True, 'phase': phase, 'target': self.target,
                    'operator_window_lift': lift,
                    'targeted_shortcuts': self.keys, 'input_scope': 'native compositor protocol events; not physical user input',
                    'result_scope': 'Chooser closed; caller must verify actual preview/cancel and copied snapshot before declaring import success'}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, TimeoutError):
            # Close this exact surviving chooser without keyboard focus/input.
            # A focus drift must never trigger repeated focus stealing. If its
            # ownership changed, leave it untouched for operator review.
            try:
                self.deadline = self.clock() + 3
                window = json.dumps('address:' + self.target['address'])
                self._window_dispatch('hl.dsp.window.close({window=' + window + '})')
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, TimeoutError):pass
            raise
