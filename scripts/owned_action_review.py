"""Composable real-pin permission/search/import/delete probes on new owned records.

Importing this module does nothing to the app. The caller owns ProductionPin,
native-input qualification, fixture creation, recording lifecycle and cleanup.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

ID = re.compile(r'[0-9a-f]{32}\Z')
PREFIX = re.compile(r'V5review-[0-9a-f]{8}\Z')
CATALOG = Path.home() / 'HermesLab/catalog.sqlite3'


def digest(value):return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
def check(condition, code):
    if not condition:raise RuntimeError(code)


def owned_navigation(record, projects, sessions):
    check(record.get('status') == 'PASS_SCOPED_TECHNICAL' and bool(PREFIX.fullmatch(record.get('prefix', ''))), 'owned_navigation_receipt_required')
    prefix = record['prefix']
    suffix = record.get('nonce_location') == 'suffix'
    for key, actual, label in (('projects', projects, 'label'), ('sessions', sessions, 'title')):
        found = {row['id']: row for row in actual}
        expected = record.get(key, [])
        check(bool(expected), 'owned_navigation_inventory_required')
        for row in expected:
            identifier = row.get('id', '')
            marked = row[label].endswith(' · ' + prefix) if suffix else row[label].startswith(prefix + ' · ')
            check(bool(ID.fullmatch(identifier)) and marked, 'positive_owned_navigation_identity_required')
            check(identifier in found and found[identifier][label] == row[label], 'owned_navigation_changed_preserve_it')
            if key == 'sessions':check(found[identifier]['project'] == row['project'], 'owned_session_moved_preserve_it')
    return prefix


def disposable_session(case, sessions, snapshot, draft, jobs, attachment_count):
    row = next((row for row in sessions if row['id'] == case.get('delete_session')), None)
    check(case.get('delete_session') in case.get('created_session_ids', []) and bool(ID.fullmatch(case.get('delete_session', ''))), 'new_created_delete_receipt_required')
    check(row and row['title'] == case['nonce'] + ' · Empty delete case' and row['project'] == case['project_id'], 'delete_case_ownership_changed')
    check(not snapshot.get('messages') and not snapshot.get('runs') and not jobs, 'delete_case_acquired_content_preserve_it')
    check(draft.get('text') == '' and draft.get('mode') == 'chat' and attachment_count == 0, 'delete_case_acquired_draft_preserve_it')
    return row['id']


def empty_new_draft(storage):
    if storage.get('hermes:new-draft'):return False
    raw = storage.get('hermes:draft-attachments:v1:new')
    if raw is None:return True
    try:
        value = json.loads(raw)
        return value.get('version') == 1 and value.get('ids') == []
    except (ValueError, AttributeError):return False


def empty_storage_restoration(original, current):
    """Only reconcile absent versus empty new-draft bookkeeping, never text."""
    check(set(original) == set(current), 'original_storage_inventory_changed')
    changes = {}
    for key, before in original.items():
        after = current[key]
        if before == after:continue
        check(key == 'hermes:new-draft' and before in (None, '') and after in (None, ''),
              'original_draft_attachment_or_sound_state_changed')
        changes[key] = {'expected': after, 'value': before}
    return changes


def selected_owned_session(case, role, view, sessions, ui_title):
    suffix = {'permission_session': 'Permission checks', 'other_session': 'Scope isolation',
              'delete_session': 'Empty delete case', 'import_session': 'Import preview'}[role]
    sid = case.get(role); expected = case['nonce'] + ' · ' + suffix
    matching = [row for row in sessions if row['title'] == expected]
    project = case.get('import_project_id') if role == 'import_session' else case.get('project_id')
    check(sid in case.get('created_session_ids', []) and view.get('session_id') == sid and view.get('project_id') == project,
          'selected_view_is_not_exact_created_case')
    check(len(matching) == 1 and matching[0]['id'] == sid and matching[0]['project'] == project and ui_title == expected,
          'selected_UI_is_not_exact_created_case')
    return sid


def fixture_text(nonce):
    check(bool(re.fullmatch(r'V5review-[0-9a-f]{8}-actions-[0-9a-f]{8}', nonce)), 'owned_action_nonce_required')
    return {'README.md': '# Harmless Hermes import verification\n' + nonce + '\n',
            'notes/context.txt': 'Only newly generated verification text. ' + nonce + '\n'}


def make_import_fixture(parent, nonce):
    texts = fixture_text(nonce)
    root = Path(parent) / (nonce + '-import-source')
    check('private-state' not in root.parts and root.parent.resolve() == Path(parent).resolve(), 'nonsensitive_owned_fixture_parent_required')
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, text in texts.items():
        target = root / name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open('x') as stream:stream.write(text)
        target.chmod(0o600)
    info = root.stat()
    return {'nonce': nonce, 'root': str(root.resolve()), 'device': info.st_dev, 'inode': info.st_ino,
            'files': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in texts.items()}}


def verify_import_fixture(receipt):
    texts = fixture_text(receipt['nonce']); root = Path(receipt['root'])
    check(root.is_absolute() and root.name == receipt['nonce'] + '-import-source' and 'private-state' not in root.parts, 'owned_fixture_path_required')
    check(not any(path.is_symlink() for path in (root, *root.parents)), 'fixture_symlink_refused')
    info = root.stat()
    check(info.st_uid == os.getuid() and (info.st_dev, info.st_ino) == (receipt['device'], receipt['inode']), 'owned_fixture_directory_changed')
    actual = {path.relative_to(root).as_posix(): path for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    check(set(actual) == set(texts), 'fixture_inventory_changed')
    for name, text in texts.items():
        path = actual[name]
        check(not path.is_symlink() and path.read_bytes() == text.encode() and receipt['files'][name] == hashlib.sha256(text.encode()).hexdigest(), 'fixture_bytes_changed')
    return texts


def expected_snapshot(texts):
    rows = [{'path': name, 'text': text, 'bytes': len(text.encode()), 'sha256': hashlib.sha256(text.encode()).hexdigest()}
            for name, text in sorted(texts.items())]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_import_ticket(project, ticket, fixture):
    check(bool(ID.fullmatch(project)) and bool(ID.fullmatch(ticket)), 'positive_owned_import_pair_required')
    verify_import_fixture(fixture)
    check(not any(path.is_symlink() for path in (CATALOG, *CATALOG.parents)), 'catalog_symlink_refused')
    before = CATALOG.stat()
    check(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1 and not before.st_mode & 0o077, 'existing_owner_only_production_catalog_required')
    connection = sqlite3.connect(CATALOG.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        connection.execute('PRAGMA query_only=ON')
        row = connection.execute('SELECT source,manifest,expires FROM imports WHERE id=? AND project=?', (ticket, project)).fetchone()
    finally:connection.close()
    after = CATALOG.stat()
    check((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), 'catalog_identity_changed')
    check(row is not None and row[2] > time.time(), 'new_owned_import_ticket_missing_or_expired')
    manifest = json.loads(row[1])
    check(Path(row[0]) == Path(fixture['root']) and manifest == fixture['files'], 'native_picker_selected_another_source_no_copy')
    return {'ticket_id': ticket, 'project_id': project, 'files': manifest,
            'source_root_matches': True, 'manifest_matches': True, 'read_only_ticket_query': True}


class OwnedActionReview:
    def __init__(self, browser, rpc, output, navigation):
        self.b, self.rpc = browser, lambda method, fields=None: rpc(browser, method, fields or {})
        self.output = Path(output); self.output.mkdir(mode=0o700, parents=True, exist_ok=True)
        check(not self.output.is_symlink() and not self.output.stat().st_mode & 0o077, 'private_action_review_output_required')
        check(browser.identity.get('url') == 'http://127.0.0.1:18791/hermes-workspace' and browser.identity.get('catalog') == 'production' and browser.identity.get('isolated_server') is False, 'actual_production_pin_required')
        self.prefix = owned_navigation(navigation, self.rpc('workspace.list'), self.rpc('session.list'))
        check(not browser.evaluate("!!document.querySelector('#cancel-response,.recording-indicator') || document.querySelectorAll('#composer .attachment').length>0"), 'preserve_live_run_recording_or_unsent_attachments')
        self.original_view = self.rpc('view.read')
        check(isinstance(self.original_view, dict) and not self.original_view.get('editor') and not self.original_view.get('file_path') and not self.original_view.get('files_open'), 'preserve_open_file_editor_before_probe')
        sid = (self.original_view or {}).get('session_id')
        self.original_draft = self.rpc('draft.read', {'session_id': sid}) if sid else None
        self.storage_keys = ['hermes-ui:sounds', 'hermes-ui:interface-volume', 'hermes:new-draft',
                             'hermes:draft-attachments:v1:new', 'hermes:draft-attachments:v1:' + (sid or 'new')]
        self.original_storage = self._storage()
        self.original_filter = browser.evaluate("document.querySelector('.rail-search input')?.value??''")
        check(self.original_draft is None or browser.evaluate("document.querySelector('#prompt').value") == self.original_draft['text'], 'wait_for_original_draft_save_before_probe')
        self.case = {'nonce': self.prefix + '-actions-' + uuid.uuid4().hex[:8], 'created_session_ids': []}
        self.report = {'status': 'PARTIAL', 'scope': 'actual production pin18791; operator proposals and trusted UI approval, no model inference',
                       'pin': browser.identity, 'case': self.case, 'checks': {}, 'actions': [], 'attachments_created': [], 'captures': [],
                       'gaps': {'guest': 'BLOCKED by current native qualification; no host fallback',
                                'R05_inline_citation_preview': 'UNVERIFIED: requires a genuine assistant citation and rendered hover review; this helper generates no model answer',
                                'native_picker': 'Pending actual chooser driver; no substitute import API',
                                'human_motion_and_listening': 'UNVERIFIED; silent recordings are technical evidence only'}}
        self.save()

    def _storage(self):return self.b.evaluate('Object.fromEntries(' + json.dumps(self.storage_keys) + '.map(k=>[k,localStorage.getItem(k)]))')
    def save(self):
        target = self.output / 'actions.json'; target.write_text(json.dumps(self.report, indent=2) + '\n'); target.chmod(0o600)

    def reload_ready(self):
        # Coordinate proof and document observers belong to the old document.
        # Until a fresh native qualification, pointer calls use the existing
        # browser protocol path rather than an inherited compositor mapping.
        native = getattr(self.b, '_native_input', None)
        if native:native.close()
        self.b._native_input = None
        self.b._native_coordinates = None
        self.b._native_diagnostics = {}
        self.b.reload_ready()

    def button(self, text, scope='document'):
        key = 'owned-' + uuid.uuid4().hex
        self.b.wait("(()=>{const root=" + scope + ";return !!root&&[...root.querySelectorAll('button')].some(e=>e.textContent.trim()===" + json.dumps(text) + "&&!e.disabled)})()")
        self.b.evaluate("(()=>{const e=[..." + scope + ".querySelectorAll('button')].find(e=>e.textContent.trim()===" + json.dumps(text) + ");if(!e)throw Error('owned_button_missing');e.scrollIntoView({block:'center'});e.dataset.ownedProbe=" + json.dumps(key) + "})()")
        self.b.click('[data-owned-probe="' + key + '"]')

    def select_value(self, selector, value, values):
        self.b.wait('!document.querySelector(' + json.dumps(selector) + ').disabled')
        self.b.click(selector)
        for _ in values:self.b.key('ArrowUp')
        for _ in range(values.index(value)):self.b.key('ArrowDown')
        self.b.key('Enter')
        self.b.wait('document.querySelector(' + json.dumps(selector) + ').value===' + json.dumps(value))

    def create(self):
        before_projects = {row['id'] for row in self.rpc('workspace.list')}
        project = self.rpc('workspace.create', {'label': self.case['nonce'] + ' · Action review'})
        check(bool(ID.fullmatch(project['id'])) and project['id'] not in before_projects, 'new_project_creation_receipt_required')
        self.case['project_id'] = project['id']; self.save()
        before_sessions = {row['id'] for row in self.rpc('session.list')}
        for role, title in (('permission_session', 'Permission checks'), ('other_session', 'Scope isolation'), ('delete_session', 'Empty delete case')):
            row = self.rpc('session.create', {'project_id': project['id'], 'arm': 'normal'})
            check(bool(ID.fullmatch(row['id'])) and row['id'] not in before_sessions, 'new_session_creation_receipt_required')
            self.case[role] = row['id']; self.case['created_session_ids'].append(row['id']); before_sessions.add(row['id']); self.save()
            self.rpc('session.rename', {'session_id': row['id'], 'title': self.case['nonce'] + ' · ' + title})
        return self.case

    def select(self, role):
        sid = self.case[role]
        check(sid in self.case['created_session_ids'], 'only_new_owned_sessions_selectable')
        view = {**self.original_view, 'project_id': self.case['project_id'], 'session_id': sid, 'arm': 'normal'}
        self.rpc('view.write', {'state': view}); self.reload_ready()
        self.filter_owned()
        return sid

    def filter_owned(self):
        self.b.click('.rail-search input'); self.b.key('a', 'KeyA', 2); self.b.call('Input.insertText', {'text': self.case['nonce']})
        self.b.wait("[...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')].every(e=>e.textContent.includes(" + json.dumps(self.case['nonce']) + '))')

    def require_native(self):
        check(getattr(self.b, '_native_diagnostics', {}).get('status') == 'PASS' and getattr(self.b, '_native_coordinates', None), 'qualify_current_native_pointer_before_motion')

    def assert_selected(self, role):
        title = self.b.evaluate("document.querySelector('.session-row.selected>button:first-child')?.getAttribute('title')")
        return selected_owned_session(self.case, role, self.rpc('view.read'), self.rpc('session.list'), title)

    def request(self, action):
        self.assert_selected('permission_session')
        sid = self.case['permission_session']
        row = self.rpc('permissions.request', {'session_id': sid, 'run_id': None, 'request_id': uuid.uuid4().hex, 'action': action})
        self.report['actions'].append({'id': row['id'], 'type': row['type'], 'resource': row['resource']}); self.save()
        return row

    def expect_denied(self, method, fields, expected):
        envelope = self.b.evaluate("(async()=>{const a=await(await fetch('/hermes-workspace/api/bootstrap')).json();const r=await fetch('/hermes-workspace/api/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':a.csrf},body:JSON.stringify({version:1,method:" + json.dumps(method) + ',fields:' + json.dumps(fields) + "})});const d=await r.json();return {status:r.status,error:typeof d.error==='string'?d.error:null}})()")
        check(envelope == {'status': 409, 'error': expected}, 'exact_server_permission_denial_not_observed')
        return envelope

    def decide(self, row, text):
        self.assert_selected('permission_session')
        resource = row['resource']; key = 'card-' + uuid.uuid4().hex
        self.b.wait("[...document.querySelectorAll('.approval-card')].some(e=>e.dataset.state==='pending'&&e.textContent.includes(" + json.dumps(resource) + '))')
        self.b.evaluate("(()=>{const e=[...document.querySelectorAll('.approval-card')].find(e=>e.dataset.state==='pending'&&e.textContent.includes(" + json.dumps(resource) + '));e.dataset.ownedProbe=' + json.dumps(key) + ";e.scrollIntoView({block:'center'})})()")
        self.button(text, "document.querySelector('[data-owned-probe=\"" + key + "\"]')")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            current = next(item for item in self.rpc('permissions.read', {'session_id': self.case['permission_session']})['actions'] if item['id'] == row['id'])
            if current['state'] in ('completed', 'denied', 'failed', 'revoked'):return current
            time.sleep(.4)
        raise RuntimeError('bounded_owned_action_result_deadline')

    def permissions(self):
        self.assert_selected('permission_session')
        sid, project = self.case['permission_session'], self.case['project_id']
        check(self.rpc('permissions.read', {'session_id': sid})['mode'] == 'chat_only', 'fresh_conversation_default_denial_missing')
        denied = self.request({'type': 'workspace.write', 'path': 'blocked.txt', 'text': 'Must not be written', 'expected_sha256': None})
        check(denied['state'] == 'denied', 'default_write_not_denied')
        self.report['checks']['default_execute_denied'] = self.expect_denied('actions.execute', {'session_id': sid, 'action_id': denied['id']}, 'action_not_approved_denied')
        self.report['checks']['legacy_write_denied'] = self.expect_denied('workspace.file.write', {'project_id': project, 'relative_path': 'bypass.txt', 'text': 'Must not be written', 'expected_sha256': None}, 'scoped_action_required')
        self.report['checks']['microphone_default_denied'] = self.expect_denied('recording.authorize', {'session_id': sid}, 'permission_required_microphone')
        check(self.rpc('workspace.files', {'project_id': project})['files'] == [], 'denied_action_produced_file')
        self.select_value('#permissions-mode', 'ask', ['chat_only', 'ask', 'workspace_agent'])
        row = self.request({'type': 'workspace.write', 'path': 'denied.txt', 'text': 'Must not be written', 'expected_sha256': None})
        check(self.decide(row, 'Deny')['state'] == 'denied', 'explicit_deny_failed')
        self.report['checks']['explicit_deny_execute_denied'] = self.expect_denied('actions.execute', {'session_id': sid, 'action_id': row['id']}, 'action_not_approved_denied')
        text = 'print(' + json.dumps(self.case['nonce']) + ')\n'
        row = self.request({'type': 'workspace.write', 'path': 'program.py', 'text': text, 'expected_sha256': None})
        written = self.decide(row, 'Allow once'); check(written['state'] == 'completed' and written['result']['sha256'] == hashlib.sha256(text.encode()).hexdigest(), 'owned_write_once_failed')
        check(self.rpc('actions.execute', {'session_id': sid, 'action_id': row['id']})['result'] == written['result'], 'completed_action_replay_changed')
        self.report['checks']['write_once_and_idempotent_replay'] = written
        self.report['checks']['wrong_session_denied'] = self.expect_denied('actions.execute', {'session_id': self.case['other_session'], 'action_id': row['id']}, 'unknown_owned_action')
        self.b.key('Escape'); self.b.click('#settings-toggle')
        self.b.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'")
        self.b.evaluate("(()=>{const l=[...document.querySelectorAll('.permission-setting')].find(e=>e.textContent.includes('Read project files'));l.querySelector('input').dataset.ownedRead='true'})()")
        self.b.click('[data-owned-read]')
        self.b.wait("document.querySelector('#settings-permissions-mode').value==='custom'")
        custom = self.rpc('permissions.read', {'session_id': sid}); check(custom['capabilities']['read'] and not custom['capabilities']['write'], 'custom_scope_not_applied')
        self.b.key('Escape')
        for model in ('abliterated', 'normal'):
            self.select_value('#model-picker', model, ['normal', 'abliterated'])
            self.reload_ready()
            self.filter_owned()
            policy = self.rpc('permissions.read', {'session_id': sid})
            check(policy['mode'] == 'custom' and policy['capabilities'] == custom['capabilities'], 'custom_scope_lost_on_model_switch_reload')
        self.report['checks']['custom_persists_across_models_reload'] = True
        self.select_value('#permissions-mode', 'ask', ['chat_only', 'ask', 'workspace_agent'])
        self.report['checks']['owned_only_workspace_files'] = self.rpc('workspace.files', {'project_id': project})['files'] == ['program.py']; self.save()

    def search_motion(self, recording):
        self.assert_selected('permission_session')
        self.require_native()
        self.b.click('#plus-menu'); self.button('⌕ Search Wikipedia', "document.querySelector('.action-menu')")
        self.b.wait("document.querySelector('dialog[open] h2')?.textContent==='Search Wikipedia'")
        self.b.click('dialog[open] input'); self.b.call('Input.insertText', {'text': 'Linux kernel'})
        before = {row['id'] for row in self.rpc('permissions.read', {'session_id': self.case['permission_session']})['actions']}
        self.button('Review search', "document.querySelector('dialog[open]')")
        self.b.wait("!!document.querySelector('.approval-card[data-state=\"pending\"]')")
        action = next(row for row in self.rpc('permissions.read', {'session_id': self.case['permission_session']})['actions'] if row['id'] not in before and row['type'] == 'search.wikipedia')
        self.report['actions'].append({'id': action['id'], 'type': action['type'], 'resource': action['resource']}); self.save()
        result = self.decide(action, 'Allow once'); check(result['state'] == 'completed' and result['result']['provider'] == 'Wikipedia' and result['result']['sources'], 'actual_Wikipedia_result_missing')
        self.report['checks']['real_Wikipedia_search'] = result
        attachment = result['result'].get('attachment')
        if attachment:self.report['attachments_created'].append(attachment['id']); self.save()
        self.b.wait("!!document.querySelector('[data-slot=\"web-search-trigger\"]')")
        recording.segment('wikipedia_sources')
        from scripts.probe_v4_visual import move
        stack = '[data-slot="web-search-trigger"] [data-slot="web-search-stack"]'
        away = self.b.rect('#settings-toggle')
        move(self.b, away['x'] + away['width'] / 2, away['y'] + away['height'] / 2); recording.hold(.7)
        baseline = self.b.rect(stack)['width']; rect = self.b.rect(stack)
        move(self.b, rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2); recording.hold(.7)
        self.report['checks']['real_source_fan_width_increased'] = self.b.rect(stack)['width'] > baseline
        trigger = '[data-slot="web-search-trigger"]'
        self.b.click(trigger); recording.hold(.25); self.b.click(trigger); recording.hold(.15); self.b.click(trigger); recording.hold(.8)
        if len(result['result']['sources']) >= 4:
            self.b.click('[aria-label^="Show "][aria-label$="more sources"]')
            recording.hold(.6); self.button('Show less', "document.querySelector('[data-slot=\"web-search-sources\"]')"); recording.hold(.6)
            self.report['checks']['real_source_expand_collapse_reverse'] = True
        else:self.report['gaps']['R05_overflow'] = 'Provider returned fewer than four pages; overflow state unverified'
        self.b.click(trigger); recording.hold(.7)
        self.report['checks']['real_sources_closed_after_reverse'] = self.b.evaluate("document.querySelector('[data-slot=\"web-search-trigger\"]').getAttribute('aria-expanded')==='false'")
        self.save()

    def delete_motion(self, recording):
        self.require_native(); sid = self.case['delete_session']
        check(empty_new_draft(self.original_storage), 'preserve_global_new_draft_before_delete_video')
        def prove_empty():
            self.assert_selected('delete_session')
            if self.b.evaluate("document.querySelector('dialog[open] h2')?.textContent==='Conversation'"):
                check(self.b.evaluate("document.querySelector('dialog[open] .app-form input').value") == self.case['nonce'] + ' · Empty delete case', 'delete_dialog_target_changed')
            return disposable_session(self.case, self.rpc('session.list'), self.rpc('chat.snapshot', {'session_id': sid}), self.rpc('draft.read', {'session_id': sid}), self.rpc('session.jobs', {'session_id': sid}), self.b.evaluate("document.querySelectorAll('#composer .attachment').length"))
        prove_empty()
        self.b.click('.session-row.selected .session-options'); self.b.wait("document.querySelector('dialog[open] h2')?.textContent==='Conversation'")
        widget = 'dialog[open] [data-slot="delete-button"]'; trigger = widget + ' button[aria-label="Delete"]'
        mount = self.b.evaluate('(()=>{const e=document.querySelector('+json.dumps(widget)+');return {layout_width:parseFloat(getComputedStyle(e).width),screen_width:e.getBoundingClientRect().width,panel_transform:getComputedStyle(e.closest("dialog")).transform}})()')
        self.report['checks']['delete_mount_geometry'] = mount; self.save()
        check(abs(mount['layout_width']-48)<=.5 and mount['screen_width']<=49, 'repaired_delete_mount_width_regressed')
        from scripts.settled_overlay import settled_overlay
        self.report['checks']['delete_panel_settled'] = settled_overlay(self.b)
        self.report['checks']['delete_mount_width_css'] = self.b.rect(widget)['width']
        check(abs(self.report['checks']['delete_mount_width_css']-48)<=1, 'settled_delete_mount_width_regressed')
        self.b.click(trigger); recording.hold(.7); self.b.click(widget + ' [aria-label="Cancel"]'); recording.hold(.8)
        prove_empty(); self.report['checks']['cancel_preserved_empty_case'] = True
        self.b.click(trigger); recording.hold(.25); self.b.key('Escape'); recording.hold(.7)
        prove_empty(); self.report['checks']['Escape_preserved_empty_case'] = True
        self.b.click('.session-row.selected .session-options'); self.b.wait("document.querySelector('dialog[open] h2')?.textContent==='Conversation'")
        settled_overlay(self.b)
        self.b.click(trigger); recording.hold(.7); prove_empty()
        self.b.click(widget + ' [aria-label="Confirm delete"]'); recording.hold(1.8)
        check(not any(row['id'] == sid for row in self.rpc('session.list')), 'owned_empty_delete_not_committed')
        self.report['checks']['genuine_new_empty_conversation_deleted'] = sid; self.save()

    def open_import_surface(self):
        self.require_native()
        if self.b.evaluate("!!document.querySelector('.dashboard-actions')"):
            self.button('Import folder', "document.querySelector('.dashboard-actions')")
        else:
            self.b.click('#plus-menu')
            self.button('Import folder', "document.querySelector('#composer-actions')")
        self.b.wait("document.querySelector('dialog[open] h2')?.textContent==='Import folder'")

    def import_motion(self, recording, fixture, picker_driver, qualify_after_reload, *, stop_after_cancel=False):
        texts = verify_import_fixture(fixture)
        check(fixture['nonce'] == self.case['nonce'], 'fixture_from_another_case')
        check(callable(getattr(recording, 'segment', None)), 'bounded_import_recording_segments_required')
        check(callable(qualify_after_reload), 'fresh_import_document_pointer_qualification_required')
        # A separate empty import project is required: permission tests created
        # program.py in their own project and must remain intact for review.
        if self.case.get('import_project_id'):
            project = next((row for row in self.rpc('workspace.list') if row['id'] == self.case['import_project_id']), None)
            session = next((row for row in self.rpc('session.list') if row['id'] == self.case.get('import_session')), None)
            check(project and project['label'] == self.case['nonce'] + ' · Import case', 'original_owned_import_project_changed')
            check(session and session['id'] in self.case['created_session_ids'] and session['project'] == project['id'] and session['title'] == self.case['nonce'] + ' · Import preview', 'original_owned_import_session_changed')
            check(self.rpc('workspace.files', {'project_id': project['id']})['files'] == [], 'import_case_acquired_files_preserve_it')
            snap = self.rpc('chat.snapshot', {'session_id': session['id']})
            check(not snap['runs'] and not snap['messages'] and self.rpc('draft.read', {'session_id':session['id']}) == {'text':'','mode':'chat'} and not self.rpc('session.jobs', {'session_id':session['id']}), 'import_case_acquired_content_preserve_it')
            selected = self.b.evaluate('localStorage.getItem(' + json.dumps('hermes:draft-attachments:v1:' + session['id']) + ')')
            if selected:
                try: selection = json.loads(selected)
                except (ValueError, TypeError): raise RuntimeError('import_case_acquired_attachments_preserve_it')
                check(isinstance(selection,dict) and selection.get('version') == 1 and selection.get('ids') == [], 'import_case_acquired_attachments_preserve_it')
        else:
            before_projects = {row['id'] for row in self.rpc('workspace.list')}
            project = self.rpc('workspace.create', {'label': self.case['nonce'] + ' · Import case'})
            check(bool(ID.fullmatch(project['id'])) and project['id'] not in before_projects, 'new_import_project_receipt_required')
            self.case['import_project_id'] = project['id']; self.save()
            before_sessions = {row['id'] for row in self.rpc('session.list')}
            session = self.rpc('session.create', {'project_id': project['id'], 'arm': 'normal'})
            check(bool(ID.fullmatch(session['id'])) and session['id'] not in before_sessions, 'new_import_session_receipt_required')
            self.case['import_session'] = session['id']; self.case['created_session_ids'].append(session['id']); self.save()
            self.rpc('session.rename', {'session_id': session['id'], 'title': self.case['nonce'] + ' · Import preview'})
        view = {**self.original_view, 'project_id': project['id'], 'session_id': session['id'], 'arm': 'normal'}
        self.rpc('view.write', {'state': view}); self.reload_ready()
        self.filter_owned()
        qualify_after_reload(); self.require_native()
        self.open_import_surface()
        # Observe only this new project's real request response. The exact
        # original fetch Promise/response is returned; no response is replaced.
        self.b.evaluate("""(()=>{const original=globalThis.fetch,records=[],responses=[],state={overflow:0};const project=""" + json.dumps(project['id']) + """;
        const wrapped=function(...args){let watched=false;try{const q=JSON.parse(args[1]?.body||'null');const u=new URL(typeof args[0]==='string'?args[0]:args[0].url,location.href);watched=u.origin===location.origin&&u.pathname==='/hermes-workspace/api/rpc'&&q?.method==='workspace.import.request'&&q.fields?.project_id===project}catch{}
        const response=Reflect.apply(original,this,args);if(watched)response.then(async r=>({status:r.status,body:await r.clone().json()})).then(({status,body})=>{if(records.length<3){records.push(body.result??null);responses.push({status,error:typeof body.error==='string'?body.error.slice(0,1000):null,result:body.result??null})}else state.overflow++}).catch(()=>{});return response;};
        globalThis.fetch=wrapped;globalThis.__ownedImportObserver={records,responses,state,cleanup:()=>{if(globalThis.fetch===wrapped)globalThis.fetch=original;}};})()""")
        preview = '[aria-label="Preview folder contents"]'
        from scripts.probe_v4_visual import move
        recording.segment('folder_interaction')
        rect = self.b.rect(preview); move(self.b, rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2)
        recording.hold(.6); self.b.click(preview); recording.hold(.5)
        check(self.b.evaluate('document.querySelector(' + json.dumps(preview) + ").getAttribute('aria-expanded')==='true'"), 'folder_click_did_not_open')
        self.b.key('Enter'); recording.hold(.5)
        check(self.b.evaluate('document.querySelector(' + json.dumps(preview) + ").getAttribute('aria-expanded')==='false'"), 'folder_keyboard_did_not_reverse')
        self.report['checks']['folder_real_hover_click_keyboard_reverse'] = True
        check(callable(picker_driver), 'actual_native_picker_driver_required_no_substitute')
        for phase in ('cancel_picker', 'preview_cancel', 'commit'):
            self.assert_selected('import_session')
            check(self.rpc('workspace.files', {'project_id': project['id']})['files'] == [], 'import_project_acquired_files_preserve_it')
            # The chooser has its own bounded wait. Rotate the Hermes-window
            # recording so no phase exceeds the recorder's 30-second cap.
            recording.segment('native_picker_' + phase)
            self.button('Choose folder', "document.querySelector('dialog[open]')")
            # Driver must operate only this request's actual native kdialog,
            # verify process/window ownership, and return after selection/cancel.
            evidence = picker_driver(phase, fixture['root'])
            check(evidence.get('actual_native_chooser') is True and evidence.get('phase') == phase, 'native_picker_evidence_missing')
            self.report.setdefault('native_picker', []).append(evidence); self.save()
            self.b.wait("!([...document.querySelectorAll('button')].some(e=>e.textContent.includes('Waiting for folder picker'))) ", timeout=15)
            verify_import_fixture(fixture)
            count = ('cancel_picker', 'preview_cancel', 'commit').index(phase) + 1
            self.b.wait('globalThis.__ownedImportObserver.records.length===' + str(count))
            observed = self.b.evaluate('globalThis.__ownedImportObserver.records[' + str(count - 1) + ']')
            if phase == 'cancel_picker':
                check(observed == {'cancelled': True} and not self.b.evaluate("!!document.querySelector('.import-review')"), 'cancelled_picker_created_preview')
                self.report['checks']['actual_picker_cancelled_without_preview'] = True; self.save()
                if stop_after_cancel:
                    self.report['checks']['diagnostic_cancel_only_no_copy'] = True
                    self.b.evaluate('globalThis.__ownedImportObserver.cleanup()'); self.save()
                    return
            else:
                self.b.wait("!!document.querySelector('.import-review')")
                check(isinstance(observed, dict) and bool(ID.fullmatch(observed.get('ticket', ''))), 'actual_UI_import_ticket_not_observed')
                verified = verify_import_ticket(project['id'], observed['ticket'], fixture)
                self.report.setdefault('verified_owned_import_tickets', []).append(verified); self.save()
                names = self.b.evaluate("[...document.querySelectorAll('.import-review li')].map(e=>e.textContent)")
                check(names == sorted(texts), 'actual_import_preview_differs_from_fixture')
                check(self.b.evaluate('globalThis.__ownedImportObserver.state.overflow===0 && globalThis.__ownedImportObserver.records.length===' + str(count)), 'unexpected_import_request_preserve_it')
                recording.hold(.6)
                self.button('Cancel import' if phase == 'preview_cancel' else 'Copy reviewed files', "document.querySelector('.import-review')")
                recording.hold(.7)
        copied = self.rpc('workspace.files', {'project_id': project['id']})
        check(copied['files'] == sorted(texts) and copied['snapshot_sha256'] == expected_snapshot(texts), 'real_import_copy_bytes_not_proven')
        verify_import_fixture(fixture)
        self.report['checks']['real_picker_preview_cancel_commit_copy_and_original_unchanged'] = {'project_id': project['id'], 'snapshot_sha256': copied['snapshot_sha256'], 'files': copied['files']}
        self.report['gaps'].pop('native_picker', None); self.save()
        self.b.evaluate('globalThis.__ownedImportObserver.cleanup()')

    def restore(self):
        # Restore presentation only. Never restore old catalogs, overwrite a
        # user's draft, revoke another conversation or delete retained evidence.
        self.b.evaluate('globalThis.__ownedImportObserver?.cleanup()')
        if self.original_view:self.rpc('view.write', {'state': self.original_view}); self.reload_ready()
        current_draft = self.rpc('draft.read', {'session_id': self.original_view['session_id']}) if self.original_draft is not None else None
        changes = empty_storage_restoration(self.original_storage, self._storage())
        # An empty new-chat draft may acquire an empty string during normal
        # document cleanup. Restore its exact original representation only;
        # compare again inside JS so concurrent user text is never overwritten.
        if changes:
            self.b.evaluate("(()=>{const changes=" + json.dumps(changes) + ";for(const [key,c]of Object.entries(changes)){if(localStorage.getItem(key)!==c.expected)throw Error('storage_changed_before_empty_restore')}for(const [key,c]of Object.entries(changes)){if(c.value===null)localStorage.removeItem(key);else localStorage.setItem(key,c.value)}})()")
        check(self.rpc('view.read') == self.original_view and current_draft == self.original_draft and self._storage() == self.original_storage, 'original_view_draft_attachment_or_sound_state_changed')
        if self.original_filter:
            self.b.click('.rail-search input'); self.b.call('Input.insertText', {'text': self.original_filter})
        self.report['checks']['original_view_draft_attachments_and_sound_state_preserved'] = True
        self.report['checks']['retained_created_records_for_scoped_cleanup'] = True; self.save()
