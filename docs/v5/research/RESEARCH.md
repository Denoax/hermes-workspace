# A coherent direction for the next Hermes pass

The strongest direction is to preserve the exact Awsmd shell, Mani's portfolio identity and buddy, and the already selected Rare UI/Inspora controls. New references should improve the spaces between them: hierarchy, action discovery, transitions, readable state and reliable input. Each source gets a specific job. A larger collection of effects would add more integration work without resolving the present quality gaps.

This research assessed 19 selected sources and checked 31 discovery routes. Some are visual studies, some primary implementation documentation, and some unavailable leads. It is a bounded survey of the relevant design landscape, not an exhaustive search of the internet. The registers keep those distinctions explicit.

## The most useful references

| Reference | Useful contribution | Evidence and limit |
| --- | --- | --- |
| [Awsmd: exact Task Management Dashboard](https://dribbble.com/shots/21673507-Task-Management-Dashboard) | The existing shell: frosted gray framing, white inset rail, monochrome hierarchy and restrained header actions. | Original static shot inspected directly. No production behavior implied. |
| [Linear: March 2026 refresh](https://linear.app/now/behind-the-latest-design-refresh) | Quiet supporting navigation, strong content hierarchy, stable header roles and softer visual separation. | Primary design-team case study and published before/after images inspected. |
| [Jordan Hughes: Untitled UI sidebar](https://dribbble.com/shots/18147616-Sidebar-navigation-Untitled-UI) | Expanded/collapsed navigation anatomy, grouping and alignment. | Pinterest lead traced to the named original; original image inspected. |
| [Brainwave navigation](https://dribbble.com/shots/20959849-Sidebar-Navigation-for-Brainwave-AI-UI-Kit) | Chat-specific navigation and compact collapsed state. | Named original inspected. This does not prove identity with the older R10 pin. |
| [Rauno's Craft](https://rauno.me/craft) and [Exclusion Tabs](https://rauno.me/craft/exclusion-tabs) | Small interactions with clear state and a strong authored feel. | Prototype states exercised. No uninterrupted timing/performance capture. |
| [Emil Kowalski: Train Your Judgement](https://emilkowal.ski/ui/train-your-judgement) | A practical way to compare popovers, interruptions and high-frequency controls. | Paired popover examples exercised; use as a review method rather than a preset animation pack. |
| [Lusion Labs](https://labs.lusion.co/) | Sparse chrome and composition that gives the main content room. | A published 2023 Awwwards image was inspected. Current live rendering was unavailable here. |
| [Things](https://culturedcode.com/things/) | Task hierarchy and project clarity. | Primary product imagery partly inspected; native app not operated. Apple lists Things 3 among its 2017 award winners. |
| [Flighty case study](https://developer.apple.com/news/?id=970ncww4) | Compact, persistent, useful status. | Apple's 2023 Interaction award and case study; the native app was not operated. |
| [Raycast navigation](https://manual.raycast.com/navigation) | Searchable actions, keyboard discovery and predictable navigation. | Primary documentation read; an installed app was not tested. |
| [Paper Liquid Metal](https://shaders.paper.design/liquid-metal) | A possible authored implementation aid for matching R02's material. | API and pinned upstream license inspected. Demo controls rendered, but the canvas was blank here. |

The exact Awsmd image is especially useful. It establishes a neutral gray glass shell and a white inset navigation surface. A green cast, heavy grain, jagged borders or generic rounded boxes cannot be justified by saying the overall dashboard is “inspired by” that shot. The actual comparison must use the same visible region and state. Its background artwork is not licensed as a Hermes runtime asset; author a suitable background in code and record any adaptation.

The Linear advice should improve organization inside that established shell. Its [2024 redesign article](https://linear.app/now/how-we-redesigned-the-linear-ui) is another primary source for the team's design process. A public [community thread](https://www.reddit.com/r/Linear/comments/1ipn0pt/i_love_the_linear_ui_in_every_way/) contains both enthusiasm and workflow complaints. That is useful qualitative feedback, not a representative usability study.

## What “highly reviewed” means in this dossier

Recognition is recorded separately from visual fit.

- CSS Design Awards names [Lusion v3 Website of the Year 2023](https://www.cssdesignawards.com/woty/lusion-v3/44311/) with a final judge score of 9.27. That score belongs to the dated v3 entry, not the different current 2026 homepage.
- [Apple's 2017 winners](https://www.apple.com/newsroom/2017/06/apple-design-awards-celebrate-the-best-in-innovation-and-creativity/) include Things 3. [Apple's 2023 winners](https://developer.apple.com/design/awards/2023/) include Flighty for Interaction.
- [Devouring Details](https://www.awwwards.com/sites/devouring-details) has an Awwwards Honorable Mention listing. It does not give every Rauno prototype the same award.
- Named designers and published source establish provenance better than anonymous reposts. They do not prove universal quality or that every embedded asset has a suitable reuse license.
- GitHub snapshots show adoption: Motion Primitives 6,657 stars, Magic UI 22,672 and Uiverse Galaxy 13,523 at retrieval. These are time-sensitive source snapshots, not component reviews or evidence of accessibility/performance.

Do not reduce those different signals to an invented common rating. The final choice should be based on actual Hermes content and behavior, using the source as a concrete comparison.

## Pinterest findings

Pinterest was valuable for discovery, but a sign-in overlay limited full inspection in this browser. No account was accessed and no overlay was removed through hidden state. The public titles led to original creator pages:

1. [Untitled UI sidebar pin](https://www.pinterest.com/pin/284430532710452399/) → Jordan Hughes's original sidebar shot.
2. [Task Management Dashboard pin](https://www.pinterest.com/pin/1111192908063344824/) → same-title Awsmd source, with image equality for that pin still unverified.
3. [Brainwave navigation pin](https://in.pinterest.com/pin/dashboard-navigation-design--218706125652214893/) → Tran Mau Tri Tam for UI8.
4. [Brainwave settings pin](https://www.pinterest.com/pin/542613455123519448/) → [original settings shot](https://dribbble.com/shots/21305840-Setting-Modals-for-Brainwave-AI-UI-Kit), text inspected; full visual review pending.
5. A chatting-dashboard pin remains unresolved and is excluded from the approved direction.

The user's existing R10 pin is separately retained. Finding another Brainwave pin does not prove it is the same image or solve the earlier canonical-pin discrepancy.

## Reuse the research and the appropriate code

The 11 exact references in `research/REFERENCE_LOCK_v4.json` remain required. Reuse their inspected clips, original creator identities and source pins. There is no reason to rediscover them during every context window.

The six Rare UI originals are already integrated into the baseline application. Keep their source-level visual core, notices and attribution, then connect actual state and callbacks. Fix CSS interference and surface sizing rather than replacing them with generic lookalikes. The pinned license is not a blanket permission to redistribute an independent component collection.

Four additional source repositories have exact commit and license-file identities in `research/REUSE_SOURCE_PINS.json`:

| Source | Reviewed license at the pin | Appropriate use |
| --- | --- | --- |
| paper-design/shaders | Apache-2.0 plus upstream NOTICE | Consider a small material prototype for the upload button. |
| ibelick/motion-primitives | MIT | Study a specific transition after reviewing source and semantics. |
| magicuidesign/magicui | MIT | Reuse only a component that solves an actual gap; Pro products are separate. |
| uiverse-io/galaxy | MIT | Trace the selected creator/item and inspect its external assets. |

Paper's current upstream licensing differs from some older forks surfaced in search. Use the pinned source, preserve the relevant notices and confirm the installed package matches it. This is a source record, not an audit of every dependency or a conclusion about the original Inspora clip's undisclosed implementation.

For the existing Files menu bug, headless [Radix popover](https://www.radix-ui.com/primitives/docs/components/popover) and [React Aria modal](https://react-aria.adobe.com/Modal) documentation provide semantic references. Reuse the current stack where it can satisfy the contract; adding several overlapping UI engines would make integration harder.

## What to carry into the next prompt

The new prompt should require one reference-to-implementation record per affected surface. It should name the exact source, the observed detail, the code path, the allowed adaptation and the remaining difference. A source screenshot, build result or test total cannot stand in for the running app.

Keep the app fast while local inference uses the GPU. Prototype any shader at the actual small control size, cap work, stop hidden/offscreen activity and measure during generation. The upload material is the useful scope; a full-screen decorative WebGL backdrop would compete for the same hardware. No performance target is assumed achieved here.

A creator-attributed native-chat concept was also inspected and rejected as a whole-app direction. Its fictional render workflow and decorative provider imagery conflict with Mani's brief. Attractive published work still needs a fit/provenance check.

## Why the continuation loop matters

“Cache” and context are different mechanisms. OpenAI's [prompt-caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching) describes an efficiency mechanism. [Compaction](https://developers.openai.com/api/docs/guides/compaction) carries prior state using fewer tokens. Neither is a durable requirements database or proof that the work is complete.

The recent Hermes failure also exposed a verification mismatch: real isolated model trials did not establish that the ordinary production pin kept working after cleanup. More context alone would not close that gap.

Official [Codex long-horizon guidance](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) supports checkpointed milestones, validation and a living record. The [ExecPlan recipe](https://developers.openai.com/cookbook/articles/codex_exec_plans) is an archived planning convention, not a reason to adopt its old model recommendations.

Anthropic's [2025 harness article](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) reports premature completion and incomplete end-to-end verification as failure modes. Its [2026 follow-up](https://www.anthropic.com/engineering/harness-design-long-running-apps) discusses context-reset handoffs and optimistic self-evaluation, particularly for design. Those are findings from its own setup, not guaranteed performance for Hermes or Codex.

This package's loop turns those concerns into a project-specific workflow: immutable requirement IDs, bounded work, source-bound evidence, checkpoints, recovery and a separate human-review state. It does not remove context limits, rate limits, hardware constraints or native authentication. It makes unfinished work explicit and recoverable.
