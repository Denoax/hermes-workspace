# V5 critique

V5 is functional, but its presentation still exposes the way components were
assembled. The app needs a clearer relationship between what is selected, what
an action affects and where its controls appear. More decorative motion would
not resolve that relationship.

## Review basis and limits

The pinned GitHub tree, all 403 source blobs, v5 verification/reference documents
and the two published v5 desktop screenshots were inspected. The screenshots
show actual populated review data in light and dark themes. Other published
390px/gallery assets are historical and are not silently promoted to v5 proof.
The full local review ZIP and its unpublished recordings are unavailable here.
Reported acceptance is 18 PASS, 11 PARTIAL, 4 BLOCKED, 3 UNVERIFIED; that count
comes from the supplied report, not an independent recount of the archive.

I can identify spatial problems in stills and state problems in code. I cannot
truthfully label an unavailable animation choppy, a physical speaker pleasant,
or the finished native app smooth. Timing numbers in code identify review risks,
not measured presentation quality.

## What my previous direction got wrong

The neutral palette improved coherence, but I gave large containers, full-row
selection fills and rounded controls too much authority. The result needs more
hierarchy within the shell. I also hid secondary row controls too aggressively.
That made the screen quieter while weakening discoverability. Finally, matching
eleven component references did not establish a consistent application-level
interaction model. V6 addresses those decisions directly.

## Findings

| ID | Evidence and problem | Consequence | V6 response |
| --- | --- | --- | --- |
| C01 | Published stills show a selected conversation alongside a project dashboard; source renders that dashboard whenever messages are empty and a folder is selected. | Empty conversations look like project views. | Add explicit new-conversation mode; selected empty conversations show conversation content. |
| C02 | Conversation overflow changes session and project before opening management. | Managing one row switches the work context and draft view. | Capture a separate management target; open/rename/move/delete operate on its ID. |
| C03 | Folder/conversation ellipses open a large form at the top right. | The result appears far from the object clicked. | A short row-anchored menu precedes the edit or deletion dialog. |
| C04 | Every Panel uses the same nonmodal `dialog.show()` and top-right location. | Settings, file browsing, recording and destructive review have identical behavior despite different purposes. | Workspace sheets for Files/Details; true modal dialogs for focused work. |
| C05 | Composer popovers use fixed negative offsets inside an overflow-hidden shell. | Small windows, zoom and virtual-keyboard displacement risk clipping or wrong placement. | Portal to body, measure the real trigger, flip and constrain to visual viewport. |
| C06 | Menu Escape always focuses the message input. | Keyboard focus loses the action's origin. | Return to its actual trigger; move normally through other controls with Tab. |
| C07 | Details trigger ID differs from Panel's inferred title-to-ID mapping. | Focus restoration relies on incidental active focus. | Explicit known trigger mapping, saved row invoker and safe fallback after deletion. |
| C08 | New activity calls `scrollIntoView` without checking the reader's position. | A reader above the latest response can be pulled away. | Follow only near the end; expose Jump to latest and clean up observers. |
| C09 | Folder and conversation use equally strong selection fills. | Parent context competes with the current page. | Quiet parent context; one primary selected conversation or overview. |
| C10 | The screenshot's narrow rail truncates most meaningful names and contains two independent scroll regions. | Scanning and understanding hierarchy require extra effort. | Slightly wider desktop rail, compact rows and full title access; native review must assess long-list scrolling. |
| C11 | The long project name occupies a large two-line hero heading. | Metadata dominates the useful folder/conversation list. | A 22px working title, tighter action spacing and correct singular/plural counts. |
| C12 | Project New conversation leaves the overview visible. | The action has little visible effect. | An explicit blank conversation view with project breadcrumb recovery. |
| C13 | Unicode music/search/file symbols mix with polished SVG components. | Stroke, optical size and meaning differ across platforms. | Independently authored SVG family for those utility controls; sound state stays tied to the existing module. |
| C14 | Hover-only or faint overflow controls compete with clipping and counts. | Secondary actions can be missed. | Persistent, restrained but visible actions; stronger hover/focus and larger coarse-pointer targets. |
| C15 | All 40px minimum controls, 17px menus and large panel radii flatten the hierarchy. | A tiny action can look as heavy as a main surface. | Separate row/menu/control/dialog scales; preserve the intentional reference components. |
| C16 | File reading and editing share a narrow generic panel. | Content inspection feels cramped. | A wider workspace-edge Files sheet; retain original-host approval boundaries. |
| C17 | The top HUD changes width and may share header space at certain sizes. | It needs real busy/approval/error/zoom collision review. | Preserve factual R03/R04 behavior; do not award full motion parity from stills. |
| C18 | Long-running metal reflections and multiple independent transitions remain active. | Isolated GPU cost and lifecycle behavior remain uncertain. | Measure during both model workloads; stop hidden work and respect reduced motion. |
| C19 | Native import previously required operator intervention to float/focus KDialog. | Normal users cannot rely on the assisted result. | Fix and prove unassisted parenting/focus in the native environment, without global desktop workarounds. |
| C20 | Live voice, hidden lifecycle, guest qualification and physical review remain incomplete. | UI polish must not imply those capabilities passed. | Retain every blocked/manual row and truthful unavailable state. |

The candidate directly addresses C01–C16 where source changes can be prepared
here. Actual native verification remains required for each. C17–C20 need the
recordings, devices or protected runtime and remain explicit acceptance work.

## What should stay

The current local-model inventory, normal/candidate chat pipeline, history,
draft/attachment ownership, cancel/retry identities and server-held permissions
have specific working contracts. Preserve them. Keep the owned cursor buddy,
accepted sound files/defaults, factual status, full interactive folder component,
real search citations and original deletion core. Focus-visible outlines are
necessary; refining their weight is different from removing keyboard feedback.

The prepared code remains a candidate. Its independent placement primitive is
limited to these single-level, body-portaled app surfaces. If native tests expose
platform, focus or collision gaps, integrate a maintained primitive such as Radix
or Floating UI through a pinned dependency and rerun acceptance. Do not accumulate
special-case offsets to defend the candidate.
