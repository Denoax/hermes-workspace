# Placement, hierarchy and motion

Read and apply `$reference-led-design`. Values here are proposed Hermes design
choices and native acceptance targets, not measurements of another app.

| Action | Surface and anchor | Close/focus behavior |
| --- | --- | --- |
| Folder/conversation ellipsis | Compact menu adjacent to that exact row, constrained to viewport | Escape returns to ellipsis; outside click respects its new target; opening changes no viewed conversation or draft |
| Edit, rename or move | Focused dialog reached from row menu | Explicit target ID; Cancel changes nothing; return to original row control |
| Delete | Focused named-target review with the existing two-stage R09 core | No deletion on menu open; preserve server controls; after deletion use a surviving logical focus target |
| Composer plus | Anchored menu above the plus, flipping only when necessary | Keyboard traversal/typeahead and logical Tab exit; Escape returns to plus; chooser cancellation preserves draft |
| Reasoning | R01 popover above brain control, edge constrained | Preserve two actual detents; Escape returns to brain; no fake extra native effort levels |
| Files / Details | Nonmodal workspace-edge sheet below header | No shell/composer reflow; Escape/outside close, direct header switching; return to actual trigger |
| Settings | Centered native modal with preferences, permissions and disclosures | Background inert while open; Tab stays inside; Escape/close returns to Settings |
| Recording/import/search forms | Focused modal for the actual operation | Keep stop/cancel explicit; native chooser/device permissions remain separate boundaries |
| Project selection | Project overview with quiet parent/current hierarchy | New conversation creates a visible composing view; breadcrumb recovers overview |
| Stream growth | Follow only near the current end | Scrolled-up reading remains stable; explicit Jump to latest resumes follow |

Start with 18px main-surface radii, 16px dialogs/sheets, 10px action menus and 6px
menu rows. Keep the reference components' internal anatomy independent. Use a
small 4/8/12/16/24 spacing scale, consistent icon stroke and optical alignment,
and useful title contrast. The rail is slightly wider on large screens. Long
names need accessible full text, sensible truncation and correct current context.
Do not squeeze navigation merely to preserve an arbitrary screenshot proportion.

The candidate uses 140ms menu entry and 160ms surface transitions with restrained
travel; sheets stay opaque during movement. The existing six Rare UI cores,
brain/material/HUD behavior and buddy logic are preserved. Verify rapid reversal,
switching and native reduced motion before approving those values. The candidate
does not yet add a shared retained exit state for anchored menus; inspect whether
their immediate removal feels correct under frequent use. Add a short nonblocking
exit only if actual playback shows a benefit, with departed controls immediately
inert and no stale focus restoration. Do not claim that every transition is done.

The placement primitive uses body portals, current trigger rectangles, visual
viewport offsets and available height. It coalesces resize/scroll updates and
cleans up observers/listeners. Complex nested surfaces, alternate browsers,
screen-reader behavior and mobile visual keyboards remain native review work.
Use a maintained primitive if that bounded solution fails; do not grow a pile of
magic offsets. Modal geometry uses browser dialog centering independently of its
trigger; an anchored menu uses the trigger as its visual origin.

Do not add eyebrows, marketing footers, fake progress, providers that are not
linked locally, decorative capability badges or background shader spectacle.
Keep the accepted simple sound pair and actual mute/volume behavior. Preserve
keyboard focus visibility. A white focus outline is not a substitute for good
alignment; removing it is not a polish fix.
