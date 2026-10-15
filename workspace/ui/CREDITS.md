# Portfolio controls, vectors and sound

Navigation is an application port of Mani's owned GooeyNav/navConnection at portfolio commit `bab9d618131842d73dc859ea9946b5210f3dcd83`, originally adapted from Swami Malode / Rare UI. Preserve `licenses/Rare-UI.txt`, `Rare-UI-usage.txt` and the visible Details credit. This application is not a standalone component/template registry.

The Close/projects/details SVG paths are the actual owned portfolio vectors. Other functional icons come from Lucide at `dab294f313897bacaa968b725b3259fa37c17bd1`, including inherited Feather icons by Cole Bemis. Full notices are in `licenses/Lucide-LICENSE.txt`.

The soft press/close clips are Kenney’s CC0 Interface Sounds select_005/select_004, reused byte-for-byte from the owned portfolio’s natural-rate, low-pass and edge-faded candidates. See sounds/SOFT_CLICK_PROVENANCE.json for source/PCM/file hashes and processing. They replace the mouseclick/mouserelease samples rejected by Mani. No randomized banks or generated media; one voice at 12%, with persistent mute. Listening approval is recorded separately.

Inter Medium and Rubik are additional exact portfolio font assets; their OFL notices are included. Typography, control material and shared Close geometry are source-based application reuse. The vanilla WebGL2 port reuses the owned glassOptics/GlassLayer optical kernel and paintPane substrate, with a shared CPU pose feeding instanced tile paint and native arrival eligibility. Source details and adaptations are in the review source map.

# Existing fonts

These exact assets were reused from Mani's `Denoax/portfolio` repository at `219ad286ec587b433a9d212b340d95bf1e574bab`. Original notices are retained in `licenses/`. Git blob and SHA256 identities are in `references/owned-assets.json`.

- Bebas Neue: display headings/brand. See `licenses/BebasNeue-OFL.txt`.
- DM Sans: readable controls and body text. See `licenses/DMSans-OFL.txt`.
- Six Caps: optional short display treatment. See `licenses/SixCaps-OFL.txt`.

The rejected CSS ring motif is removed from the resting view. No generated raster media, invented logo or remote asset dependency is used. Prior captures are evidence of the previous UI, not approval of the new candidate.

# Owned glass and controls

Pure `glassOptics.ts`, `sliderFlight.ts`, and `paintPane.ts` are preserved under `owned/`; `scripts/build_portfolio_ports.py` builds the runtime MJS with an explicitly supplied existing esbuild. Settings geometry and material come from owned `v22.css`/`v24.css`, ThemeToggle vectors/material from the owned component/theme palette, and the shared navigation from the pinned source above. v25 cohort timing and bounded cup travel follow Mani's owned emission recipe rather than the rejected v24 fan. George's Flying Dropdown, discovered through [Inspora](https://www.inspora.design/posts/flying-dropdown-menu), is behavioral reference; no creator runtime or asset license is inferred.

The existing Hermes desktop icon is the exact installed local source asset `apps/desktop/assets/icon.png` at commit `63279301bcbdc185c1b07b98a9312eb0c862f26d`, SHA-256 `d60d164e24fdcf6532133b8ea43c77a201e4b9e9dbc396187b58d51d8590ef52`. Its repository MIT notice is included as `licenses/Hermes-MIT.txt`. No new brand image was generated.

For visual continuation, read/apply `$reference-led-design`: inspect real published/owned sources, preserve the approved work, do not generate substitute visual or audio assets, and distinguish actual rendered/motion/listening evidence from human approval.
