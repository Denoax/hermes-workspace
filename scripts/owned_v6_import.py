"""Focused new-owned import review with guarded v6 presentation restoration."""
import hashlib
import json
import re
import uuid
import os
from pathlib import Path

from scripts.owned_action_review import OwnedActionReview, check, fixture_text, verify_import_fixture
from scripts.owned_v6_interactions import INTENT, NEW_SELECTION, presentation_changes, selection_ids, sha


def allowed_import_view(case, view, original):
    if view == original:
        return True
    return (view.get('session_id') == case.get('import_session')
            and view.get('project_id') == case.get('import_project_id')
            and view.get('arm') == 'normal' and case.get('import_session') in case.get('created_session_ids', []))


def resumed_import_case(receipt, prefix):
    check(isinstance(receipt,dict) and isinstance(receipt.get('case'),dict), 'exact_v6_import_case_receipt_required')
    case = receipt.get('case', {})
    check(case.get('version') == 1 and case.get('kind') == 'v6_fresh_import_only'
          and isinstance(case.get('nonce'),str)
          and bool(re.fullmatch(re.escape(prefix) + r'-actions-[0-9a-f]{8}', case.get('nonce', ''))),
          'exact_v6_import_case_receipt_required')
    check(set(case) == {'nonce','created_session_ids','version','kind','import_project_id','import_session'}
          and all(isinstance(case.get(k),str) and re.fullmatch('[0-9a-f]{32}',case[k]) for k in ['import_project_id','import_session'])
          and case.get('created_session_ids') == [case['import_session']]
          and receipt.get('status') == 'PARTIAL'
          and receipt.get('checks',{}).get('folder_real_hover_click_keyboard_reverse') is True
          and not receipt.get('checks',{}).get('real_picker_preview_cancel_commit_copy_and_original_unchanged'),
          'only_exact_uncommitted_import_case_can_resume')
    return json.loads(json.dumps(case))


def existing_import_fixture(parent, nonce):
    texts=fixture_text(nonce)
    root=Path(parent)/(nonce+'-import-source')
    check(root.is_dir() and not any(p.is_symlink() for p in (root,*root.parents)), 'existing_exact_owned_fixture_required')
    info=root.stat()
    receipt={'nonce':nonce,'root':str(root),'device':info.st_dev,'inode':info.st_ino,
             'files':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in texts.items()}}
    verify_import_fixture(receipt)
    return receipt


