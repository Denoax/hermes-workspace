"""Prepare, never install, an additive v6 scope and recoverable ledger pair.

Read and apply $reference-led-design. This utility does no GUI, native control,
model execution, approval, Git write or live-ledger mutation. The sole writer
reviews the proposal, checks the captured input hashes, then installs the pair.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import tempfile

import package_v5_review as archive
from v6_review_profile import TASK_IDS, V5_TASK_IDS, V6_TASK_IDS

LOOP = '.agent/hermes-loop/'
OBJECTIVE = ('Complete Hermes v6 interaction refinement against the preserved current checkout; '
             'retain the working v4 repair, v5 behavior, all user data and every unresolved v5 gap; '
             'verify the existing production pin and return a source-bound complete review.')
CONSTRAINTS = (
    'V6 is an additive scope authorized by the current user request; preserve all 36 v5 IDs, original evidence, blockers and historical completion records.',
    'Review the actual local v5 complete ZIP and uninterrupted recordings; prepared candidate tests are not native visual or motion approval.',
    'Revalidate only source-bound affected claims and dependent DONE rows; never rewrite old proof hashes to make historical observations current.',
    'Keep row management ownership separate from the viewed conversation; preserve its draft, attachments, model, reading position and every later user record.',
    'Keep native qualification, unassisted import, microphone, physical-device, reboot and human approval gaps explicit; no old receipt, host fallback or self-issued approval.',
)


def extend(requirements, state, extension, changed_sources):
    """Pure extension; old proof objects and unaffected task objects stay exact."""
    original_ids = [task['id'] for task in requirements['tasks']]
    extension_ids = [task['id'] for task in extension['tasks']]
    if original_ids != list(V5_TASK_IDS) or set(state['tasks']) != set(V5_TASK_IDS):
        raise ValueError('exact_live_v5_inventory_required_before_extension')
    if extension.get('schema_version') != 1 or extension_ids != list(V6_TASK_IDS):
        raise ValueError('exact_additive_v6_extension_required')
    if any(item.get('status') == 'IN_PROGRESS' for item in state['tasks'].values()):
        raise ValueError('checkpoint_and_stop_current_batch_before_scope_change')
    result, updated = deepcopy(requirements), deepcopy(state)
    result['objective'] = OBJECTIVE
    result['constraints'].extend(item for item in CONSTRAINTS if item not in result['constraints'])
    result['tasks'].extend(deepcopy(extension['tasks']))
    affected = {}
    for task_id in original_ids:
        item = state['tasks'][task_id]
        if item['status'] != 'DONE':
            continue
        hits = {proof_id: sorted(set(state['evidence'][proof_id].get('source_files', {})) & set(changed_sources))
                for proof_id in item.get('evidence', [])}
        hits = {proof_id: sources for proof_id, sources in hits.items() if sources}
        if hits:
            affected[task_id] = {'source_bindings_changed': hits, 'dependencies_reopened': []}
    # A still-DONE parent cannot retain a newly reopened prerequisite. This is a
    # claim dependency change, not a reason to invalidate unrelated source tests.
    while True:
        additions = {}
        for task in requirements['tasks']:
            task_id = task['id']
            dependencies = [name for name in task.get('depends_on', []) if name in affected]
            if state['tasks'][task_id]['status'] == 'DONE' and task_id not in affected and dependencies:
                additions[task_id] = {'source_bindings_changed': {}, 'dependencies_reopened': dependencies}
        if not additions:
            break
        affected.update(additions)
    for task_id, cause in affected.items():
        item = updated['tasks'][task_id]
        prior = deepcopy(item)
        prior.pop('history', None)
        item.setdefault('history', []).append({'event': 'V6_SCOPE_REVALIDATION',
                                              'previous_claim': prior, **cause})
        item['status'] = 'VERIFY'
        item.pop('acceptance_status', None)
        item['notes'] = ('V6 integration changes a selected proof source or reopens a required completion dependency. '
                         'The v5 result and exact evidence remain historical below. Revalidate this contract on '
                         'the final current source; do not overwrite its old proof hashes. Previous scope: ' + prior.get('notes', ''))
    for task in extension['tasks']:
        updated['tasks'][task['id']] = {'status': 'TODO', 'evidence': [],
                                      'notes': 'New v6 scope: no current implementation or native acceptance is claimed yet.'}
    updated['tasks']['V6-BASE']['status'] = 'IN_PROGRESS'
    updated['tasks']['V6-BASE']['notes'] = ('Reconcile current source, user edits and actual launcher/profile/catalog first; '
                                           'the immutable prepared candidate is guidance, not installed success.')
    if [task['id'] for task in result['tasks']] != list(TASK_IDS):
        raise ValueError('complete_ordered_v5_plus_v6_inventory_required')
    return result, updated, affected


def load_controller(root):
    spec = importlib.util.spec_from_file_location('v6_scope_controller', root / 'scripts/loopctl.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(root, candidate, extension_path, destination):
    inputs = {name: archive.read_scoped(root, LOOP + name) for name in archive.LEDGER_FILES}
    requirements, state = (json.loads(inputs[name]) for name in archive.LEDGER_FILES[:2])
    controller = load_controller(root)
    errors = controller.inspect(root, requirements, state, archive.digest(inputs['requirements.json']))
    structural_errors = [error for error in errors if ': stale source ' not in error]
    if structural_errors:
        raise ValueError('current_live_ledger_invalid:' + ';'.join(structural_errors))
    raw_extension = extension_path.read_bytes()
    extension = json.loads(raw_extension)
    patch = (candidate.parent / 'changes/v6.patch').read_text()
    patch_paths = re.findall(r'^diff --git a/(\S+) b/\1$', patch, flags=re.M)
    changed = {}
    for name in patch_paths:
        archive.safe_name(name)
        if (root / name).is_file():
            before = archive.read_scoped(root, name)
            after = archive.read_scoped(candidate, name)
            if before != after:
                changed[name] = {'live': archive.digest(before), 'candidate': archive.digest(after),
                                 'reason': 'Candidate integration changes the current source.'}
    for proof in state['evidence'].values():
        for name, expected in proof.get('source_files', {}).items():
            actual = archive.digest(archive.read_scoped(root, name)) if (root / name).is_file() else None
            if actual != expected:
                record = changed.setdefault(name, {'live': actual, 'reason': 'Stored proof predates current source.'})
                record.setdefault('historical_proof_sha256', [])
                if expected not in record['historical_proof_sha256']:
                    record['historical_proof_sha256'].append(expected)
    extended, updated, affected = extend(requirements, state, extension, changed)
    raw_requirements = archive.encoded(extended)
    updated['requirements_sha256'] = archive.digest(raw_requirements)
    decision = {'schema_version': 1, 'decision': 'EXPLICIT_USER_AUTHORIZED_ADDITIVE_V6_SCOPE',
                'captured_utc': datetime.now(timezone.utc).isoformat(),
                'basis': 'Current user request to extend the existing loop without dropping old gaps.',
                'before_inputs': {name: archive.digest(data) for name, data in inputs.items()},
                'extension_sha256': archive.digest(raw_extension), 'requirements_sha256': archive.digest(raw_requirements),
                'retained_v5_ids': list(V5_TASK_IDS), 'appended_v6_ids': list(V6_TASK_IDS),
                'retained_evidence_ids': list(state['evidence']), 'source_changes': changed,
                'reopened_completion_claims': affected, 'incoming_stale_proof_diagnostics': errors,
                'approval_effect': 'No native, GPU, physical, reboot or human approval is created.'}
    updated.setdefault('scope_history', []).append({'decision_path': LOOP + 'scope-decisions/v6-scope.json',
                                                   'before_requirements_sha256': decision['before_inputs']['requirements.json'],
                                                   'after_requirements_sha256': updated['requirements_sha256']})
    raw_state = archive.encoded(updated)
    plan = ('# Hermes v6 continuation plan\n\nRead and apply $reference-led-design. The root interactive session is the sole live writer.\n\n'
            'The current user request explicitly appends 21 v6 tasks to the 36 preserved v5 tasks. '
            'The recoverable pre-extension pair and full old evidence are retained. No candidate TODO state replaces live state.\n\n'
            'First reconcile actual source/pin and the complete local v5 ZIP plus uninterrupted recordings. '
            'Then integrate only reviewed candidate changes, revalidate the reopened claims, and checkpoint after meaningful work. '
            'Only one task is IN_PROGRESS. Native protected admission and all old VM/import/device/reboot/human gaps remain in force.\n\n'
            'The scope decision records exactly which proof source hashes or completion prerequisites changed. '
            'Unrelated baseline, native-repair identity and server permission proof remain unchanged; their historical scope is not expanded.\n\n'
            'The final inventory is 57 rows. Use canonical_v6_acceptance.py and package_v6_review.py; '
            'the original v5 commands retain their 36-row defaults. No publication, model success or visual approval is implied by this scope extension.\n\n'
            'If installation is interrupted, stop the writer, compare the scope decision and hashes, then restore or complete BOTH '
            'requirements.json and state.json from the retained pair. Never regenerate old tasks from candidate TODOs or restore a catalog.\n')
    resume = controller.checkpoint(extended, updated, controller.choose(extended, updated), LOOP + 'requirements.json', LOOP + 'state.json')
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    staged = {'requirements.json': raw_requirements, 'state.json': raw_state,
              'PLAN.md': plan.encode(), 'RESUME.md': resume.encode(),
              'scope-decisions/v6-scope.json': archive.encoded(decision)}
    for name, data in {**{f'pre-extension/{name}': data for name, data in inputs.items()}, **{f'ledger/{name}': data for name, data in staged.items()}}.items():
        target = destination / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o600)
    # Validation observes a private source/evidence overlay, never changes live
    # proof hashes, and does not treat its consistency result as real UI proof.
    with tempfile.TemporaryDirectory(prefix='v6-ledger-overlay-', dir=destination) as directory:
        overlay = Path(directory)
        names = {'scripts/loopctl.py'}
        for evidence in state['evidence'].values():
            names.add(evidence['artifact'])
            names.update(evidence.get('source_files', {}))
        for name in names:
            if (root / name).is_file():
                target = overlay / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read_scoped(root, name))
        for name in changed:
            if not (candidate / name).is_file():
                continue
            target = overlay / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read_scoped(candidate, name))
        validation = controller.inspect(overlay, extended, updated, archive.digest(raw_requirements))
    report = {'structural_valid': not validation, 'errors': validation, 'rows': len(extended['tasks']),
              'unchanged_evidence_registry': state['evidence'] == updated['evidence'],
              'human_approval_unchanged': state.get('human_approval') == updated.get('human_approval'),
              'reopened_ids': list(affected), 'untouched_old_task_ids': [name for name in V5_TASK_IDS if name not in affected],
              'live_files_modified': False, 'fixture_scope': 'Private candidate source overlay consistency only; no runtime/UI truth attested.'}
    (destination / 'overlay-validation.json').write_bytes(archive.encoded(report))
    if validation:
        raise ValueError('proposed_overlay_invalid:' + ';'.join(validation))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'candidate', 'extension', 'destination'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root.resolve(), args.candidate.resolve(), args.extension.resolve(), args.destination), indent=2))


if __name__ == '__main__':
    main()
