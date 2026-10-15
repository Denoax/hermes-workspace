# Codex integration

Use this reference when Mani asks to install or propagate the policy. Saving the personal skill in ChatGPT Work does not prove installation on a separate computer or adoption by an already-running agent.

## Personal skill

- Keep the complete `reference-led-design` folder, including `SKILL.md`, `agents/openai.yaml` and its references.
- In ChatGPT desktop, find the saved skill on the Skills page. Explicitly invoke it in Codex as `$reference-led-design` or select it from `/skills`.
- For a separately installed local Codex, place the complete folder at `~/.agents/skills/reference-led-design`, or at a repository's `.agents/skills/reference-led-design` for project-only use. Preserve or back up an existing version instead of overwriting unrelated files. Avoid duplicate installations with the same skill name.
- Verify it appears in `/skills` and load it before continuing design work. Codex detects local skill changes automatically; restart if discovery has not updated. Do not claim that remote saving alone achieved this check.

Implicit invocation is enabled in `agents/openai.yaml`. Matching still depends on the host loading and selecting the skill; this is guidance, not a technical lock on tools.

## Standing instruction for local Codex

For the user's requested permanent policy, merge the following block into the appropriate global or project instructions without replacing unrelated rules. Global Codex instructions normally live in `$CODEX_HOME/AGENTS.md` (default `~/.codex/AGENTS.md`); respect an existing `AGENTS.override.md` that takes precedence. Verify the instructions actually load in a fresh local session. Do not edit a separate machine's files without access or claim to have done so.

```markdown
## Mani's reference-led design policy

Every Codex prompt, instruction pack or continuation brief written for Mani must explicitly require reading and applying $reference-led-design, and carry the operative source rules forward when the receiving agent cannot access it. Do not rely on implicit matching alone or add unrelated visual research to nonvisual tasks.

For visual design, UI, websites, portfolios, layouts, animation, 3D scenes, assets, plans and visual reviews, read and apply $reference-led-design before making visual decisions. Reuse approved work; inspect real published references and original/official documentation; adapt their principles in original code. Do not use model-generated visual media as assets, concept authority or a missing-asset fallback unless Mani later explicitly requests that particular generation task. Do not add unsolicited AI styling or fake product telemetry. Verify actual implementation and continuous motion, and report unresolved checks honestly. If the skill is unavailable, apply these rules directly and identify the installation gap while continuing independent work.
```

Keep the local instructions and skill version aligned; do not treat an old generated concept or earlier handoff as authority over the user's later policy. For the existing portfolio, read `portfolio.md` as well.

Official installation/discovery guidance: https://learn.chatgpt.com/docs/build-skills
Official instruction precedence guidance: https://learn.chatgpt.com/docs/agent-configuration/agents-md
Checked 6 October 2026; recheck official documentation if installing into a host with different discovery behaviour.
