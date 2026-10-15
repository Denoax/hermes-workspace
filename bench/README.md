# Benchmark assets

Twelve authored synthetic cases provide deterministic initial smoke/regression
checks. These are deliberately small diagnostics, not an exhaustive cyber or
reasoning benchmark. Do not claim a model's intelligence from them alone.

Only cases/prompts and explicitly selected task assets go to the controller.
Keep `answer_keys.json`, scoring code and hidden verification inputs OUTSIDE all
agent-accessible guests. Do not execute model-generated code on the host.
The offline scorer compares JSON answers strictly, including types, and reports
schema/error/correctness without using an LLM judge. Expanded agent/code tasks
require real tool/VM integration and fresh independent validation by Codex.

`toy_function.c` is authored reference source for making a stripped binary in a
trusted preparation/validation guest. Do not supply its source as the answer to
a solver being evaluated on reconstructed code; generate a model-facing listing
or equivalent observations, then verify behavior in a fresh guest.

Run starter checks with `python3 -B -m unittest discover -s tests -v` from the
package root. This tests reference helpers/fixtures only. There is no model
answer, VM result, or performance score in this starter package.

Grade saved raw-answer strings with `python3 -B -m starter.scoring --answers
trial_answers.json` from the package root. The input is a JSON object mapping
case IDs to raw JSON-answer strings; preserve model text exactly for grading.
A parse failure is not automatically classified as a refusal.
