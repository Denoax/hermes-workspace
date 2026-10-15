# Hermes local workspace

Read/apply `$reference-led-design` for visual continuation. Preserve accepted work and use inspected published references; no generated visual media or fake activity.

The current UI and text-chat implementation is described in [the main README](../README.md), [operation and recovery](../docs/LOCAL_CHAT.md) and [source adaptations](../docs/LOCAL_CHAT_SOURCES.md). `frontend` holds the pinned React/Motion source; `ui/dist` is its self-hosted build. The existing launcher, cookie/Host/Origin/CSRF boundaries and loopback binding remain intact.

`conversations.py`, `chat.py`, `models.py`, `attachments.py`, `voice.py`, `search.py` and `reset.py` own chat, persistence and lifecycle. Ordinary conversations have no executable tools. The separately qualified legacy guest pipeline remains in `jobs.py` and the native/guest modules, with its original quotas, leases, reviewed imports and apply contracts. It does not become enabled by opening this app.

The six integrated Rare UI components retain their exact upstream license and visible Settings attribution. Older UI modules and gallery captures are retained for recovery/history; the glass/pixel emission graph is not imported by the current frontend.
