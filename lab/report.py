"""Reports distinguish planned/blocked records from actual model trials."""
import csv
import json
from pathlib import Path
import statistics

FIELDS = ("arm", "case_id", "status", "execution_kind", "passed", "category",
          "wall_seconds", "ttft_seconds", "prompt_tokens", "completion_tokens", "finish_reason",
          "refusal", "containment", "model_sha256", "reason", "model_calls", "finish_reasons",
          "RSS_high_water_kib", "device_aggregate_VRAM_MiB")


def request_usage(result):
    completed=[event for event in result.get('relay_events',[]) if event.get('outcome')=='completed']
    if not completed:
        return {key:result.get(key) for key in ('prompt_tokens','completion_tokens','finish_reason')}
    totals={}
    for key in ('prompt_tokens','completion_tokens'):
        values=[(event.get('usage') or {}).get(key) for event in completed]
        totals[key]=sum(values) if all(type(value) is int and value>=0 for value in values) else None
    return {**totals,'model_calls':len(completed),'finish_reasons':[event.get('finish_reason') for event in completed],
            'finish_reason':completed[-1].get('finish_reason')}


def write_results(directory, rows):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for row in rows:
        resources=row.get('backend_resources') or {}
        for field in ('RSS_high_water_kib','device_aggregate_VRAM_MiB'):
            row[field]=resources.get(field)
    with (directory / "trials.jsonl").open("w") as output:
        for row in rows:
            output.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    with (directory / "trials.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    actual = [row for row in rows if row["status"] == "completed" and row["execution_kind"] in ('paired_guest_Hermes', 'normal_guest_Hermes','abliterated_guest_Hermes')]
    paired = [row for row in actual if row['execution_kind'] == 'paired_guest_Hermes']
    text = f"Actual guest Hermes trials: {len(actual)}; paired trials: {len(paired)}.\n"
    text += f"Blocked or incomplete records: {len(rows) - len(actual)}.\n"
    text += "Only actual independently graded runs contribute to correctness. Missing timings, refusal and containment metrics remain null.\n"
    for arm in ('normal','abliterated'):
        arm_rows=[row for row in actual if row['arm']==arm]
        correct=sum(row['passed'] is True for row in arm_rows)
        errors=sum(str(row.get('answer','')).startswith('HTTP ') for row in arm_rows)
        text+=f"{arm}: {correct}/{len(arm_rows)} strictly correct; provider-error final responses: {errors}.\n"
        walls=[row['wall_seconds'] for row in arm_rows if type(row.get('wall_seconds')) in (int,float)]
        if walls:
            text+=f"  Observed case wall seconds: median {statistics.median(walls):.3f}, range {min(walls):.3f}–{max(walls):.3f}; n={len(walls)}.\n"
    text+='Wall time includes guest Hermes startup and all requests. RSS is process high-water; VRAM samples cover the whole device including desktop.\n'
    text+='Small synthetic samples, fixed arm order and cache effects limit inference. Provider errors confound capability comparison; TTFT and refusal rates are unmeasured.\n'
    (directory / "comparison.txt").write_text(text)
    return {"actual_trials": len(actual), "records": len(rows)}


def blocked_matrix(case_ids, reason):
    return [{"arm": arm, "case_id": case_id, "status": "blocked",
             "execution_kind": "no_model_execution", "passed": None, "category": None,
             "wall_seconds": None, "ttft_seconds": None, "prompt_tokens": None,
             "completion_tokens": None, "finish_reason": None, "refusal": None,
             "containment": None, "model_sha256": None, "reason": reason}
            for arm in ("normal", "abliterated") for case_id in case_ids]
