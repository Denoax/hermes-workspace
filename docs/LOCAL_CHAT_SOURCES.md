# Local chat UI source and adaptation record

Read and apply `$reference-led-design` for visual continuation. Preserve approved
work and the accepted click samples. Use inspected published references and
original code; do not generate visual assets or invent activity or approvals.

## Reused components

Six components come from [Rare UI](https://github.com/swamimalode07/rare-ui) at
`9633fcfa81c212a0ba48507e9c56be4869d61928`: ai-status, web-search,
folder-component, voice-note, task-list and delete-button. The original component
bytes were acquired and checked against the handoff's Git blob pins before
integration. They live in `workspace/frontend/src/components` with the upstream
utility helper. The complete upstream license, including Commons Clause and
attribution conditions, is in `workspace/ui/licenses/Rare-UI-integrated.txt`.
This is not an assertion that the components are plain MIT. Settings credits
Rare UI; preserve that attribution and review the terms for redistribution.

Adaptations connect real state and accessible semantics: AiStatus receives
actual run states; WebSearch receives actual Wikipedia results and no invented
progress/favicons; FolderImport is a compact native-button child; VoiceNote
requires a real media URL, uses the audio clock and measured waveform, pauses
when hidden, and has no timer-only demo playback; TaskList receives actual
attachment/search events and cannot invent completed tasks; DeleteButton awaits
the server acknowledgement and retains errors instead of animating fake success.
All respect app and system reduced motion. Formatting and local utility imports
are integration changes. Component appearance is an adaptation, not a claim of
unchanged upstream bytes or pixel identity.

## Observed references and original implementations

| Published reference | Observed detail | Hermes adaptation |
| --- | --- | --- |
| [Galaxy brain effort](https://www.inspora.design/posts/galaxy-brain-effort-slider), ozzy / @ozzyxs1a | Effort and current value, Faster/Smarter labels, pink brain thumb, stepped track | Original CSS/SVG popover; two effective off/on positions because the pinned template exposes a boolean, not four native effort levels |
| [iquid-metal](https://www.inspora.design/posts/iquid-metal), @BrettFromDJ | Black circular face with thin reflective rim and moving spectral highlights | Original CSS upload control; `+` replaces the source's send arrow to distinguish upload from Send |
| [hypnotizing-ui](https://www.inspora.design/posts/hypnotizing-ui), @k_grajeda | Top-attached black notch, concave shoulders, muted file row, readable work label, tiny luminous glyph | Original CSS, shown only during actual admitted work; no example filenames or idle animation |
| [Brainwave supplied pin](https://de.pinterest.com/pin/333055334963544751/) | Branch rails, rounded selection, count chip and outlined coloured folders | Original Hermes hierarchy with real records; no copied logo, scene art or invented asset counts |
| [Task Management Dashboard](https://dribbble.com/shots/21673507-Task-Management-Dashboard), Awsmd | Neutral tinted material, white inset rail, dark selection, restrained spacing | Compact conversation shell; light follows the observed material, dark is a deliberate semantic adaptation |

The exact Dribbble page was inspected in Iris. The supplied Pinterest page was
also inspected in Iris; its login overlay obscures part of the image. The
handoff reports a different canonical pin (`468163323787275414`), so original
designer identity remains ambiguous. The three exact Inspora clip hashes were
verified and frames inspected locally. Original creator source/license was not
obtained; the independently authored controls do not redistribute those clips.
Private reference frames/clips are excluded from the review and public source.
Continuous playback and matched-scale results are recorded separately; a frame
inspection does not establish smooth motion or human approval.

## Technical implementation sources

- [Pinned llama.cpp server b9980](https://github.com/ggml-org/llama.cpp/blob/b9980/tools/server/README.md): chat SSE, template/tokenizer endpoints and thinking switch.
- [MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder): explicit device capture, negotiated recording formats and track cleanup.
- [whisper.cpp v1.7.6](https://github.com/ggml-org/whisper.cpp/tree/v1.7.6): optional CPU-only local transcription. `scripts/prepare_voice.py` pins source and English tiny weights; it does not alter Qwen or use cloud transcription.

React, React DOM, Motion, react-use-measure, react-markdown, clsx and tailwind-merge
are pinned in the lockfile. Tailwind, TypeScript and esbuild are build tools.
Installed package license notices accompany the bundle. The accepted fonts,
Hermes mark, theme buddy and CC0 Kenney-derived soft press/close samples are
reused with their existing notices. No generated visual media was added.
