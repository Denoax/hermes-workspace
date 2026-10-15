# Source record

Historical pre-v4 record. Current implementation and evidence are described in
[production v4](../docs/PRODUCTION_V4.md) and the [current source record](../docs/LOCAL_CHAT_SOURCES.md).

Principal visual reference: Mani's installed Paseo 0.11.2 desktop and owned Kona theme, inspected natively and in the installed SDK/source. The adaptation uses its restrained Noto typography, three-pane workspace/conversation/review arrangement, dark surfaces and blue selection color. Existing theme icons are reused. No new raster artwork or generated media is used.

The installed `@getpaseo/plugin` 0.11.2 provider request/context exposes no trustworthy originating local/remote client identity at the Lab mutation boundary. Adding a Lab provider there could not enforce the requested local-only distinction while preserving normal Codex clients. The documented dedicated loopback fallback therefore implements the same bounded native broker interface; Paseo plugins/configuration/defaults remain unchanged.

Official extension/security references inspected:
- https://paseo.sh/docs/custom-providers
- https://paseo.sh/docs/plugins/providers
- https://paseo.sh/docs/security
- https://wiki.hypr.land/configuring/code-snippets/
- https://wiki.hypr.land/Configuring/Basics/Binds/

Actual Hyprland is 0.56.2. Its installed Lua configuration and native dispatch results govern focus/float/size behavior; public snippets were insufficient for every action. The live sidebar IPC verifies Hermes at the former Steam slot and repeat activation with one app. The central display was DPMS off during attempted panel capture; no screenshot or physical input approval is claimed from IPC alone.

Pinned Hermes 63279301bcbdc185c1b07b98a9312eb0c862f26d source governs wire compatibility. The isolated registry produces sorted schemas; tool results retain `name` while internal `tool_name`/timestamps are stripped; final summaries may omit tools. The relay accepts only these narrowed documented shapes and fixed tool names. Its prior default no-tool profile remains enforced.

B08's public fixture contains expected_keys=["outputs"], but the original native runner sends only prompt. That prompt says requested keys without naming them. Both historic maps also have incorrect arithmetic. The new labelled tool-assisted profile supplies only the missing public schema and task formula, never oracle values/grader authority. Original prompts/scorer/receipts and matrix gate remain unchanged.

Offline C++ data comes from Ubuntu's pinned Noble archive Release/Packages hashes, authenticated using the archive keyring from the previously signed 20260926 base image. The signature key is F6ECB3762474EDA9D21B7022871920D1991BC93C. The compiler lock records 36 missing packages, exact URLs/SHA-256s and ZIP metadata. Package data is extracted only in disposable guests; no maintainer scripts or host package changes occur. This old pinned compiler is not advertised as the current security baseline. `scripts/rebuild_compiler.py` reproduced the exact compiler ZIP SHA-256 08b4768c5e16e95dd17bc457a2e937f87e9b1acaadf303bfaa024014709bcdd3. Runtime ISO contents are pinned; byte reproduction of ISO recording timestamps is not yet claimed.

Actual UI evidence and a short CDP screencast live under evidence/. They cover scripted browser interactions and frame inspection; physical input/device review and human visual/motion approval remain separate. Native VM/model receipts are added only after protected execution succeeds.
