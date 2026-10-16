# V6 reference research

Read and apply `$reference-led-design`. This pass reuses the previous research
and exact R01–R11 provenance, then investigates the gaps found in v5. It does not
claim a second exhaustive tour of every inspiration hub. No generated visuals,
copied product artwork or invented reviews were used.

## Sources and inspected evidence

| Source | What was actually inspected | Assigned role and limits |
| --- | --- | --- |
| [Emil Kowalski: Good vs Great Animations](https://emilkowal.ski/ui/good-vs-great-animations) | Original article, interactive Options menu, settled render and ArrowDown focus. The browser measured its menu at 224×242px with 6px radius and origin below the surface. | Trigger-relative origin and restrained menu geometry. Candidate values are independent adaptations. Two state captures do not establish continuous timing. |
| [Raycast redesign, Thomas Paul Mann](https://www.raycast.com/blog/a-fresh-look-and-feel) | Primary 2022 rationale and published action-bar imagery in browser. James McDonald's consistent outline-icon work is credited there. | Contextual action grouping, discoverable frequent actions and icon consistency. Native Raycast was not operated, and its assets were not copied. |
| [Linear: March 2026 refresh](https://linear.app/now/behind-the-latest-design-refresh) | Current primary article; earlier directly inspected before/after imagery was reused. | Quieter chrome and stronger content hierarchy within the established shell. No copied branding or claim that Hermes is Linear. |
| [Rauno Freiberg: Invisible Details](https://rauno.me/craft/interaction-design) | Original primary essay; prior Craft interaction study reused. | Input continuity and reducing interaction friction. No claim of inspecting undisclosed implementation. |
| [NN/G: Kate Kaplan's contextual menus study](https://www.nngroup.com/articles/contextual-menus-guidelines/) | Full primary research article, dated November 2025. | Secondary local actions, visible contextual triggers and consistent placement. This is usability evidence, not a beauty score. |
| [W3C menu-button pattern](https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/) | Official keyboard/role/focus contract. | Actual menu behavior; labels alone cannot implement a menu. |
| [W3C modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) | Official modal focus and dismissal contract. | Native modal behavior for focused forms. Assistive-technology testing remains necessary. |
| [W3C disclosure navigation example](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/) | Official example and its explicit implementation/support limits. | Honest disclosure navigation rather than an incomplete tree widget. No example code copied or conformance inferred. |
| [Floating UI flip](https://floating-ui.com/docs/flip) and [size](https://floating-ui.com/docs/size) | Original implementation documentation. | Collision and available-space requirements. Candidate code is independently authored for a bounded case, not a general replacement. |
| [Radix Popover](https://www.radix-ui.com/primitives/docs/components/popover) and [Dropdown Menu](https://www.radix-ui.com/primitives/docs/components/dropdown-menu) | Official positioning, focus and layering APIs. | Maintained fallback architecture if native tests expose gaps. No new dependency was silently introduced. |
| [web.dev animation guide](https://web.dev/articles/animations-guide) | Primary browser-performance guidance. | Prefer transform/opacity for surface movement; actual workload measurements still govern. |
| [WCAG target-size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Official criterion and exceptions. | Target spacing/size review. Proposed 34–36px desktop rows and 44px coarse-pointer targets are Hermes choices, not a blanket WCAG mandate. |
| [Jordan Hughes' original sidebar](https://dribbble.com/shots/18147616-Sidebar-navigation-Untitled-UI) | Original page refreshed; earlier directly inspected image reused. Its Pinterest lead failed to fetch this pass. | Hierarchy and useful row density. The related pin does not resolve R10's canonical identity. |

Apple's Popovers page returned only a JavaScript shell through text retrieval;
no unseen Apple recommendation is used as supporting evidence. The earlier
Lusion Labs archive, Awsmd shell, Things, Flighty and portfolio study remain in
the bundled v5 research with their original dates and access limits. Lusion's
dated recognition does not establish the current live homepage's behavior.

## Design conclusions

Use a single spatial rule per action category. Keep local secondary actions near
their row, conversation inputs near the composer, browsing at the workspace edge
and focused forms in a centered dialog. Make the current page visually distinct
from its parent location. Keep useful content at a working scale and let small
surfaces carry less visual weight than main containers.

Motion should explain entry, exit and continuity. It must tolerate reversal,
repeated input, Escape and context changes without trapping focus or moving hit
targets. A persistent decorative effect cannot consume the same attention as a
real running task. These are adaptations to Hermes' actual workflows, not an
assortment of unrelated showcase effects.

The existing eleven references remain recorded. The current user request allows
reorganizing their application-level placement; preserve their recognizable core,
truthful model capabilities, rights/notices and all functional controls. Record
concrete changes rather than claiming global pixel-perfect identity.
