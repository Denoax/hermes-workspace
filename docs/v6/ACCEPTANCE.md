# V6 production acceptance

Read and apply `$reference-led-design`. Proposed numerical thresholds below are
Hermes regression criteria. Source, unit tests, native observations and human
approval are different evidence categories.

## Context and navigation

Create positively identified harmless review records. Keep unknown/user records
and all later drafts/messages. Select empty conversation A in project P: show its
conversation view, not P's dashboard. Click New conversation in P: show a visibly
new composing view and focus the input. Use the project breadcrumb to recover
overview. Repeat through filter, collapse, reload and back/reopen where supported.
Current conversation, parent context and overview must be distinguishable.

While A has a draft and attachment, open B's ellipsis. The viewed session, model,
draft, selection and scroll position remain A. Rename/move B using its explicit
ID. Cancel changes nothing. Deletion review names B; only confirmed deletion of
the known empty test record is permitted. Preserve A throughout. Repeat folder
actions on an unselected branch. A stale/deleted target produces a clear error,
never an operation on the current session by fallback.

## Menus and surfaces

Exercise row, plus and effort popovers at top/bottom/left/right edges, actual
desktop scaling, 200% zoom, 390px width and a short window. Record visual viewport,
DPR, zoom and trigger/surface rectangles. Surfaces remain within the proposed
8 CSS px viewport inset, preserve the trigger's size/position within 1px, and
scroll internally when constrained. No clipping by shell or detached placement.

Enter/Space opens the actual control. Menu arrows/Home/End skip disabled actions;
typeahead and Tab/Shift-Tab move predictably. Escape returns to the originating
trigger. Outside click preserves the new clicked focus target. Opening a dialog
from a menu cannot restore focus over its input. Closing a menu must not erase a
draft, trigger another sound or leave an invisible hit target.

Settings/edit/delete dialogs are actually modal: initial focus is useful, Tab is
contained, background is inert, Escape/close works and focus returns logically.
Deletion of an invoker uses a surviving target. Files/Details remain nonmodal at
useful desktop sizes, switch directly and reserve the actual composer/status area.
They must not cover Send/Cancel, readiness errors or attachment actions. When
space is insufficient, use and verify an explicit focused small-screen alternative.
No accidental shell/header reflow or stale modal backdrop after rapid switching.

## Reading and layout

Scroll well above the end during a real long response. New tokens, approval cards
and attachments cannot pull the reader down. Jump to latest resumes follow.
Repeat with code blocks, image layout, restored history, new conversation, hidden
tab and resize. Observers/listeners/queued frames stop on unmount/context change;
old events cannot affect a different conversation.

Inspect 1280×800,1440×900,1920×1080,390×844 and the user's real scaling in both
themes. Check rail names/counts/branches, heading balance, equal control baselines,
menu paddings, optical icons, borders and actual readable text. Keep compact v5
composer behavior and essential actions. Verify font metadata/weight mapping;
do not simulate a typography pass by changing every font-size number.

## Motion and performance

Review uninterrupted normal-speed open/close/reopen/reversal and rapid alternating
menus, sheets, Settings, effort and deletion. Record each issue before fixing it.
The candidate currently uses immediate popover removal; decide from playback
whether a short nonblocking exit improves it. No delayed hit testing, stale
focus, opaque exit overlays or motion competing with input. Full lifecycle R03/R04,
source search preview, folder hover/flap, voice and actual task states retain
their separate coverage. Do not invent a guest task to fill missing footage.

Measure UI work at idle and during normal/candidate inference. State workload,
sample duration, CPU frame metrics and missing GPU/presentation data. Test reduced
motion/transparency, forced colors, high zoom and lifecycle cleanup. Video encoding
rate is not physical display cadence. Human continuous-motion approval is a real
user observation, not a test result or model taste score.

## Regression and final state

Existing-pin production checks: both real models, contextual follow-ups, history,
reload, stream growth, actual compute cancel, same-ID retry, current draft plus
attachment retention and direct permissions denial. Revalidate related server
contracts without rewriting their security boundaries. Preserve five WAV hashes,
mute/volume, buddy tracking and normal model pins. Keep guest/device/import/reboot
limits exactly scoped. After acceptance workers stop, send fresh production turns
and verify normal Qwen restored/idle at65,536. Return the complete ledger and final
canonical per-row report; no missing requirement is converted into PASS.
