"""Derive one 36-row acceptance inventory from current durable ledger evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_v5_review as archive

LOOP = '.agent/hermes-loop/'
EVIDENCE_FIELDS = ('kind', 'outcome', 'fixture', 'scope', 'app_url', 'via', 'runtime_identity', 'model',
                   'viewport', 'theme', 'reference_ids', 'duration_seconds', 'continuous')


def generate(root, public, review, inspector=None, *, expected_rows=36, expected_ids=None):
    source = archive.committed_source(public)
    source_hashes = {name: archive.digest(data) for name, data in source['files'].items()}
    inputs = {name: archive.read_scoped(root, LOOP + name) for name in archive.LEDGER_FILES}
    requirements, state = (json.loads(inputs[name]) for name in archive.LEDGER_FILES[:2])
    task_ids = [task['id'] for task in requirements['tasks']]
    if (len(task_ids) != expected_rows or len(set(task_ids)) != expected_rows or set(state['tasks']) != set(task_ids)
            or expected_ids is not None and task_ids != list(expected_ids)):
        raise ValueError(f'complete_exact_{expected_rows}_row_inventory_required')
    if inspector is None:
        spec = importlib.util.spec_from_file_location('review_loopctl', root / 'scripts/loopctl.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        inspector = controller.inspect
    errors = inspector(root, requirements, state, archive.digest(inputs['requirements.json']))
    if errors:raise ValueError('ledger_validation_failed: ' + '; '.join(errors))
    review.mkdir(mode=0o700, parents=True, exist_ok=True)
    generated = []
    def stage(name, data):
        archive.checked(name, data)
        path = review / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != review and review in p.parents):
            raise ValueError('review_stage_symlink_refused')
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
        generated.append(name)
    snapshots = {}
    for name, data in inputs.items():
        target = 'loop/' + name
        stage(target, data)
        snapshots[name] = {'archive_path': 'review/' + target, 'sha256': archive.digest(data)}
    evidence = {}
    for evidence_id, record in state['evidence'].items():
        artifact_name = archive.safe_name(record['artifact'])
        path = root / artifact_name
        entry = {name: record[name] for name in EVIDENCE_FIELDS if name in record}
        entry.update(expected_sha256=record.get('sha256'), actual_sha256=None, archive_path=None,
                     source_files={})
        if path.exists():
            data = archive.read_scoped(root, artifact_name)
            actual = archive.digest(data)
            if source_hashes.get(artifact_name) == actual:
                target = 'source/' + artifact_name
            else:
                target = 'review/ledger-artifacts/' + artifact_name
                stage(target.removeprefix('review/'), data)
            entry.update(actual_sha256=actual, archive_path=target)
        entry['artifact_current'] = entry['actual_sha256'] == entry['expected_sha256'] and entry['actual_sha256'] is not None
        for name, expected in record.get('source_files', {}).items():
            archive.safe_name(name)
            actual = archive.digest(archive.read_scoped(root, name)) if (root / name).exists() else None
            entry['source_files'][name] = {'expected_sha256': expected, 'live_sha256': actual,
                                           'public_commit_sha256': source_hashes.get(name),
                                           'current': actual == expected and actual == source_hashes.get(name)}
        evidence[evidence_id] = entry
    rows = []
    for task in requirements['tasks']:
        item = state['tasks'][task['id']]
        status = archive.STATUS_MAP[item['status']]
        explicit = item.get('acceptance_status')
        if explicit is not None:
            if explicit not in ('PARTIAL', 'BLOCKED', 'UNVERIFIED'):
                raise ValueError('only_ledger_DONE_can_produce_PASS')
            if not item.get('notes'):raise ValueError('explicit_acceptance_status_needs_scope_notes')
            status = explicit
        if status == 'BLOCKED' and not item.get('blocker'):raise ValueError('blocked_acceptance_needs_concrete_blocker')
        selected = item.get('evidence', [])
        if any(evidence_id not in evidence for evidence_id in selected):raise ValueError('referenced_evidence_missing')
        if status == 'PASS' and any(not evidence[evidence_id]['artifact_current'] or
                any(not fact['current'] for fact in evidence[evidence_id]['source_files'].values()) for evidence_id in selected):
            raise ValueError('PASS_evidence_is_not_bound_to_final_public_source:' + task['id'])
        rows.append({'id': task['id'], 'title': task['title'], 'status': status, 'ledger_status': item['status'],
                     'manual': task.get('manual', False), 'depends_on': task.get('depends_on', []),
                     'acceptance': task['acceptance'], 'reference_ids': task.get('reference_ids', []),
                     'evidence_ids': selected, 'scope_and_remaining': item.get('notes', ''), 'blocker': item.get('blocker')})
    raw_publication = archive.read_scoped(review, 'publication.json')
    final_publication = archive.publication(json.loads(raw_publication), source)
    final_publication.update(archive_path='review/publication.json', sha256=archive.digest(raw_publication))
    verification = final_publication.get('verification_artifact')
    if verification:
        data = archive.read_scoped(review, verification)
        final_publication['verification_archive_path'] = 'review/' + verification
        final_publication['verification_sha256'] = archive.digest(data)
    counts = {status: sum(row['status'] == status for row in rows) for status in archive.STATUSES}
    result = {'schema_version': 1, 'inventory': f'exact current {expected_rows}-row requirements ledger',
              'source': {'commit': source['commit'], 'tree': source['tree'], 'files': source_hashes},
              'runtime_scope': 'Per-evidence native/production identity and capture scope; source hashes alone do not attest installed behavior.',
              'ledger_inputs': snapshots, 'rows': rows, 'evidence': evidence, 'publication': final_publication,
              'summary': {'counts': counts, 'overall': 'PASS' if counts['PASS'] == expected_rows else 'PARTIAL',
                          'unfinished_ids': [row['id'] for row in rows if row['status'] != 'PASS'],
                          'publication_status': final_publication['status']},
              'observation_truth_attested_by_generator': False, 'human_identity_authenticated_by_generator': False}
    stage('acceptance.json', archive.encoded(result))
    required = generated + ['publication.json'] + ([verification] if verification else [])
    return {'acceptance': result, 'generated_review_files': sorted(generated), 'required_review_files': sorted(set(required))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'public', 'review'):parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.root.resolve(), args.public.resolve(), args.review.resolve())
    print(json.dumps({'summary': result['acceptance']['summary'], 'required_review_files': result['required_review_files']}, indent=2))


if __name__ == '__main__':main()