def picker_request_outcome(browser, recovery, phase):
    check(phase in ('cancel_picker','preview_cancel','commit'), 'fixed_picker_diagnostic_phase_required')
    observed=browser.evaluate("(async()=>{const o=globalThis.__ownedImportObserver;"
        "if(o?.responses?.some(r=>r.error)){await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame)}"
        "const e=document.querySelector('dialog[open][aria-label=\"Import folder\"] [role=alert]');let visible=false;if(e){const b=e.getBoundingClientRect();"
        "const h=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);visible=b.width>0&&b.height>0&&(h===e||e.contains(h))}"
        "return {responses:o?.responses??[],ui_alert:e?.textContent?.slice(0,1000)??null,ui_alert_unoccluded:visible}})()")
    if observed is None:return None
    check(isinstance(observed,dict) and isinstance(observed.get('responses'),list) and len(observed['responses'])<=3,
          'actual_import_response_shape_required')
    index=('cancel_picker','preview_cancel','commit').index(phase)
    if len(observed['responses'])<=index:return None
    response=observed['responses'][index]
    check(isinstance(response,dict), 'actual_import_response_shape_required')
    observed={key:observed.get(key) for key in ('ui_alert','ui_alert_unoccluded')} | {'response':response}
    check(type(response.get('status')) is int and 100<=response['status']<=599, 'actual_import_HTTP_status_required')
    # Raw RPC/UI strings stay only in private recovery. The public category is
    # selected from existing fixed source strings, never an arbitrary exception.
    from workspace.desktop import _PICKER_ERRORS
    known={value:key for key,value in _PICKER_ERRORS.items()}
    known.update({'native_picker_invalid_reply':'invalid_picker_protocol',
                  'native_desktop_session_unavailable':'desktop_session_unavailable',
                  'A Hermes folder chooser is already open.':'picker_already_open'})
    error=response.get('error')
    if isinstance(error,str):category=known.get(error,'unclassified_backend_error')
    elif isinstance(response.get('result'),dict) and response['result'].get('cancelled') is True:category='cancelled_before_chooser_observed'
    else:category='request_completed_before_chooser_observed'
    recovery=Path(recovery)
    check('private-state' in recovery.parts and not any(p.is_symlink() for p in (recovery,*recovery.parents)), 'private_error_recovery_required')
    recovery.mkdir(mode=0o700,parents=True,exist_ok=True)
    check(recovery.stat().st_uid==os.getuid() and not recovery.stat().st_mode&0o077,'owner_only_private_error_recovery_required')
    path=recovery/(phase+'-request-'+uuid.uuid4().hex+'.json')
    with path.open('x') as stream:json.dump(observed,stream,indent=2)
    path.chmod(0o600)
    return {'HTTP_status':response['status'],'classification':category,
            'dialog_error_visible': observed['ui_alert_unoccluded'] is True,
            'private_response_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'raw_error_scope':'RPC/UI details retained only outside review output; exclude all private-state files.'}


class OwnedImportReview(OwnedActionReview):
    def __init__(self, browser, rpc, output, navigation, recovery):
        super().__init__(browser, rpc, output, navigation)
        check(not browser.evaluate("!!document.querySelector('dialog[open]')"), 'preserve_original_panel_before_import_review')
        before = self.original_storage
        self.storage_keys = list(dict.fromkeys([*self.storage_keys, INTENT]))
        self.original_storage = self._storage()
        check(all(self.original_storage[k] == value for k, value in before.items()), 'presentation_changed_during_import_guard')
        check(not self.original_storage.get('hermes:new-draft') and not selection_ids(self.original_storage.get(NEW_SELECTION)),
              'global_new_draft_or_attachments_preserved_probe_not_started')
        self.original_scroll = browser.evaluate("document.querySelector('.conversation').scrollTop")
        self.case.update(version=1, kind='v6_fresh_import_only')
        recovery = Path(recovery)
        check('private-state' in recovery.parts and not any(p.is_symlink() for p in (recovery, *recovery.parents)),
              'separate_private_import_recovery_required')
        recovery.mkdir(mode=0o700, parents=True, exist_ok=True)
        check(recovery.stat().st_uid == os.getuid() and not recovery.stat().st_mode & 0o077, 'private_import_recovery_required')
        path = recovery / (self.case['nonce'] + '-presentation.json')
        with path.open('x') as stream:
            json.dump({'version':1,'kind':'private_v6_import_presentation','view':self.original_view,
                       'draft':self.original_draft,'storage':self.original_storage,
                       'filter':self.original_filter,'scroll':self.original_scroll},stream)
        path.chmod(0o600)
        self.report['scope'] = 'Actual18791 pin; only a fresh import project/session and native chooser; no model/search/permission actions.'
        self.report['private_recovery'] = 'Raw presentation stays in private-state and must never enter publication/review ZIP.'
        self.report['original_presentation_sha256'] = sha({'view':self.original_view,'draft':self.original_draft,'storage':self.original_storage,'filter':self.original_filter})
        self.save()

    def _restore_storage(self, changes):
        self.b.evaluate("(()=>{const changes=" + json.dumps(changes) + ";for(const[k,c]of Object.entries(changes)){"
                        "if(localStorage.getItem(k)!==c.expected)throw Error('concurrent_storage_change_preserved')}"
                        "for(const[k,c]of Object.entries(changes)){if(c.value===null)localStorage.removeItem(k);else localStorage.setItem(k,c.value)}})()")

    def restore(self):
        from scripts.probe_v4_visual import close_panels, input_text

        self.b.evaluate('globalThis.__ownedImportObserver?.cleanup()')
        close_panels(self.b)
        view = self.rpc('view.read')
        check(allowed_import_view(self.case, view, self.original_view), 'unexpected_user_view_preserved_no_import_restore')
        owned_projects = {self.case['import_project_id']} if self.case.get('import_project_id') else set()
        if self.case.get('import_session'):
            sid = self.case['import_session']
            current = next((r for r in self.rpc('session.list') if r['id'] == sid), None)
            check(current and current['project'] == self.case['import_project_id']
                  and current['title'] == self.case['nonce'] + ' · Import preview', 'owned_import_session_changed_preserve_it')
            draft = self.rpc('draft.read', {'session_id':sid})
            selected = self.b.evaluate('localStorage.getItem(' + json.dumps('hermes:draft-attachments:v1:' + sid) + ')')
            snap = self.rpc('chat.snapshot', {'session_id':sid})
            check(draft == {'text':'','mode':'chat'} and not selection_ids(selected)
                  and not snap['messages'] and not snap['runs'] and not self.rpc('session.jobs', {'session_id':sid}),
                  'new_import_user_content_preserved_no_restore')
            if view.get('session_id') == sid:
                check(self.b.evaluate("document.querySelector('#prompt').value===''&&document.querySelectorAll('#composer .attachment').length===0"),
                      'unsaved_import_input_preserved_no_restore')
        original = self.rpc('draft.read', {'session_id':self.original_view['session_id']}) if self.original_draft is not None else None
        check(original == self.original_draft, 'new_original_user_draft_preserved_no_restore')
        self._restore_storage(presentation_changes(self.original_storage, self._storage(), owned_projects))
        self.rpc('view.write', {'state':self.original_view})
        self.reload_ready()
        self._restore_storage(presentation_changes(self.original_storage, self._storage(), owned_projects))
        if self.original_filter:
            input_text(self.b, '.rail-search input', self.original_filter)
        self.b.evaluate("document.querySelector('.conversation').scrollTop=" + json.dumps(self.original_scroll))
        check(self.rpc('view.read') == self.original_view
              and (self.rpc('draft.read', {'session_id':self.original_view['session_id']}) if self.original_draft is not None else None) == self.original_draft
              and self._storage() == self.original_storage, 'original_import_presentation_not_restored')
        check(self.b.evaluate("document.querySelector('.rail-search input').value") == self.original_filter,
              'original_import_filter_not_restored')
        self.report['checks']['original_view_draft_attachments_sound_and_composing_intent_preserved'] = True
        self.report['checks']['fresh_import_records_retained_without_reset'] = True
        self.save()
