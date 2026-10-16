"""Guarded R05 hover/focus on one genuine historical citation, starting on owned A.

Read/apply $reference-led-design. No model, search, new record, link activation,
policy/audio preference changes or captures. Root reviews and runs separately.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import time

sys.dont_write_bytecode = True

ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
RECEIPTS = {
    'actions-resume/owned/actions.json': '7f4b9b5cf1f0f9cac3041837bcb76207f7ce7a2513bc109e52d2046dfb2fa72f',
    'citation-repeat/citation.json': '485f449962366cec3eb2110c88a43b6f789ae59309f380c3ad36c62770fb18c5',
    'citation-final/citation.json': '6c5e02ad58b813d79e39b44f2890f741522950e7e5beb06c2bbac4b13005b42b',
}
SELECTOR = '.message.assistant [data-slot="web-search-citation"]>a'
SOURCES = ('scripts/probe_v5_citation.py', 'scripts/probe_v6_geometry.py', 'scripts/v6_motion_review.py',
    'scripts/owned_v6_interactions.py', 'scripts/v6_surface_review.py', 'scripts/v6_zoom_restore.py',
    'scripts/v6_preferences_review.py', 'scripts/probe_v4_visual.py', 'scripts/probe_v4_chat.py',
    'scripts/probe_v5_owned_actions.py', 'scripts/production_pin.py', 'workspace/parity_browser.py',
    'workspace/native_coordinates.py', 'workspace/capture.py', 'workspace/launcher.py', 'workspace/server.py', 'workspace/catalog.py', 'workspace/conversations.py',
    'workspace/frontend/src/main.tsx', 'workspace/frontend/src/MessageMarkdown.tsx',
    'workspace/frontend/src/lib/citations.ts', 'workspace/frontend/src/components/web-search.tsx',
    'workspace/ui/dist/app.js', 'workspace/ui/dist/app.css', 'workspace/ui/dist/identities.json')


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def bounded_json(path, expected=None):
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
            and path.stat().st_uid == os.getuid() and path.stat().st_size < 2 * 1024 * 1024,
            'bounded_owned_original_receipt_required')
    require(expected is None or sha(path) == expected, 'original_receipt_hash_mismatch')
    return json.loads(path.read_text())


def load_historic(review):
    """Exact immutable receipt chain; does not read a catalog or execute a CLI."""
    documents = {name: bounded_json(review / name, wanted) for name, wanted in RECEIPTS.items()}
    actions = documents['actions-resume/owned/actions.json']
    created = documents['citation-repeat/citation.json']
    preview = documents['citation-final/citation.json']
    from scripts.probe_v5_citation import actions_case
    original, aid, sources = actions_case(actions)
    require(created['status'] == 'FAIL' and created['new_sessions'] == 1 and created['new_attachments'] == 0,
            'retained_failed_creation_receipt_required')
    require(preview['status'] == 'PASS_SCOPED_TECHNICAL' and preview['new_response_generated'] is False
            and preview['new_sessions'] == preview['new_attachments'] == 0, 'actual_preview_only_receipt_required')
    require(preview['preview_only_receipt_sha256'] == RECEIPTS['citation-repeat/citation.json'], 'preview_creation_chain_mismatch')
    for record in (created, preview):
        require(record['actions_sha256'] == RECEIPTS['actions-resume/owned/actions.json']
                and record['source_permission_session_id'] == original['permission_session']
                and record['project_id'] == original['project_id'] and record['attachment_id'] == aid
                and record['sources'] == sources, 'real_provider_chain_mismatch')
    for key in ('session_id', 'run_id', 'prompt_sha256', 'answer_sha256', 'run'):
        require(created[key] == preview[key], 'real_created_turn_changed_between_receipts')
    return {'nonce': original['nonce'], 'project_id': original['project_id'], 'session_id': preview['session_id'],
            'attachment_id': aid, 'sources': deepcopy(sources), 'run': deepcopy(preview['run']),
            'attachment': deepcopy(actions['checks']['real_Wikipedia_search']['result']['attachment']),
            'prompt_sha256': preview['prompt_sha256'], 'answer_sha256': preview['answer_sha256']}


def validate_historic(case, projects, sessions, snapshot, run, draft, jobs, metadata, raw_selection):
    """Positive exact history ownership. Reject later content before selection."""
    project = [row for row in projects if row.get('id') == case['project_id']]
    session = [row for row in sessions if row.get('id') == case['session_id']]
    require(len(project) == 1 and project[0].get('label') == case['nonce'] + ' · Action review', 'historic_project_changed')
    require(len(session) == 1 and session[0].get('title') == case['nonce'] + ' · Citation check'
            and session[0].get('project') == case['project_id'] and session[0].get('arm') == 'normal', 'historic_session_changed')
    require(run == case['run'] and snapshot.get('runs') == [run] and run['state'] == 'completed'
            and run['session'] == case['session_id'] and run['model'] == 'normal'
            and run['identity']['arm'] == 'normal' and run['identity']['context'] == 65536,
            'historic_completed_run_changed')
    require(run['settings']['prompt_sha256'] == case['prompt_sha256']
            and run['settings'].get('attachments') == [case['attachment_id']], 'historic_prompt_or_attachment_changed')
    messages = snapshot.get('messages', [])
    require(len(messages) == 2 and [row.get('role') for row in messages] == ['user', 'assistant']
            and all(row.get('job') == run['id'] for row in messages), 'historic_two_message_scope_changed')
    require(text_sha(messages[0]['text']) == case['prompt_sha256']
            and text_sha(messages[1]['text']) == case['answer_sha256'] and '[1]' in messages[1]['text'],
            'historic_message_hash_changed')
    require(draft == {'text': '', 'mode': 'chat'} and not jobs and raw_selection is None,
            'historic_draft_jobs_or_selection_changed')
    require(metadata == case['attachment'] and metadata.get('id') == case['attachment_id']
            and metadata.get('metadata', {}).get('search', {}).get('provider') == 'Wikipedia'
            and metadata['metadata']['search']['sources'] == case['sources'],
            'historic_canonical_attachment_changed')
    attachments = snapshot.get('attachments', {})
    require(set(attachments) == {run['id']} and attachments[run['id']] == [metadata], 'historic_turn_attachment_scope_changed')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=ROOT)
    parser.add_argument('--v5-review', type=Path, required=True)
    parser.add_argument('--owned-case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-production-probe', action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe or os.getuid() == 0:
        parser.error('reviewed explicit normal-operator execution required')
    root = args.app_root.resolve(strict=True); sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import NativeX11Input, prepare, enable_native_input, input_text, move
    from scripts.probe_v6_geometry import load_case
    from scripts.v6_motion_review import verify_aggregate_bytes, attachment_proof
    from scripts.owned_v6_interactions import OwnedInteractions, owned_row, presentation_changes, selection_ids
    from scripts.v6_surface_review import capture_context, compare_context, require_owned_native_focus, native_key, viewport
    from scripts.v6_zoom_restore import active_owned, qualify_points_once, command
    from scripts.v6_preferences_review import media_state
    from scripts.probe_v5_owned_actions import runtime_identity
    from workspace.server import normal_profile_unchanged
    from workspace import launcher

    historic = load_historic(args.v5_review)
    receipt = bounded_json(args.owned_case); case = load_case(receipt)
    require(receipt.get('kind') == 'actual_interaction_subcheck_aggregate', 'original_v6_aggregate_required')
    aggregate = verify_aggregate_bytes(receipt, args.owned_case); proof = attachment_proof(receipt)
    out = args.output
    require('private-state' in out.parts and not any(p.is_symlink() for p in (out, *out.parents)), 'new_private_output_required')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    require(out.stat().st_uid == os.getuid() and not out.stat().st_mode & 0o077, 'owner_only_output_required')
    sources = {name: sha(root / name) for name in SOURCES}
    report = {'status': 'IN_PROGRESS', 'scope': 'Exact genuine historical R05 hover/staged trusted Tab; no inference/search/link activation/new record/edit/delete/audio-setting change/capture.',
              'receipt_chain_sha256': RECEIPTS, 'v6_aggregate_identity': aggregate, 'source_sha256_before': sources,
              'diagnostic_sha256': sha(Path(__file__)), 'checks': {}, 'cleanup': {}, 'native_qualification': [],
              'media_exportable': False, 'new_response_generated': False, 'reference_parity_and_human_review': 'UNVERIFIED'}
    target = out / 'citation.json'
    def save():
        target.write_text(json.dumps(report, indent=2) + '\n'); target.chmod(0o600)
    browser = None; original = expected_historic = preferences = original_filter = original_effort = original_focus = a_state = None
    cursor = address = native_geometry = None
    outer = outer_original = outer_expected = None
    outer_staged = False
    switched = filter_touched = safe_to_close = False
    expected_filter = None
    def read(method, fields=None): return rpc(browser, method, fields or {})
    def storage(keys): return browser.evaluate('Object.fromEntries(' + json.dumps(keys) + '.map(k=>[k,localStorage.getItem(k)]))')
    def all_roles():
        sessions, projects = read('session.list'), read('workspace.list')
        for role in ('A', 'B', 'P', 'Q'):
            owned_row(case, role, sessions if role in ('A', 'B') else projects)
        return projects, sessions
    def historic_guard():
        projects, sessions = all_roles(); sid, rid, aid = historic['session_id'], historic['run']['id'], historic['attachment_id']
        return validate_historic(historic, projects, sessions, read('chat.snapshot', {'session_id': sid}),
            read('chat.read', {'run_id': rid}), read('draft.read', {'session_id': sid}), read('session.jobs', {'session_id': sid}),
            read('attachment.metadata', {'id': aid}), browser.evaluate('localStorage.getItem(' + json.dumps('hermes:draft-attachments:v1:' + sid) + ')'))
    def a_snapshot():
        sid = case['records']['A']['id']
        return {'draft': read('draft.read', {'session_id': sid}), 'snapshot': read('chat.snapshot', {'session_id': sid}),
                'jobs': read('session.jobs', {'session_id': sid}),
                'selection': browser.evaluate('localStorage.getItem(' + json.dumps('hermes:draft-attachments:v1:' + sid) + ')')}
    def native_guard():
        require_owned_native_focus(browser)
        current = active_owned(browser, address)
        require((current['at'], current['size']) == native_geometry, 'native_geometry_drift_abort')
        require(a_snapshot() == a_state, 'newer_A_content_preserved_abort')
        require(read('view.read') in (original['view'], expected_historic), 'newer_view_or_theme_preserved_abort')
        presentation_changes(original['storage'], storage(list(original['storage'])),
                             {case['records']['P']['id'], historic['project_id']})
        require(expected_filter is None or browser.evaluate('document.querySelector(".rail-search input").value') == expected_filter,
                'newer_filter_preserved_abort')
    def visible_hit(selector):
        require(browser.evaluate('''(()=>{const e=document.querySelector(''' + json.dumps(selector) + ''');if(!e)return false;const r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,h=document.elementFromPoint(x,y);return r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight&&!!h&&(h===e||e.contains(h))})()'''),
                'native_target_not_visible_or_covered_abort')
    def select_row(sid, nonce):
        nonlocal filter_touched, expected_filter
        native_guard(); visible_hit('.rail-search input'); filter_touched = True
        input_text(browser, '.rail-search input', nonce)
        expected_filter = nonce
        selector = '.session-row:has(#conversation-options-' + sid + ')>button:first-child'
        browser.wait('!!document.querySelector(' + json.dumps(selector) + ')')
        browser.evaluate('document.querySelector(' + json.dumps(selector) + ').scrollIntoView({block:"nearest"})')
        native_guard(); visible_hit(selector); browser.click(selector)
    def wait_view(expected):
        # Browser.wait polls at40Hz. Network observation uses the established
        # rate-limit-aware RPC reader and a bounded5Hz cadence instead.
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if read('view.read') == expected:
                return
            time.sleep(min(.2,max(0,deadline-time.monotonic())))
        raise RuntimeError('expected_view_not_observed_within_existing_deadline')
    def tooltip():
        observed = browser.evaluate('''(()=>new Promise(resolve=>{const end=performance.now()+2500;let last=null,stable=0;function sample(){const e=document.querySelector('[data-slot="web-search-citation"] [role="tooltip"]');if(e){const c=getComputedStyle(e),r=e.getBoundingClientRect(),m=new DOMMatrixReadOnly(c.transform==='none'?undefined:c.transform),v={x:r.x,y:r.y,width:r.width,height:r.height,opacity:+c.opacity};stable=last&&v.opacity>=.995&&Math.abs(m.a-1)<=.002&&Math.abs(m.d-1)<=.002&&Math.abs(m.f)<=.25&&(c.filter==='none'||c.filter==='blur(0px)')&&['x','y','width','height'].every(k=>Math.abs(v[k]-last[k])<=.25)?stable+1:0;last=v;if(stable>=4)return resolve({status:'settled',last:v})}if(performance.now()>end)return resolve({status:'timeout'});requestAnimationFrame(sample)}requestAnimationFrame(sample)}))()''')
        require(observed['status'] == 'settled', 'historic_tooltip_not_settled')
        bounds = browser.evaluate('''(()=>{const e=document.querySelector('[data-slot="web-search-citation"] [role="tooltip"]'),c=document.querySelector('.workspace-body').getBoundingClientRect(),r=e.getBoundingClientRect(),n=e.querySelector('.line-clamp-3'),s=n&&getComputedStyle(n),q=n?.getBoundingClientRect();return {tooltip:r.toJSON(),clip:c.toJSON(),snippet:n?{height:q.height,line_height:parseFloat(s.lineHeight),scroll_height:n.scrollHeight,client_height:n.clientHeight}:null,visible:r.top>=Math.max(0,c.top)-.5&&r.bottom<=Math.min(innerHeight,c.bottom)+.5&&r.left>=Math.max(0,c.left)-.5&&r.right<=Math.min(innerWidth,c.right)+.5}})()''')
        require(bounds['visible'] and bounds['snippet'] and bounds['snippet']['height'] <= bounds['snippet']['line_height'] * 3 + .5, 'historic_tooltip_bounds_or_snippet_clamp_failed')
        return {'settling': observed, 'bounds': bounds}
    def alarm(_signal, _frame): raise TimeoutError('historic_citation_bounded_deadline')
    previous, previous_term = signal.signal(signal.SIGALRM, alarm), signal.signal(signal.SIGTERM, alarm)
    signal.alarm(180); save()
    try:
        require(normal_profile_unchanged(), 'normal_configuration_changed_before_citation')
        browser = ProductionPin(); prepare(browser)
        report['runtime_before'] = runtime_identity(browser, root)
        require(not browser.evaluate('!!document.querySelector("dialog[open],.anchored-popover,#cancel-response,.recording-indicator,.attachment-issues")'), 'original_active_surface_or_work_preserved')
        require(browser.evaluate('document.querySelector("#effort-toggle .brain-icon").classList.contains("brain-on")') is False,
                'original_transient_thinking_on_preserved_no_probe')
        outer_original = capture_context(browser, read)
        outer = OwnedInteractions(browser, rpc, out / 'private-owner', out / 'private-recovery')
        outer.case = deepcopy(case)
        outer.report['case'] = outer.case
        outer.report['scope'] = 'Only A/B/P/Q reused; no old D/E creation or deletion and no inference.'
        all_roles()
        outer_expected = {**outer.original_view, 'session_id': case['records']['A']['id'],
                          'project_id': case['records']['P']['id'], 'arm': 'normal'}
        require(read('view.read') == outer.original_view, 'newer_initial_view_preserved_no_switch')
        outer_staged = True
        read('view.write', {'state': outer_expected})
        outer.reload(); prepare(browser)
        all_roles(); original = capture_context(browser, read)
        require(original['view']['session_id'] == case['records']['A']['id'] and original['view']['project_id'] == case['records']['P']['id']
                and original['view']['arm'] == 'normal' and original['view']['task_kind'] == 'chat'
                and not any(original['view'].get(key) for key in ('editor', 'file_path', 'files_open')), 'start_on_exact_owned_A_required')
        require(original['prompt'] == original['draft']['text'] and text_sha(original['prompt']) == proof['draft_sha256'], 'original_unsaved_or_changed_A_input_preserved')
        a_state = a_snapshot(); require(not a_state['snapshot']['runs'] and not a_state['snapshot']['messages'] and not a_state['jobs'], 'owned_A_acquired_content_preserved')
        require(selection_ids(a_state['selection']) == [proof['id']], 'current_A_selection_differs_from_genuine_receipt')
        metadata = read('attachment.metadata', {'id': proof['id']})
        require(all(metadata[key] == proof[key] for key in ('sha256', 'mime', 'bytes')), 'current_A_attachment_provenance_changed')
        historic_guard(); report['checks']['exact_historic_identity_before_selection'] = 'PASS'
        original_filter = browser.evaluate('document.querySelector(".rail-search input").value')
        expected_filter = original_filter
        original_effort = browser.evaluate('document.querySelector("#effort-toggle .brain-icon").classList.contains("brain-on")')
        original_focus = browser.evaluate('''(()=>{const e=document.activeElement;window.__v6HistoricOriginalFocus=e;return {tag:e?.tagName,id:e?.id||null,owned_A_row:e===document.querySelector(''' + json.dumps('.session-row:has(#conversation-options-' + case['records']['A']['id'] + ')>button:first-child') + '''),start:e?.selectionStart??null,end:e?.selectionEnd??null,direction:e?.selectionDirection??null}})()''')
        preferences = media_state(browser)
        historic_key = 'hermes:draft-attachments:v1:' + historic['session_id']
        original['storage'][historic_key] = browser.evaluate('localStorage.getItem(' + json.dumps(historic_key) + ')')
        recovery = out / 'original-presentation.PRIVATE.json'
        with recovery.open('x') as handle: json.dump({'context': original, 'filter': original_filter, 'focus': original_focus, 'effort': original_effort}, handle)
        recovery.chmod(0o600)
        safe_to_close = True
        expected_historic = {**original['view'], 'session_id': historic['session_id'], 'project_id': historic['project_id'], 'arm': 'normal'}
        require(launcher.focus(), 'normal_existing_pin_activation_failed')
        client = active_owned(browser); address = client['address']; cursor = command('/usr/bin/hyprctl', 'cursorpos', '-j')
        browser._native_input = NativeX11Input(); points = qualify_points_once(browser, browser._native_input, client)
        report['native_qualification'].append(points); require(points['status'] == 'PASS_POINTS_ONLY', 'fresh_native_qualification_failed')
        browser._native_coordinates = (*points['mapping'], address); browser._native_diagnostics = {'status': 'PASS'}
        native_geometry = (client['at'], client['size']); enable_native_input(browser)
        browser.evaluate('''(()=>{const state={sequence:0,expected:null};window.__v6SurfaceKeyReview=state;addEventListener('keydown',e=>{if(e.isTrusted&&e.key===state.expected)state.sequence++},true)})()''')
        select_row(historic['session_id'], historic['nonce']); switched = True
        wait_view(expected_historic)
        require(read('view.read') == expected_historic, 'historic_view_did_not_preserve_original_theme_motion')
        historic_guard()
        browser.wait('document.querySelectorAll(' + json.dumps(SELECTOR) + ').length===1')
        require(browser.evaluate('document.querySelector(' + json.dumps(SELECTOR) + ').href') == historic['sources'][0]['url'], 'historic_rendered_citation_href_changed')
        require(browser.evaluate('document.querySelector("#prompt").value===""&&document.querySelector("#model-picker").value==="normal"'), 'historic_rendered_draft_or_model_changed')
        native_guard(); browser.evaluate('document.querySelector(' + json.dumps(SELECTOR) + ').scrollIntoView({block:"center"})')
        visible_hit(SELECTOR); rect = browser.rect(SELECTOR); move(browser, rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2)
        report['checks']['native_hover'] = tooltip(); native_guard(); move(browser, 20, 100)
        browser.wait('!document.querySelector("[data-slot=web-search-citation] [role=tooltip]")')
        report['checks']['hover_dismissal'] = 'PASS'
        browser.evaluate('''(()=>{const target=document.querySelector(''' + json.dumps(SELECTOR) + '''),all=[...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex="0"]')].filter(e=>!e.disabled&&e.getClientRects().length),i=all.indexOf(target);if(i<1)throw Error('historic_citation_Tab_predecessor_missing');all[i-1].focus()})()''')
        native_guard(); native_key(browser, 'Tab')
        require(browser.evaluate('document.activeElement===document.querySelector(' + json.dumps(SELECTOR) + ')&&document.activeElement.matches(":focus-visible")'), 'historic_staged_native_Tab_not_focused')
        report['checks']['staged_predecessor_trusted_Tab'] = tooltip(); native_guard(); native_key(browser, 'Tab')
        browser.wait('!document.querySelector("[data-slot=web-search-citation] [role=tooltip]")')
        report['checks']['keyboard_dismissal'] = 'PASS'
        historic_guard(); require(a_snapshot() == a_state, 'owned_A_content_changed_during_citation')
        report['checks']['exact_historic_and_A_content_after_observation'] = 'PASS'
        report['viewport'] = viewport(browser); report['effective_preferences'] = preferences
        report['runtime_after'] = runtime_identity(browser, root)
        require(report['runtime_after'] == report['runtime_before'], 'runtime_changed_during_historic_observation')
        report['status'] = 'PASS_SCOPED_TECHNICAL'
    except Exception as error:
        import traceback
        detail = {'error_category':type(error).__name__,'detail':str(error)[:2000],
                  'traceback':traceback.format_exc()[-24000:]}
        private_error = out / 'failure.PRIVATE.json'
        private_error.write_text(json.dumps(detail,indent=2)+'\n');private_error.chmod(0o600)
        report['private_failure_diagnostic'] = {'retained':True,'sha256':sha(private_error)}
        code = str(error); report.update(status='BLOCKED' if not switched else 'FAIL', error_category=type(error).__name__,
            error_code=code if re.fullmatch('[A-Za-z0-9_]{1,160}', code) else 'historic_observer_or_application_error')
    finally:
        cleanup_until = time.monotonic() + 60
        def cleanup(name, callback):
            try:
                remaining = cleanup_until - time.monotonic(); require(remaining > 0, 'cleanup_budget_exhausted')
                signal.alarm(max(1, math.ceil(remaining))); callback(); report['cleanup'][name] = {'status': 'ok'}
            except Exception as error:
                code = str(error)
                report['cleanup'][name] = {'status': 'failed', 'error_category': type(error).__name__,
                    'error_code':code if re.fullmatch('[A-Za-z0-9_]{1,160}',code) else 'private_cleanup_observer_failure'}; report['status'] = 'FAIL'
            save()
        restored = safe_to_close and not filter_touched
        if browser and filter_touched:
            def restore():
                nonlocal restored, expected_filter
                native_guard()
                require(browser.evaluate('document.querySelector(".rail-search input").value') in (historic['nonce'], case['nonce']), 'newer_filter_preserved_no_restore')
                if read('view.read') != original['view']:
                    select_row(case['records']['A']['id'], case['nonce'])
                    wait_view(original['view'])
                    browser.wait('document.querySelector("#prompt").value===' + json.dumps(original['prompt']))
                require(read('view.read') == original['view'] and a_snapshot() == a_state, 'original_A_view_or_content_not_restored')
                current = storage(list(original['storage']))
                changes = presentation_changes(original['storage'], current, {case['records']['P']['id'], historic['project_id']})
                browser.evaluate('''(()=>{const changes=''' + json.dumps(changes) + ''';for(const[k,c]of Object.entries(changes))if(localStorage.getItem(k)!==c.expected)throw Error('concurrent_storage_preserved');for(const[k,c]of Object.entries(changes)){if(c.value===null)localStorage.removeItem(k);else localStorage.setItem(k,c.value)}})()''')
                native_guard(); visible_hit('.rail-search input'); input_text(browser, '.rail-search input', original_filter)
                expected_filter = original_filter
                browser.evaluate('''(()=>{const e=document.querySelector('.conversation'),r=''' + json.dumps(original['reading']) + ''';if(e&&r){e.scrollTop=r.top;e.scrollLeft=r.left}})()''')
                require(browser.evaluate('document.querySelector("#effort-toggle .brain-icon").classList.contains("brain-on")') == original_effort, 'original_transient_effort_changed')
                restored_context = capture_context(browser, read); restored_context['storage'] = storage(list(original['storage']))
                report['original_context_restoration'] = compare_context(original, restored_context)
                require(report['original_context_restoration']['status'] == 'PASS' and media_state(browser) == preferences, 'original_context_or_preferences_not_restored')
                require(browser.evaluate('document.querySelector(".rail-search input").value') == original_filter, 'original_filter_not_restored')
                browser.evaluate('''(()=>{if(document.activeElement!==document.querySelector('.rail-search input'))throw Error('newer_focus_preserved');let e=window.__v6HistoricOriginalFocus;const f=''' + json.dumps(original_focus) + ''';if(!e?.isConnected&&f.id)e=document.getElementById(f.id);if(!e?.isConnected&&f.owned_A_row)e=document.querySelector(''' + json.dumps('.session-row:has(#conversation-options-' + case['records']['A']['id'] + ')>button:first-child') + ''');if(!e?.isConnected||e.tagName!==f.tag)throw Error('original_focus_node_unavailable');if(e===document.body)document.activeElement.blur();else e.focus({preventScroll:true});if(document.activeElement!==e)throw Error('original_focus_not_restored');if(f.start!==null)e.setSelectionRange(f.start,f.end,f.direction)})()''')
                restored = True
            cleanup('original_A_presentation_draft_upload_model_theme_effort_preferences', restore)
        if browser and outer and outer_staged:
            def restore_outer():
                nonlocal restored
                require(not filter_touched or restored, 'preserve_unrestored_inner_document')
                require(read('view.read') in (outer_expected, outer.original_view), 'newer_outer_view_preserved')
                outer.restore()
                observed = capture_context(browser, read)
                report['outer_context_restoration'] = compare_context(outer_original, observed)
                require(report['outer_context_restoration']['status'] == 'PASS', 'original_outer_context_not_restored')
                restored = True
            cleanup('original_user_presentation', restore_outer)
            if report['cleanup']['original_user_presentation']['status'] != 'ok': restored = False
        if browser:
            if getattr(browser, '_native_input', None): cleanup('own_native_connection', browser._native_input.close)
            if cursor:
                def restore_cursor():
                    active_owned(browser, address); connection = NativeX11Input()
                    try: connection.move(cursor['x'], cursor['y'])
                    finally: connection.close()
                cleanup('cursor', restore_cursor)
            cleanup('owned_pin', browser.close if restored else browser.detach_preserving_document)
        cleanup('normal_configuration', lambda: require(normal_profile_unchanged(), 'normal_configuration_changed_after_citation'))
        def source_check():
            report['source_sha256_after'] = {name: sha(root / name) for name in SOURCES}
            require(report['source_sha256_after'] == sources and sha(Path(__file__)) == report['diagnostic_sha256'], 'source_changed_during_citation')
        cleanup('source_identity', source_check)
        signal.alarm(0); signal.signal(signal.SIGALRM, previous); signal.signal(signal.SIGTERM, previous_term); save()
    print(json.dumps({'status': report['status'], 'report': str(target)}))
    return 0 if report['status'] == 'PASS_SCOPED_TECHNICAL' else 2


if __name__ == '__main__':
    raise SystemExit(main())
