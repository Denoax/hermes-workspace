# Normal and abliterated model comparison

Question: does an abliterated version improve successful, independently checked
work on these authorized local tasks, and what reliability/performance changes
come with it? Reduced refusal alone is not proof of higher capability.

Reported current setup to CONFIRM, not silently replace:
- Model file: `/home/mani/.local/share/llama.cpp/models/Qwen3.6-35B-A3B-Q4_K_M.gguf`.
- Alias: `qwen3.6-35b-a3b-q4`; backend was llama.cpp b9980 Vulkan.
- Endpoint was `http://127.0.0.1:8080/v1`; context was 65,536.
- Earlier hardware: RTX 4070, about 12 GB VRAM, 62 GiB RAM.
- Earlier offload included `--n-gpu-layers 99 --n-cpu-moe 28 --device Vulkan0`.
These are historical facts, not an up-to-date host audit or guaranteed flags.

## Provenance and artifact selection

Official family card inspected: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
Existing local GGUF metadata, hashes, tokenizer/chat template and actual backend
identity take precedence over aliases or filename alone.

Candidate GGUF publisher inspected:
https://huggingface.co/mradermacher/Qwen3.6-35B-A3B-abliterated-GGUF
The card advertises Q4_K_M at roughly 21.3 decimal GB and points to
`wangzhang/Qwen3.6-35B-A3B-abliterated` as its source. Follow that actual source
and validate its lineage before use; do not attribute this GGUF to Huihui.

Other publisher cards to investigate separately:
https://huggingface.co/huihui-ai/Huihui-Qwen3.6-35B-A3B-abliterated
https://huggingface.co/trohrbaugh/Qwen3.6-35B-A3B-heretic
The latter describes a historical expert-tensor serialization repair. Inspect
current artifact/revision and verify runtime reload/output; do not use a stale
copy or assume the publisher's benchmark applies to this local GGUF/backend.

These are candidates, not endorsements or measured local recommendations.
Pin repository commit, exact filenames/shards, expected file sizes and published
LFS hashes; compute local hashes after download. Record base family/revision,
ablation method/revision, additional tuning, tokenizer/template and quantizer.
Verify licenses and compatibility. Download only selected data files through a
trusted fetcher; do not execute model-repository scripts, enable remote code, or
load pickle weights. SHA-256 proves byte identity, not publisher trust.

Retain the existing base GGUF unchanged. Store the candidate as a separate lab
artifact. No host-global package reinstall or backend upgrade merely because
a community model-card quickstart says so. Use installed help/pinned original
runtime docs. If a backend change is necessary, build a separate pinned lab
runtime and document the comparison confound.

On this hardware, loading both full models concurrently is an unsuitable default.
Measure available GPU/RAM/space, include both artifacts, VM images, caches and
desktop reserve, and run sequentially. Never presume 3B activated parameters
means only 3B weights need storage. No new 35B weight-modification/training job
is required for the first phase. Investigate making a matched derivative only
as a later resource-budgeted experiment if no suitable artifact exists.

## Comparison design

- Record the exact model artifacts and runtime/config hash for every trial.
- Keep task, tool permissions, VM snapshot, context/output budgets, prompt,
  sampling settings, API parsing and retry policy matched wherever possible.
- Fresh guest workspace and Hermes memory/session between cases and arms. No
  cached answers, transferred successes or hidden cloud model assistance.
- First smoke: one repeat of three cases per model; extend to all 12 cases with
  repeated seeds only after resource/isolation checks. Counterbalance A/B order
  in later repeats. Start with a measured 8K context; treat larger-context trials
  as a separate sweep. Do not overwrite the normal server's context settings.
- Record deterministic answer/candidate verification, schema failures,
  legitimate-task refusals, permission violations, retries, wall time, time to
  first token and measured token usage, peak RSS/VRAM and abnormal shutdowns.
- Record missing metrics as missing. Seed equality is not a guarantee of
  deterministic GPU inference. Report per-case outcomes and sample size.
- Tiny samples demonstrate feasibility, not statistical superiority.
- If the derivative's source revision/quantization differs or is undocumented,
  label results as an ARTIFACT comparison. Do not attribute a change solely to
  abliteration. Missing data does not authorize invented provenance.

Grade by outside deterministic tools. The model may explain observations but
cannot mark its own answer correct, modify its judge, relax isolation or select
new real-world targets. Keep regression and containment scores separate.
The initial fixtures contain legitimate controlled tasks; no harmful-response
count is needed to demonstrate capability. The original model may already solve
all of them. Report that result honestly and expand difficulty within the lab.
