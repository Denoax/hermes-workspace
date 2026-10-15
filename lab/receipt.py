"""Convert native receipts into independently graded, explicitly incomplete rows."""
from lab.report import blocked_matrix,request_usage
from starter.scoring import score


def trial_rows(record, keys, model_pins):
    if record.get('evidence_kind')!='trusted_native_control_receipt':
        raise ValueError('native_control_receipt_required')
    stages={'smoke':['B01','B04','B08'],'matrix':[f'B{i:02}' for i in range(1,13)]}
    output={}
    for stage,cases in stages.items():
        planned=blocked_matrix(cases,'not_attempted_before_evidence_gate_or_window_end')
        indexed={(row['arm'],row['case_id']):row for row in planned}
        seen=set()
        for result in record.get(stage,[]):
            identity=(result.get('arm'),result.get('case_id'))
            if identity not in indexed or identity in seen:raise ValueError('unexpected_or_duplicate_trial')
            seen.add(identity);row=indexed[identity]
            if result.get('status')!='ok':
                row['reason']=result.get('reason','native_trial_incomplete')
                continue
            if result.get('evidence_kind')!='real_guest_Hermes':raise ValueError('real_guest_evidence_required')
            if result.get('model_sha256')!=model_pins[row['arm']]['sha256']:
                raise ValueError('loaded_model_identity_mismatch')
            grading=score(row['case_id'],result.get('answer'),keys)
            if result.get('passed') is not grading['passed']:raise ValueError('outside_grading_disagrees')
            row.update(status='completed',execution_kind='paired_guest_Hermes',reason=None,
                       passed=grading['passed'],category=grading['category'],answer=result['answer'],
                       containment='qualified_native_run',model_sha256=result['model_sha256'])
            for field in ('wall_seconds','ttft_seconds','prompt_tokens','completion_tokens','finish_reason',
                          'backend_resources','Hermes_revision'):
                row[field]=result.get(field)
            row.update(request_usage(result))
        output[stage]=planned
    return output
