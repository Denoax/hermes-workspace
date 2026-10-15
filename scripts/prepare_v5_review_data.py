"""Create clearly named, owned navigation records on the actual production pin.

These are real empty catalog records, not fabricated messages or model results.
The output identifies every created ID for later narrowly scoped cleanup.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import re
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute-production-probe', action='store_true')
    parser.add_argument('--resume-owned', action='store_true', help='Resume only the positively identified empty records from a failed setup.')
    args = parser.parse_args()
    if not args.execute_production_probe:
        parser.error('explicit production probe flag required')
    if os.geteuid() == 0:
        raise RuntimeError('normal_operator_required')
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = args.output / 'owned-navigation.json'
    if target.exists() and not args.resume_owned:
        raise RuntimeError('new_output_directory_required')
    report = {'status': 'IN_PROGRESS', 'scope': 'actual production18791 catalog',
              'prefix': 'V5review-' + uuid.uuid4().hex[:8],
              'projects': [], 'sessions': [], 'messages_inserted': 0,
              'model_inference_started': False}
    if args.resume_owned:
        previous = json.loads(target.read_text())
        if previous.get('status') != 'FAIL' or not re.fullmatch(r'V5review-[0-9a-f]{8}', previous.get('prefix', '')):
            raise RuntimeError('exact_failed_owned_setup_required')
        history = args.output / ('owned-navigation-failed-' + str(time.time_ns()) + '.json')
        history.write_bytes(target.read_bytes())
        report = previous
        report['status'] = 'IN_PROGRESS'
        report.pop('error_type', None)
        report.pop('error_code', None)

    def save():
        target.write_text(json.dumps(report, indent=2) + '\n')

    browser = None
    leave_open = False
    try:
        browser = ProductionPin()
        report['pin'] = browser.identity
        if browser.evaluate('document.querySelectorAll("#composer .attachment").length'):
            leave_open = True
            raise RuntimeError('unsent_attachments_must_be_preserved')
        initial = rpc(browser, 'view.read', {})
        initial_draft = rpc(browser, 'draft.read', {'session_id': initial['session_id']}) if initial.get('session_id') else None
        prompt = browser.evaluate('document.querySelector("#prompt").value')
        if prompt != (initial_draft['text'] if initial_draft else ''):
            leave_open = True
            raise RuntimeError('unsaved_prompt_must_be_preserved')
        if args.resume_owned:
            actual_projects = {row['id']: row for row in rpc(browser, 'workspace.list', {})}
            actual_sessions = {row['id']: row for row in rpc(browser, 'session.list', {})}
            for row in report['projects']:
                if actual_projects.get(row['id']) != row or not row['label'].startswith(report['prefix']):
                    raise RuntimeError('owned_project_drift')
            for row in report['sessions']:
                actual = actual_sessions.get(row['id'])
                if not actual or actual['project'] != row['project'] or rpc(browser, 'session.history', {'session_id': row['id']}):
                    raise RuntimeError('owned_empty_session_drift')
        # No view navigation is needed: all mutations create positively owned
        # records, leaving the original view/draft untouched.
        for index, (label, parent_index, color) in enumerate((
            ('Local research workspace', None, 'blue'),
            ('Source notes and a deliberately long nested project title', 0, 'purple'),
            ('Interface studies', 1, 'orange'),
            ('Archive and experiments', 0, 'green'),
        )):
            if index < len(report['projects']):
                continue
            row = rpc(browser, 'workspace.create', {'label': report['prefix'] + ' · ' + label})
            report['projects'].append({'id': row['id'], 'label': row['label'], 'parent': None, 'color': color})
            save()
            parent = report['projects'][parent_index]['id'] if parent_index is not None else None
            rpc(browser, 'folder.update', {'project_id': row['id'], 'label': row['label'], 'parent': parent, 'color': color})
            report['projects'][-1]['parent'] = parent
            save()
        for index, title in ((0, 'Review overview'), (1, 'Long conversation title retained through focus and disclosure'),
                             (2, 'Reference anatomy and keyboard navigation'), (3, 'Archived local experiments')):
            project = report['projects'][index]['id']
            row = report['sessions'][index] if index < len(report['sessions']) else rpc(browser, 'session.create', {'project_id': project, 'arm': 'normal'})
            owned = {'id': row['id'], 'project': project, 'title': (report['prefix'] + ' · ' + title)[:80]}
            if index < len(report['sessions']):
                report['sessions'][index] = owned
            else:
                report['sessions'].append(owned)
            save()
            rpc(browser, 'session.rename', {'session_id': row['id'], 'title': owned['title']})
        report['selected_session_id'] = report['sessions'][1]['id']
        report['checks'] = {
            'original_view_unchanged': rpc(browser, 'view.read', {}) == initial,
            'original_draft_unchanged': not initial_draft or rpc(browser, 'draft.read', {'session_id': initial['session_id']}) == initial_draft,
            'owned_sessions_have_no_messages': all(not rpc(browser, 'session.history', {'session_id': row['id']}) for row in report['sessions']),
        }
        if not all(report['checks'].values()):
            raise RuntimeError('owned_navigation_preservation_check_failed')
        report['status'] = 'PASS_SCOPED_TECHNICAL'
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__, error_code=str(error) if str(error).isidentifier() else 'owned_record_setup_failed')
        raise
    finally:
        save()
        if browser:
            if leave_open:
                browser.detach_preserving_document()
            else:
                browser.close()
    print(json.dumps({'status': report['status'], 'report': str(target), 'prefix': report['prefix'], 'session_id': report.get('selected_session_id')}))


if __name__ == '__main__':
    main()
