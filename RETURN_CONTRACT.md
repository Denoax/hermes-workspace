# Local Codex return contract

Return ONE `~/Downloads/MANI_HERMES_VM_LAB_REVIEW_<UTC>.zip` with exact bytes and
SHA-256. Keep original service configs, keys, raw logs/tokens and model weights
in private local storage. No weights, guest disk images, personal profiles or
credentials belong in the review archive.

Include the rebuildable lab source (omit venv/caches/dependencies), pinned version
record, sanitized configs, source/asset provenance, complete automated validation
results, model artifact metadata/hashes, actual model runs in JSONL/CSV, a readable
comparison, containment/watchdog/cleanup evidence, failures and resource measures,
normal-setup recovery checks and host-specific rollback instructions.

Report every implemented command and tested lifecycle path. Distinguish dry run,
fixture/mock test, real VM integration, real local inference and actual paired
Hermes runs. A mock responder cannot count as local-model evaluation. Sanitized
transcripts may retain synthetic prompts/answers but omit local tokens and keys.
State sample size, incomplete cases, confounds and unverified isolation honestly.

Include `SHA256SUMS.txt`, verify a clean extraction and every payload checksum,
and inspect text for secrets. A regex pass alone is not adequate sanitization.
Do not include the whole home or existing Hermes/router repositories by default.
Use a clean lab-source export and preserve prior Git work. No pushes/deployments.

Final response: what is implemented, which live tests passed, which model artifacts
were actually tested and what they achieved, unresolved gaps, exact review ZIP
path/size/hash, private rollback location and any genuinely needed next decision.
No claim that fewer refusals proved more intelligence or complete containment.
