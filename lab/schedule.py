"""Deterministic matched diagnostic schedule, independent of model answers."""
import hashlib


def paired_schedule(cases, smoke=True, repeats=1):
    if type(repeats) is not int or not 1 <= repeats <= 3:
        raise ValueError("repeat_budget")
    catalog = {case["case_id"]: case for case in cases}
    selected = ["B01", "B04", "B08"] if smoke else [f"B{i:02}" for i in range(1, 13)]
    if any(case_id not in catalog for case_id in selected):
        raise ValueError("incomplete_catalog")
    trials = []
    for repeat in range(repeats):
        arms = ("normal", "abliterated") if repeat % 2 == 0 else ("abliterated", "normal")
        for arm in arms:
            for case_id in selected:
                prompt = catalog[case_id]["prompt"]
                trials.append({"arm": arm, "case_id": case_id, "repeat": repeat,
                               "seed": 41 + repeat, "context_tokens": 8192,
                               "output_tokens": 1024, "temperature": 0.0, "top_p": 1.0,
                               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                               "fresh_guest_required": True, "status": "planned"})
    return trials
