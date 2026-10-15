# Repository presentation sources

Read and apply `$reference-led-design` for visual continuation. Reuse the actual
interface and licensed source assets, preserve approved work, and inspect rendered
output. No model-generated media, fake telemetry or fabricated model results.

The composition follows the inspected [portfolio](https://github.com/Denoax/portfolio)
presentation: a wide motion banner, centered identity, actual interface gallery,
paired themes, controls, architecture, validation and credits. The existing
[Kona Desktop](https://github.com/Denoax/konata-hyprland-dotfiles) README was also
inspected and confirmed by Mani as the requested Kona reference. Its artwork is
not reused. The shared structure is adapted to Hermes's actual content and
monochrome interface rather than copied as a desktop/anime theme.

- `banner.html` is original typography and CSS around actual Hermes captures.
  It uses the same existing Bebas Neue/DM Sans fonts and exact Hermes icon as the
  app. No brand image was generated.
- `banner.png` is the active closed-Settings README/profile header. `banner.gif` is the historical motion version of the same composed
  banner with the actual interface recording inside the frame. The composition is
  presentation media, not an unedited live application capture. The latest owner
  request keeps Settings closed in both active headers; the separate interaction
  gallery retains the motion example.
- `social-preview.png` is the matching 1280×640 solid-background image, below
  GitHub's 1 MB social-preview limit. Upload it under Repository Settings →
  Social preview; adding it to the README does not set that separate field.
  Mani requested the fresh closed-Settings view, larger “Local workspace” text,
  “Hermes × Your local model” identity and removal of the outer documentation
  caption. Fixture provenance remains here and in the repository README.
- `workspace-*.webp`, `settings-*.webp` and `files.webp` are actual current browser
  captures, converted losslessly. Documentation content is explicitly labelled
  and isolated from the private catalog. It is not live model evidence.
- `workspace-motion.mp4` retains the original timestamps of the real pointer and
  keyboard tour. `interaction.gif` resizes/samples the full recording at its
  original pace, silently. The composed banner uses the same pace. Palette
  conversion is lossy; a GIF does not establish physical display smoothness.

`capture-sources.json`, `motion-source.json` and `banner-sources.json` identify
the exact source/output bytes and current served UI assets. New documentation
captures do not replace the technical acceptance evidence in the separate review.

Rebuild on the configured workstation, with the existing authenticated review
browser harness and ffmpeg:

```sh
python3 scripts/github_showcase.py capture
python3 scripts/github_showcase.py motion
python3 scripts/github_showcase.py serve
```

Leave the loopback-only server running in that terminal, then run
`python3 scripts/github_showcase.py compose` in another. It captures `banner.html`
at1280×460 and its `?format=social` variant at1280×640, with the local font routes
served from `workspace/ui/fonts`. Ctrl+C stops the documentation server. It serves
only showcase files and the two named font assets. Source font licenses,
the Hermes icon notice, functional vector and sound notices remain in
`workspace/ui/licenses` and `workspace/ui/sounds`.

GitHub's current [social-preview documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview)
specifies PNG/JPG/GIF under1 MB and recommends1280×640. A repository push and
setting its social preview are distinct publication operations.

An initial banner export froze its video inset on the first frame. It was rejected
before delivery. The final exporter decodes the original recording into source-
paced frames, composes each real frame and verifies distinct GIF output frames.
