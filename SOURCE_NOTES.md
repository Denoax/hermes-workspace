> Historical handoff research follows below. Current artifact evidence is in
> `results/continuation/candidate_artifact.json`, `candidate_provenance.json`,
> `guest_image_signature.json` and `actual_offline_guest_installation.json`.
> The selected candidate bytes have now been acquired and SHA-256 verified;
> no alternative Huihui/Heretic weights were acquired.

Current systemd unit search order was measured with native
`systemd-analyze --user unit-paths`. `/run/user/1000/systemd/user.control` precedes
the persistent user unit directory; a mask in the lower-priority runtime `user`
directory would not override that service. The window checks actual LoadState,
MainPID and its recorded symlink identity. Official load-path reference:
https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml .

The actual pinned Hermes custom-provider module at revision
`63279301bcbdc185c1b07b98a9312eb0c862f26d` emits `reasoning_effort="none"` for a
thinking-only length continuation. The b9980 revision's server README documents
`chat_template_kwargs: {"enable_thinking": false}`. The relay maps only that
specific request value; caller-supplied template kwargs and other reasoning
levels remain rejected. Primary version-bound references:
https://github.com/NousResearch/hermes-agent/blob/63279301bcbdc185c1b07b98a9312eb0c862f26d/plugins/model-providers/custom/__init__.py
and https://raw.githubusercontent.com/ggml-org/llama.cpp/8014d2cf9/tools/server/README.md .

# Original sources and decisions

Checked 2026-10-12. These are short paraphrases and task-specific engineering
interpretations. Recheck installed versions. No model weights, local VM or host
isolation result was inspected during package preparation.

## QEMU invocation

- URL: https://www.qemu.org/docs/master/system/invocation.html
- Access: inspected
- Application: Restricted user networking blocks guest host/outside IP access but explicit forwarding remains. Pin the installed version, limit forwarding, and verify both families.

## QEMU security

- URL: https://www.qemu.org/docs/master/system/security.html
- Access: inspected
- Application: Unprivileged processes, least privilege, resource limits and management-layer confinement underpin guest isolation. A virtual machine alone is not a guarantee against escape.

## Hermes configuration

- URL: https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- Access: inspected
- Application: Profile state does not prevent account-level filesystem access. Auxiliary/delegated calls and fallback routing need explicit inspection. Use guest-local state and a bounded local relay.

## Hermes repository

- URL: https://github.com/NousResearch/hermes-agent
- Access: inspected
- Application: Reuse the installed/pinned build and relevant tool/terminal interfaces. Do not copy all personal configuration, plugin credentials or messaging state into the lab.

## llama.cpp server

- URL: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Access: inspected
- Application: The server offers inference and optional tool/admin/media functions. Expose only bounded required local inference; installed flags can differ from current master.

## Official Qwen model

- URL: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
- Access: inspected
- Application: Official family/architecture documentation is a provenance starting point; the actual local GGUF metadata and pinned artifact hash must be confirmed.

## Candidate GGUF

- URL: https://huggingface.co/mradermacher/Qwen3.6-35B-A3B-abliterated-GGUF
- Access: publisher card inspected; weights not downloaded
- Application: Card points to wangzhang as source and lists Q4_K_M around 21.3 GB. Follow actual lineage and verify exact revision/files locally. Quickstart commands are not an approved install script.

## Candidate Huihui weights

- URL: https://huggingface.co/huihui-ai/Huihui-Qwen3.6-35B-A3B-abliterated
- Access: publisher card inspected; weights not downloaded
- Application: Separate candidate for provenance investigation; not asserted to be the ancestor of the selected GGUF.

## Candidate Heretic weights

- URL: https://huggingface.co/trohrbaugh/Qwen3.6-35B-A3B-heretic
- Access: publisher card inspected; weights not downloaded
- Application: Card reports an earlier expert-tensor loading repair. Validate actual runtime correctness and revision; publisher measurements do not establish local performance.

## Heretic implementation

- URL: https://github.com/p-e-w/heretic
- Access: inspected
- Application: Abliteration optimizes refusal reduction while aiming to preserve capabilities. Availability and support vary by architecture; no new 35B modification job is required in phase one.

## Original refusal research

- URL: https://arxiv.org/abs/2406.11717
- Access: inspected earlier in this conversation
- Application: The study demonstrated refusal-direction interventions across tested models; it does not guarantee better reasoning or safe autonomous action.

## Ubuntu image index

- URL: https://cloud-images.ubuntu.com/releases/noble/release/
- Access: inspected
- Application: Use updated official image and independent published signature/checksum verification. Resolve a fixed image revision locally rather than trusting mutable latest URLs.

## Cloud-init modules

- URL: https://docs.cloud-init.io/en/latest/reference/modules.html
- Access: inspected
- Application: Trusted preparation can set up guest users/packages/keys; strip temporary access and prove final isolation before agent activation.

## Design inference

Three guests, sequential 35B inference, an outside deterministic supervisor,
bounded relay and the smoke/extended matrix are design choices for this task.
The hardware data is historical personal context and must be re-measured.
This handoff does not assert that every source prescribes this exact architecture.
