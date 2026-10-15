# Real permissions

## User experience

Use an always-visible compact Permissions selector near the composer, independent of model selection and reasoning. The same policy is editable in Settings. Show a clear current mode and the actual selected workspace. Keep the user's chosen policy when switching models. Use plain labels; do not expose unexplained sandbox configuration jargon.

| Mode | Actual behavior |
| --- | --- |
| Chat only | Local inference and explicitly attached context. No autonomous search, file changes or execution. |
| Ask before actions | The model may propose supported actions; approval is required before actions outside existing scoped read grants. Show the action, affected resources and consequences. |
| Workspace agent | Permit enabled reads/writes inside the selected app workspace and qualified guest execution. Network/search remains a separate scope. Host changes and external publication still need explicit approval. |

Use a Custom state if granular settings differ from the presets. Do not silently broaden a mode after reload, model change or a tool failure. Choose Chat only as the initial policy for existing conversations without an explicit grant.

Granular controls must map to working, enforced capabilities:
- read selected project files / uploaded context;
- edit copies in the selected app workspace;
- run supported commands in a qualified guest;
- search using the actually configured provider (label Wikipedia if it remains Wikipedia-only);
- microphone recording (app consent plus browser permission; explain browser denial and release tracks after recording);
- apply reviewed changes to original host files: separate scoped diff approval, never implied by Workspace agent.

Unsupported actions must be visibly unavailable with an honest reason. Implement the supported workflow end to end instead of exposing fake switches. Do not claim arbitrary shell access when only fixed allowlisted VM tasks exist. If expanding task types, extend and verify the guest/native contract while retaining path, timeout, process ownership and network limits.

An approval card offers Allow once, Allow for this session (only for a narrow resource/action scope) and Deny. No permission is granted by text the model writes. A denied action stays denied after reconnect or model retry. The user can revoke a grant without opening a new conversation.

## Enforcement

Enforce at the authenticated server and the final dispatcher. Hiding controls, changing a system prompt or storing a checkbox in localStorage is insufficient.

- Server-held, versioned policy bound to user/project/conversation. Validate requested capability and exact resource scope before dispatch.
- Approval tickets bound to the actual normalized action, conversation, model-run identity, policy version, arguments/command hash and relevant file base hashes. One use, expiry, atomic consume and stable idempotency.
- The model, a guest, an uploaded file, search result or tool output cannot grant policy or forge approval.
- Resolve and constrain file paths using descriptor-based checks where needed. Reject traversal, symlink escape, stale base versions and writes outside the selected workspace. Diff application to originals gets a separate review.
- Use the qualified guest for execution; no host-shell fallback. Filesystem limits must be enforced by the actual runtime, not a string prefix check. Enforce guest/network boundaries and provider access separately from approval decisions.
- Separate model output from actionable commands. Parse only the supported tool schema, validate arguments, apply tool/result limits, step/time budgets and loop termination.
- Revoke pending tickets after policy changes. Cancel owned in-flight work where supported and state honestly which completed effects cannot be undone.
- Store a minimal audit of requested/allowed/denied/executed actions and policy changes without credentials or unrestricted prompt/file dumps.

Protected native admission is a separate control plane. A permissions mode cannot repair a missing trusted socket, grant UID 0 or bypass root peer checks. Ordinary text chat should require no execution/network approval.

## Meaningful checks

Exercise actual UI → API → dispatch → guest/workspace/result flows, including direct denied API attempts, cross-conversation tickets, replay/expiry, policy revocation, model-emitted escalation attempts, path/symlink escape and cancellation. Verify that the mode and granular choices survive reload and model changes.

Official Codex documentation separates execution boundaries from approval policy and notes separate controls for tools such as MCP and browser access. Use that principle for Hermes; these custom modes are not a claim that Hermes runs the Codex sandbox.

Sources inspected for the principle:
- https://developers.openai.com/codex/permissions (redirected to https://learn.chatgpt.com/docs/permissions during this review)
- https://developers.openai.com/codex/agent-approvals-security

Do not modify Mani's Codex settings as part of this work.
