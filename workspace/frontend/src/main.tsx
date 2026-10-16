import {
  useState,
  useEffect,
  useLayoutEffect,
  useRef,
  useCallback,
  type FormEvent,
  type CSSProperties,
} from "react";
import { createRoot } from "react-dom/client";
import { AnchoredPopover } from "./AnchoredPopover";
import { UIIcon } from "./UIIcon";
import { useReadingPosition } from "./lib/use-reading-position";
import { saveManagedConversation } from "./lib/conversation-management";
import { restoreComposingIntent, saveComposingIntent } from "./lib/composing-intent";
import { ManagementError, managementFailureMessage, type ManagementFailure } from "./ManagementError";
import { useFolderImport } from "./lib/use-folder-import";
import { AnimatePresence, MotionConfig } from "motion/react";
import { MessageMarkdown } from "./MessageMarkdown";
import { applyCancellationResult, applyRetryResult } from "./lib/run-receipts";
import { RecordingSession } from "./recording-session";
import AiStatus from "./components/ai-status";
import WebSearch from "./components/web-search";
import FolderImport from "./components/folder-component";
import { VoiceNote, VoiceNoteGroup } from "./components/voice-note";
import TaskList from "./components/task-list";
import DeleteButton from "./components/delete-button";
import {
  Panel,
  Brain,
  Effort,
  MetalButton,
  WorkingIndicator,
} from "./controls";
import {
  PermissionMode,
  PermissionSettings,
  ApprovalCards,
  usePermissions,
  type Action,
} from "./permissions";
import { Buddy } from "./Buddy";
import { ReducedMotionContext } from "./lib/reduced-motion";
import { Recorder, waveform } from "./recording";
import { activityStatus } from "./lib/activity-status";
import { folderTree } from "./lib/folder-tree";
import {
  useDraftAttachments,
  type AttachmentToken,
} from "./lib/use-draft-attachments";
import {
  readSelection,
  sameSelection,
  samePrompt,
  type DraftSelection,
} from "./lib/draft-selection";
import { turnCitationSources } from "./lib/citations";
import {
  bootstrap,
  rpc,
  stream,
  upload,
  terminal,
  audioURL,
  type Folder,
  type Session,
  type Model,
  type Run,
  type Event,
  type Attachment,
  type Search,
} from "./api";
// @ts-expect-error Self-hosted accepted sound module is deliberately outside the bundle.
import { installInterfaceAudio } from "/interface-audio.mjs";

type Message = { role: string; text: string; job?: string };
type Readiness = {
  state: "ready" | "busy" | "repair_required" | "unavailable";
  control: { trusted: boolean; code: string };
  admission: { available: boolean; code: string };
  models?: Record<string, { available: boolean; code: string; detail: string }>;
  detail: string;
  retryable: boolean;
};
type Caps = {
  attachments: boolean;
  folder_import: boolean;
  project_library: boolean;
  recording: boolean;
  transcription: boolean;
  search: { provider: string; configured: boolean };
  text_admission: boolean;
  text_readiness?: Readiness;
  integrations: string[];
};
type Snapshot = {
  messages: Message[];
  runs: Run[];
  after_seq: number;
  activity?: Event[];
  attachments?: Record<string, Attachment[]>;
};
const palette = ["blue", "orange", "green", "purple", "rose", "slate"];
const noop = () => {};
function App() {
  const [connected, setConnected] = useState(false),
    [error, setError] = useState("");
  const [folders, setFolders] = useState<Folder[]>([]),
    [sessions, setSessions] = useState<Session[]>([]),
    [models, setModels] = useState<Model[]>([]),
    [caps, setCaps] = useState<Caps | null>(null);
  const [folder, setFolder] = useState<string | null>(null),
    [session, setSession] = useState<string | null>(null),
    [expanded, setExpanded] = useState<Set<string>>(new Set()),
    [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]),
    [run, setRun] = useState<Run | null>(null),
    [events, setEvents] = useState<Event[]>([]),
    [cursor, setCursor] = useState(0);
  const [model, setModel] = useState("normal"),
    [effort, setEffort] = useState("off"),
    [text, setText] = useState(""),
    [search, setSearch] = useState<Search | null>(null),
    [searchQuery, setSearchQuery] = useState<string | null>(null);
  const [panel, setPanel] = useState<string | null>(null),
    [menu, setMenu] = useState<string | null>(null),
    [mobile, setMobile] = useState(false),
    [editingFolder, setEditingFolder] = useState<Folder | null>(null);
  const [rowMenu, setRowMenu] = useState<
    { kind: "folder"; value: Folder; anchor: HTMLElement } |
    { kind: "conversation"; value: Session; anchor: HTMLElement } | null>(null);
  const [managedSession, setManagedSession] = useState<Session | null>(null);
  const [managedProject, setManagedProject] = useState<string | null>(null);
  const [managementSaving, setManagementSaving] = useState(false);
  const [managementFailure, setManagementFailure] = useState<ManagementFailure | null>(null);
  const managementEpoch = useRef(0);
  const managementPending = useRef<number | null>(null);
  const [managementDelete, setManagementDelete] = useState(false);
  const [startingConversation, setStartingConversation] = useState(false);
  const reading = useReadingPosition(`${folder ?? ""}/${session ?? "new"}/${startingConversation}`, !folder || !!session || startingConversation);
  const managementInvoker = useRef<HTMLElement | null>(null);
  const [theme, setTheme] = useState("dark"),
    [reduced, setReduced] = useState(false),
    [volume, setVolume] = useState(
      Number(localStorage.getItem("hermes-ui:interface-volume") ?? 12),
    );
  const [busy, setBusy] = useState(false),
    [recording, setRecording] = useState(false),
    [voice, setVoice] = useState<{
      blob: Blob;
      waveform: number[];
      duration: number;
      url: string;
    } | null>(null),
    [recordSeconds, setRecordSeconds] = useState(0);
  const [fileNames, setFileNames] = useState<string[]>([]),
    [selectedFile, setSelectedFile] = useState<{
      path: string;
      text: string;
      sha256: string;
    } | null>(null);
  const [historyAttachments, setHistoryAttachments] = useState<
    Record<string, Attachment[]>
  >({});
  const [draftReady, setDraftReady] = useState(false);
  const [draftRetry, setDraftRetry] = useState(0);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [notchWidth, setNotchWidth] = useState(210);
  const [dismissedFailure, setDismissedFailure] = useState<string | null>(null);
  const notchContext = useRef<HTMLDivElement>(null);
  const notchLabel = useRef<HTMLElement>(null);
  const [recordLevels, setRecordLevels] = useState<number[]>([]);
  const [formValue, setFormValue] = useState("");
  const folderImport = useFolderImport(folder, panel === "Import folder", (files) => {
    setFileNames(files);
    setPanel("Files");
  });
  const [actionRows, setActionRows] = useState<Action[]>([]);
  const [editingText, setEditingText] = useState("");
  const [actionPrompt, setActionPrompt] = useState("");
  const [taskKind, setTaskKind] = useState("python");
  const sessionCreation = useRef<Promise<string> | null>(null);
  const sending = useRef(false),
    audio = useRef<ReturnType<typeof installInterfaceAudio> | null>(null),
    recorder = useRef(new Recorder()),
    uploadController = useRef<AbortController | null>(null),
    input = useRef<HTMLTextAreaElement>(null),
    fileInput = useRef<HTMLInputElement>(null),
    currentSession = useRef(session),
    currentFolder = useRef(folder),
    nextCursor = useRef(0);
  const recordingSession = useRef(new RecordingSession(recorder.current));
  currentSession.current = session;
  currentFolder.current = folder;
  const active = !!run && !terminal(run.state);
  const selectedModel = models.find((m) => m.id === model);
  const selectedReadiness = readiness?.models?.[model];
  const modelReady =
    readiness?.state === "ready" && selectedReadiness?.available !== false;
  const report = useCallback(
    (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
    [],
  );
  const draftAttachments = useDraftAttachments(session, connected);
  const attachments = draftAttachments.items;
  // Scoped versions own unsent edits; React text is the current view. This also
  // preserves a newer follow-up while an earlier submit acknowledgement arrives.
  const promptDrafts = useRef(
    new Map<string, { text: string; revision: number }>(),
  );
  const promptWrites = useRef(new Map<string, Promise<boolean>>());
  const draftTransfer = useRef<{
    id: string;
    from: DraftSelection;
    to: DraftSelection;
  } | null>(null);
  const mounted = useRef(true);
  const scopeKey = (scope: string | null) => scope ?? "new";
  function editText(
    next: string | ((previous: string) => string),
    owner = currentSession.current,
  ) {
    if (!mounted.current || currentSession.current !== owner) return;
    const key = scopeKey(owner),
      before = promptDrafts.current.get(key) ?? { text, revision: 0 };
    const value = typeof next === "function" ? next(before.text) : next;
    promptDrafts.current.set(key, {
      text: value,
      revision: before.revision + 1,
    });
    setText(value);
  }
  function persistPrompt(
    owner: string | null,
    expected: { text: string; revision: number },
    replacement = expected.text,
  ) {
    const key = scopeKey(owner);
    const perform = async () => {
      const latest = promptDrafts.current.get(key);
      if (!samePrompt(latest, expected)) return false;
      if (owner)
        await rpc("draft.write", {
          session_id: owner,
          text: replacement,
          mode: "chat",
        });
      else localStorage.setItem("hermes:new-draft", replacement);
      return true;
    };
    const previous = promptWrites.current.get(key);
    const pending = previous ? previous.then(perform, perform) : perform();
    promptWrites.current.set(key, pending);
    return pending;
  }
  function addAttachment(item: Attachment, token: AttachmentToken) {
    const result = draftAttachments.add(item, token);
    if (!result)
      throw Error(
        "The attachment draft changed while the upload finished. Attach the file again in the intended conversation.",
      );
    if (result.background && mounted.current)
      setError(
        "Attachment saved to the previous conversation's draft. Return there to review it.",
      );
    return result;
  }
  const permissions = usePermissions(session, ensureSession, report);
  useEffect(() => {
    const reason = recordingSession.current.reconcile(
      session,
      permissions.policy?.capabilities.microphone,
    );
    if (reason) {
      setRecording(false);
      setError(
        reason === "permission"
          ? "Recording stopped because microphone permission was revoked."
          : "Recording cancelled when the conversation changed.",
      );
    }
  }, [session, permissions.policy?.capabilities.microphone]);
  const refreshReadiness = useCallback(async () => {
    const next = await rpc<Readiness>("readiness.read");
    setReadiness(next);
    return next;
  }, []);
  const refresh = useCallback(async () => {
    const [f, s, m, c] = await Promise.all([
      rpc<Folder[]>("workspace.list"),
      rpc<Session[]>("session.list"),
      rpc<Model[]>("models.list"),
      rpc<Caps>("capabilities.read"),
    ]);
    setFolders(f);
    setSessions(s);
    setModels(m);
    setCaps(c);
    if (c.text_readiness) setReadiness(c.text_readiness);
    return { folders: f, sessions: s };
  }, []);
  const load = useCallback(async (id: string) => {
    const snap = await rpc<Snapshot>("chat.snapshot", { session_id: id });
    if (currentSession.current !== id) return;
    setMessages(snap.messages);
    setHistoryAttachments(snap.attachments ?? {});
    setRun(snap.runs.at(-1) ?? null);
    setEvents(snap.activity ?? []);
    const searched = snap.activity?.filter((e) => e.type === "search").at(-1);
    setSearch(
      searched
        ? {
            provider: String(searched.provider),
            query: String(searched.query),
            sources: searched.sources as Search["sources"],
          }
        : null,
    );
    setCursor(snap.after_seq);
    nextCursor.current = snap.after_seq;
  }, []);
  useEffect(() => {
    bootstrap()
      .then(async () => {
        await refresh();
        const old = await rpc<{
          theme?: string;
          motion?: string;
          session_id?: string | null;
          project_id?: string | null;
          arm?: string;
        } | null>("view.read");
        try { setStartingConversation(restoreComposingIntent(localStorage, old)); }
        catch (error) { report(error); }
        if (old) {
          setTheme(old.theme ?? "dark");
          setReduced(old.motion === "reduced");
          setFolder(old.project_id ?? null);
          setSession(old.session_id ?? null);
          setModel(old.arm ?? "normal");
        }
        audio.current = installInterfaceAudio();
        audio.current.setVolume(volume / 100);
        setConnected(true);
      })
      .catch(report);
    mounted.current = true;
    return () => {
      mounted.current = false;
      recordingSession.current.cancel();
      uploadController.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!connected) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await rpc<Readiness>("readiness.read");
        if (!stopped) setReadiness(next);
      } catch (error) {
        if (!stopped) report(error);
      } finally {
        if (!stopped) timer = setTimeout(poll, active ? 4000 : 10000);
      }
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [connected, active]);
  useEffect(() => {
    if (!active || !run) {
      setElapsed(0);
      return;
    }
    const tick = () =>
      setElapsed(Math.max(0, Math.floor(Date.now() / 1000 - run.created)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [active, run?.id]);
  useEffect(() => {
    if (!session) {
      setActionRows([]);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const update = async () => {
      try {
        const result = await permissions.refreshPolicy(session);
        if (alive) setActionRows(result.actions ?? result.pending ?? []);
      } catch (error) {
        if (alive) report(error);
      } finally {
        if (alive) timer = setTimeout(update, 3500);
      }
    };
    void update();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [session]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.dataset.motion = reduced ? "reduced" : "system";
    if (!connected) return;
    try { saveComposingIntent(localStorage, { project_id: folder, session_id: session }, startingConversation); }
    catch (error) { report(error); }
    rpc("view.write", {
      state: {
        project_id: folder,
        session_id: session,
        file_path: null,
        editor: null,
        files_open: false,
        arm: model,
        task_kind: "chat",
        theme,
        motion: reduced ? "reduced" : "system",
      },
    }).catch(report);
  }, [theme, reduced, connected, folder, session, model, startingConversation]);
  useEffect(() => {
    if (!connected) return;
    setDraftReady(false);
    let alive = true;
    const owner = session,
      key = scopeKey(owner);
    const restorePrompt = (fallback: string) => {
      if (!alive || currentSession.current !== owner) return;
      const draft = promptDrafts.current.get(key) ?? {
        text: fallback,
        revision: 0,
      };
      promptDrafts.current.set(key, draft);
      setText(draft.text);
      setDraftReady(true);
    };
    if (!session) {
      setMessages([]);
      setRun(null);
      setEvents([]);
      restorePrompt(localStorage.getItem("hermes:new-draft") ?? "");
    } else {
      load(session)
        .then(() =>
          rpc<{ text: string }>("draft.read", { session_id: session }),
        )
        .then((draft) => restorePrompt(draft.text))
        .catch(report);
    }
    return () => {
      alive = false;
      const draft = promptDrafts.current.get(key);
      if (draft) persistPrompt(owner, draft).catch(report);
    };
  }, [session, connected, draftRetry]);
  useEffect(() => {
    setSelectedFile(null);
    setEditingText("");
    setFileNames([]);
  }, [folder]);
  useEffect(() => {
    if (!connected || !draftReady) return;
    const draft = promptDrafts.current.get(scopeKey(session));
    if (!draft) return;
    const id = setTimeout(() => {
      persistPrompt(session, draft).catch(report);
    }, 400);
    return () => clearTimeout(id);
  }, [text, session, draftReady, connected]);
  useEffect(() => {
    const el = input.current;
    if (el) {
      el.style.height = "0px";
      el.style.height = Math.min(160, Math.max(24, el.scrollHeight)) + "px";
    }
  }, [text]);
  useEffect(() => {
    if (!run || terminal(run.state)) return;
    const id = run.id,
      owner = session,
      controller = new AbortController();
    let alive = true;
    let attempts = 0;
    const consume = (event: Event) => {
      if (
        !alive ||
        currentSession.current !== owner ||
        event.run_id !== id ||
        event.seq <= nextCursor.current
      )
        return;
      nextCursor.current = event.seq;
      if (event.type === "delta" && event.text)
        setMessages((old) => {
          const at = old.findIndex(
            (m) => m.role === "assistant" && m.job === id,
          );
          if (at < 0)
            return [...old, { role: "assistant", text: event.text!, job: id }];
          return old.map((m, i) =>
            i === at ? { ...m, text: m.text + event.text } : m,
          );
        });
      else {
        setEvents((old) => [...old, event]);
        if (event.type === "search")
          setSearch({
            provider: String(event.provider),
            query: String(event.query),
            sources: event.sources as Search["sources"],
          });
        if (event.type === "state") {
          setRun((old) =>
            old?.id === id
              ? { ...old, state: event.state!, error: event.error ?? null }
              : old,
          );
          if (event.state && terminal(event.state)) {
            refresh().catch(report);
          }
        }
      }
    };
    const follow = async () => {
      while (alive) {
        try {
          await stream(id, nextCursor.current, consume, controller.signal);
          if (!alive) return;
          const latest = await rpc<Run>("chat.read", { run_id: id });
          setRun((old) => (old?.id === id ? latest : old));
          if (terminal(latest.state)) return;
        } catch (e) {
          if (!alive) return;
          if (++attempts > 3) {
            report(
              Error(
                "Stream disconnected. Reload to reconnect; the request has not been resubmitted.",
              ),
            );
            return;
          }
        }
        await new Promise((r) =>
          setTimeout(r, Math.min(3000, 500 * 2 ** attempts)),
        );
      }
    };
    follow();
    return () => {
      alive = false;
      controller.abort();
    };
  }, [run?.id, session, cursor]);
  useEffect(() => { setRowMenu(null); setMenu(null); }, [session, folder]);
  useEffect(() => {
    if (!recording) return;
    const tick = setInterval(
      () =>
        setRecordSeconds(
          Math.floor((performance.now() - recorder.current.started) / 1000),
        ),
      1000,
    );
    return () => clearInterval(tick);
  }, [recording]);
  useEffect(() => {
    const pause = () => {
      if (document.hidden) {
        document.querySelectorAll("audio").forEach((a) => a.pause());
        if (recordingSession.current.cancel()) {
          setRecording(false);
          setError("Recording cancelled when the app became hidden.");
        }
      }
      document.documentElement.dataset.visibility = document.hidden
        ? "hidden"
        : "visible";
    };
    document.addEventListener("visibilitychange", pause);
    return () => document.removeEventListener("visibilitychange", pause);
  }, []);
  useEffect(
    () => () => {
      if (voice) URL.revokeObjectURL(voice.url);
    },
    [voice],
  );
  async function newConversation() {
    setStartingConversation(true);
    draftAttachments.resetNew();
    const old = promptDrafts.current.get("new");
    promptDrafts.current.set("new", {
      text: "",
      revision: (old?.revision ?? 0) + 1,
    });
    localStorage.removeItem("hermes:new-draft");
    setSession(null);
    setMessages([]);
    setRun(null);
    setSearch(null);
    setMobile(false);
    setText("");
    input.current?.focus({ preventScroll: true });
  }
  async function ensureSession(): Promise<string> {
    if (currentSession.current) return currentSession.current;
    if (!sessionCreation.current) {
      const origin = draftAttachments.capture();
      sessionCreation.current = (async () => {
        const created = await rpc<Session>("session.create", {
          project_id: folder,
          arm: model,
        });
        if (!draftAttachments.owns(origin))
          throw Error(
            "Conversation changed during creation. Return to the intended draft before continuing.",
          );
        const copied = promptDrafts.current.get("new") ?? { text, revision: 0 };
        await rpc("draft.write", {
          session_id: created.id,
          text: copied.text,
          mode: "chat",
        });
        if (!draftAttachments.owns(origin))
          throw Error(
            "Conversation changed during creation. The new empty conversation was retained.",
          );
        const transfer = draftAttachments.migrateNew(created.id);
        draftTransfer.current = { id: created.id, ...transfer };
        // Preserve edits made while the create/write requests were in flight.
        const latest = promptDrafts.current.get("new") ?? copied;
        promptDrafts.current.set(created.id, latest);
        promptDrafts.current.set("new", {
          text: "",
          revision: latest.revision + 1,
        });
        localStorage.removeItem("hermes:new-draft");
        currentSession.current = created.id;
        setSession(created.id);
        return created.id;
      })().finally(() => {
        sessionCreation.current = null;
      });
    }
    return sessionCreation.current;
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      sending.current ||
      busy ||
      active ||
      !draftReady ||
      !draftAttachments.ready ||
      draftAttachments.issues.length ||
      !text.trim() ||
      !selectedModel
    )
      return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      const selection = draftAttachments.capture();
      const prompt = text,
        selected = model,
        reasoning = effort,
        query = searchQuery;
      const promptVersion = promptDrafts.current.get(
        scopeKey(selection.scope),
      ) ?? { text: prompt, revision: 0 };
      await draftAttachments.verify(selection.selection.ids);
      const ready = await refreshReadiness();
      if (
        ready.state !== "ready" ||
        ready.models?.[selected]?.available === false
      )
        throw Error(
          ready.models?.[selected]?.detail ||
            ready.detail ||
            "Local model connection needs repair. Your draft is preserved.",
        );
      if (selection.scope === null && !draftAttachments.owns(selection))
        throw Error(
          "Conversation changed before Send. Your draft is preserved; send again in the intended conversation.",
        );
      const id = selection.scope ?? (await ensureSession());
      let submittedSelection = selection;
      if (selection.scope === null) {
        const transfer = draftTransfer.current;
        submittedSelection = {
          ...selection,
          scope: id,
          selection:
            transfer?.id === id &&
            sameSelection(transfer.from, selection.selection)
              ? transfer.to
              : { ...selection.selection, revision: "" },
        };
      }
      const pendingKey = "hermes:pending:" + id;
      let pending: Record<string, unknown> | null = null;
      try {
        pending = JSON.parse(localStorage.getItem(pendingKey) || "null");
      } catch {
        /* An invalid local request is never reused. */
      }
      if (
        pending &&
        (pending.prompt !== prompt ||
          pending.model_id !== selected ||
          pending.reasoning !== reasoning ||
          JSON.stringify(pending.attachments) !==
            JSON.stringify(selection.selection.ids) ||
          pending.search_query !== query)
      )
        pending = null;
      const fields = pending ?? {
        session_id: id,
        request_id: crypto.randomUUID().replaceAll("-", ""),
        model_id: selected,
        prompt,
        reasoning,
        attachments: selection.selection.ids,
        search_query: query,
      };
      localStorage.setItem(pendingKey, JSON.stringify(fields));
      await rpc<Run>("chat.submit", fields);
      localStorage.removeItem(pendingKey);
      const latest = promptDrafts.current.get(id);
      if (latest && samePrompt(latest, promptVersion)) {
        const clearedSelection =
          draftAttachments.clearAccepted(submittedSelection);
        if (clearedSelection) {
          const clearedPrompt = await persistPrompt(id, latest, "");
          const after = promptDrafts.current.get(id);
          if (
            clearedPrompt &&
            samePrompt(after, latest) &&
            sameSelection(readSelection(localStorage, id), clearedSelection)
          ) {
            promptDrafts.current.set(id, {
              text: "",
              revision: latest.revision + 1,
            });
            if (currentSession.current === id) {
              setText("");
              setSearch(null);
              setSearchQuery(null);
            }
          } else if (after) await persistPrompt(id, after);
        }
      }
      await load(id);
      await refresh();
    } catch (error) {
      if (mounted.current) report(error);
    } finally {
      sending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function cancelResponse() {
    const requested = run;
    if (!requested || terminal(requested.state)) return;
    try {
      const receipt = await rpc<Run>("chat.cancel", { run_id: requested.id });
      setRun((current) => applyCancellationResult(current, requested, receipt));
    } catch (error) {
      report(error);
    }
  }
  async function addFiles(files: FileList | null) {
    if (!files || uploadController.current || busy) return;
    const controller = new AbortController();
    setMenu(null);
    setBusy(true);
    setError("");
    uploadController.current = controller;
    try {
      let token = draftAttachments.capture();
      if (token.selection.ids.length + files.length > 8)
        throw Error("At most eight attachments per turn.");
      for (const file of Array.from(files)) {
        let item = await upload(
          /\.(py|cpp|c|h|md|json|txt)$/i.test(file.name)
            ? new Blob([file], { type: "text/plain" })
            : file,
          file.name,
          controller.signal,
        );
        if (item.mime.startsWith("audio/")) {
          if (!caps?.transcription)
            throw Error(
              "Audio stored, but local transcription is unavailable. Attach it again when transcription is available.",
            );
          item = await rpc<Attachment>("attachment.transcribe", {
            id: item.id,
          });
        }
        const added = addAttachment(item, token);
        token = added.token;
        if (!added.background && item.metadata.transcript)
          editText(
            (previous) =>
              (previous ? previous + "\n" : "") + item.metadata.transcript,
            token.scope,
          );
      }
    } catch (error) {
      if (mounted.current) report(error);
    } finally {
      if (uploadController.current === controller)
        uploadController.current = null;
      if (mounted.current) setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  async function startRecording() {
    setMenu(null);
    setError("");
    let owner: string | null = null,
      authorized = false;
    try {
      owner = await ensureSession();
      const id = owner;
      await recordingSession.current.start(
        id,
        async () => {
          await rpc("recording.authorize", { session_id: id });
          authorized = true;
        },
        () =>
          mounted.current && !document.hidden && currentSession.current === id,
        [
          () => {
            recordingSession.current.cancel();
            setRecording(false);
            setError(
              "Recording stopped at the two-minute limit; microphone released.",
            );
          },
          setRecordLevels,
          () => {
            recordingSession.current.cancel();
            setRecording(false);
            setError(
              "Microphone disconnected or recording failed; capture released. Reconnect the device and start again.",
            );
          },
        ],
      );
      setRecording(true);
      setRecordSeconds(0);
      setRecordLevels([]);
    } catch (error) {
      if (
        !mounted.current ||
        (error instanceof DOMException && error.name === "AbortError")
      )
        return;
      if (!authorized && owner && currentSession.current === owner) {
        setPanel("Settings");
        if (
          error instanceof Error &&
          error.message === "permission_required_microphone"
        ) {
          report(
            new Error(
              "Microphone is off for this conversation. Enable it in Settings before recording.",
              { cause: error },
            ),
          );
          return;
        }
      }
      report(error);
    }
  }
  async function stopRecording() {
    try {
      const { blob, measured } = await recordingSession.current.stop(
        async (blob) => {
          setRecording(false);
          return { blob, measured: await waveform(blob) };
        },
      );
      setVoice({ blob, ...measured, url: URL.createObjectURL(blob) });
    } catch (error) {
      if (
        !mounted.current ||
        (error instanceof DOMException && error.name === "AbortError")
      )
        return;
      setRecording(false);
      report(error);
    }
  }
  async function useVoice() {
    if (!voice || busy || uploadController.current) return;
    const captured = voice,
      controller = new AbortController();
    uploadController.current = controller;
    setBusy(true);
    try {
      const token = draftAttachments.capture();
      if (token.selection.ids.length >= 8)
        throw Error("At most eight attachments per turn.");
      const item = await upload(
        captured.blob,
        "Voice note.webm",
        controller.signal,
      );
      const transcribed = await rpc<Attachment>("attachment.transcribe", {
        id: item.id,
      });
      const added = addAttachment(transcribed, token);
      if (!added.background && transcribed.metadata.transcript)
        editText(
          (previous) =>
            (previous ? previous + "\n" : "") + transcribed.metadata.transcript,
          token.scope,
        );
      if (mounted.current)
        setVoice((current) => (current === captured ? null : current));
    } catch (error) {
      if (mounted.current) report(error);
    } finally {
      if (uploadController.current === controller)
        uploadController.current = null;
      if (mounted.current) setBusy(false);
    }
  }
  async function newFolder() {
    setFormValue("");
    setPanel("New folder");
  }
  async function createFolder(event: FormEvent) {
    event.preventDefault();
    if (!formValue.trim()) return;
    try {
      const f = await rpc<Folder>("workspace.create", {
        label: formValue.trim(),
      });
      await rpc("folder.update", {
        project_id: f.id,
        label: f.label,
        parent: folder,
        color: "blue",
      });
      if (folder) setExpanded((old) => new Set([...old, folder]));
      setFolder(f.id);
      setPanel(null);
      await refresh();
    } catch (error) {
      report(error);
    }
  }
  async function importFolder() {
    setMenu(null);
    folderImport.reset();
    setPanel("Import folder");
  }
  async function showFiles() {
    setPanel("Files");
    setMenu(null);
    if (!folder) {
      setFileNames([]);
      return;
    }
    try {
      const result = await rpc<{ files: string[] }>("workspace.files", {
        project_id: folder,
      });
      setFileNames(result.files);
    } catch (e) {
      report(e);
    }
  }
  async function readFile(path: string) {
    await requestAction({ type: "workspace.read", path });
  }
  async function attachLibrary() {
    if (!selectedFile || busy || uploadController.current) return;
    const controller = new AbortController();
    uploadController.current = controller;
    setBusy(true);
    try {
      const token = draftAttachments.capture();
      if (token.selection.ids.length >= 8)
        throw Error("At most eight attachments per turn.");
      const item = await upload(
        new Blob([selectedFile.text], { type: "text/plain" }),
        selectedFile.path.split("/").at(-1)!,
        controller.signal,
      );
      const added = addAttachment(item, token);
      if (!added.background) setPanel(null);
    } catch (error) {
      if (mounted.current) report(error);
    } finally {
      if (uploadController.current === controller)
        uploadController.current = null;
      if (mounted.current) setBusy(false);
    }
  }
  async function searchWeb() {
    setMenu(null);
    setFormValue(searchQuery ?? "");
    setPanel("Search Wikipedia");
  }
  async function requestAction(action: Record<string, unknown>) {
    try {
      const id = await ensureSession();
      const row = await rpc<Action>("permissions.request", {
        session_id: id,
        run_id: run?.id ?? null,
        request_id: crypto.randomUUID().replaceAll("-", ""),
        action,
      });
      if (currentSession.current !== id) return row;
      setActionRows((old) => [
        ...old.filter((item) => item.id !== row.id),
        row,
      ]);
      await permissions.refreshPolicy(id);
      if (row.state === "pending") setPanel(null);
      if (row.state === "allowed") return await executeAction(row, id);
      return row;
    } catch (error) {
      report(error);
      return null;
    }
  }
  async function executeAction(action: Action, owner = session) {
    if (!owner) return;
    try {
      const row = await rpc<Action>("actions.execute", {
        session_id: owner,
        action_id: action.id,
      });
      if (currentSession.current !== owner) return row;
      setActionRows((old) => [
        ...old.filter((item) => item.id !== row.id),
        row,
      ]);
      await permissions.refreshPolicy(owner);
      if (row.state === "completed" && action.type === "workspace.read") {
        const file = row.result as {
          path: string;
          text: string;
          sha256: string;
        };
        setSelectedFile(file);
        setEditingText(file.text);
        setPanel("Files");
      }
      if (row.state === "completed" && action.type === "workspace.write") {
        const result = row.result as { path: string; sha256: string };
        setSelectedFile({
          path: result.path,
          text: String(action.action.text),
          sha256: result.sha256,
        });
        await showFiles();
      }
      if (row.state === "completed" && action.type === "search.wikipedia") {
        const result = row.result as Search;
        setSearch(result);
        setSearchQuery(null);
        if (
          result.attachment &&
          !draftAttachments.addForScope(result.attachment, owner)
        )
          throw Error(
            "Search finished in a different conversation. Open its search result there to attach it.",
          );
      }
      return row;
    } catch (error) {
      report(error);
      return null;
    }
  }
  async function decideAction(action: Action, decision: string) {
    if (!session) return;
    try {
      const row = await rpc<Action>("permissions.decide", {
        session_id: session,
        ticket_id: action.ticket_id || action.id,
        decision,
      });
      if (currentSession.current !== session) return;
      setActionRows((old) => [
        ...old.filter((item) => item.id !== row.id),
        row,
      ]);
      await permissions.refreshPolicy();
      if (row.state === "allowed") await executeAction(row);
    } catch (error) {
      report(error);
    }
  }
  async function deleteRecord(kind: string, id: string) {
    await rpc("content.delete", { kind, id });
    if (id === currentSession.current || (kind === "project" && id === currentFolder.current)) {
      currentSession.current = null;
      setSession(null);
      if (kind === "project") setFolder(null);
    }
    const viewedSession = currentSession.current, viewedFolder = currentFolder.current;
    const current = await refresh();
    if (viewedSession && currentSession.current === viewedSession && !current.sessions.some((s) => s.id === viewedSession)) {
      currentSession.current = null;
      setSession(null);
    }
    if (viewedFolder && currentFolder.current === viewedFolder && !current.folders.some((f) => f.id === viewedFolder))
      setFolder(null);
  }
  const filteredFolders = folderTree(folders, query);
  function folderRow(row: Folder, depth = 0): React.ReactNode {
    const open = !!query.trim() || expanded.has(row.id),
      children = filteredFolders.children.get(row.id) ?? [];
    return (
      <div
        key={row.id}
        className="folder-branch"
      >
        <div
          className={"folder-row " + (folder === row.id ? (session || startingConversation ? "context" : "selected") : "")}
          style={
            {
              "--depth": depth,
              "--folder-color": `var(--${row.color})`,
            } as CSSProperties
          }
        >
          <button
            className="branch-toggle"
            disabled={!children.length || !!query.trim()}
            aria-hidden={!children.length}
            aria-expanded={children.length ? open : undefined}
            aria-controls={children.length && open ? "folder-children-" + row.id : undefined}
            title={
              query.trim()
                ? "Matching branches stay expanded while filtering."
                : undefined
            }
            aria-label={
              query.trim()
                ? "Filtered branch: " + row.label
                : (open ? "Collapse " : "Expand ") + row.label
            }
            onClick={() =>
              setExpanded((s) => {
                const n = new Set(s);
                n.has(row.id) ? n.delete(row.id) : n.add(row.id);
                return n;
              })
            }
            onKeyDown={(e) => {
              if (e.key === "ArrowRight")
                setExpanded((s) => new Set([...s, row.id]));
              if (e.key === "ArrowLeft")
                setExpanded((s) => {
                  const n = new Set(s);
                  n.delete(row.id);
                  return n;
                });
            }}
          >
            {children.length ? (open ? "⌄" : "›") : ""}
          </button>
          <button
            className="folder-select"
            aria-current={folder === row.id ? (session || startingConversation ? "location" : "page") : undefined}
            title={row.label}
            onClick={() => {
              setStartingConversation(false);
              setFolder(row.id);
              setSession(null);
              setMobile(false);
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3Z" />
            </svg>
            <span>{row.label}</span>
            <small>{sessions.filter((s) => s.project === row.id).length}</small>
          </button>
          <button
            className="folder-options"
            id={"folder-options-" + row.id}
            aria-label={"Actions for " + row.label}
            title={"Actions for " + row.label}
            aria-haspopup="menu"
            aria-expanded={rowMenu?.kind === "folder" && rowMenu.value.id === row.id}
            aria-controls={rowMenu?.kind === "folder" && rowMenu.value.id === row.id ? "row-actions" : undefined}
            onClick={(event) => {
              setMenu(null);
              setRowMenu(rowMenu?.kind === "folder" && rowMenu.value.id === row.id ? null : { kind: "folder", value: row, anchor: event.currentTarget });
            }}
          >
            <UIIcon name="more" />
          </button>
        </div>
        {open && (
          <div id={"folder-children-" + row.id}>{children.map((f) => folderRow(f, depth + 1))}</div>
        )}
      </div>
    );
  }
  const listed = sessions.filter(
    (s) =>
      (query || folder === null ? true : s.project === folder) &&
      s.title.toLowerCase().includes(query.toLowerCase()),
  );
  const activity = activityStatus(
    run,
    events,
    actionRows,
    models.find((item) => item.id === run?.model)?.label ??
      selectedModel?.label ??
      "Local model",
    elapsed,
  );
  const label = activity.runLabel;
  const showActivity =
    activity.visible &&
    !(activity.state === "failed" && dismissedFailure === run?.id);
  useLayoutEffect(() => {
    if (!showActivity) return;
    const context = notchContext.current?.scrollWidth ?? 0;
    const status = (notchLabel.current?.scrollWidth ?? 0) + 19;
    setNotchWidth(Math.max(210, Math.min(340, Math.max(context, status) + 47)));
  }, [showActivity, activity.label, activity.context]);
  const tasks = events
    .filter((e) => e.type === "file" || e.type === "search")
    .map((e) => ({
      id: String(e.seq),
      label:
        e.type === "file"
          ? "Included " + e.name + " · " + e.lines + " lines"
          : "Retrieved public sources",
      done: true,
    }));
  return (
    <ReducedMotionContext.Provider value={reduced}>
      <MotionConfig reducedMotion={reduced ? "always" : "user"}>
        <VoiceNoteGroup>
          <div id="app" className="shell">
            <a className="skip-link" href="#prompt">
              Skip to message
            </a>
            <aside
              className={"sidebar " + (mobile ? "mobile-open" : "")}
              aria-label="Projects and conversations"
            >
              <div className="brand">
                <img src="/brand/hermes.png" alt="" />
                Hermes
                <button
                  className="mobile-close icon-button"
                  aria-label="Close navigation"
                  onClick={() => setMobile(false)}
                >
                  ×
                </button>
              </div>
              <button
                className="new-conversation"
                id="new-session"
                onClick={newConversation}
              >
                New conversation <span>＋</span>
              </button>
              <label className="rail-search">
                <UIIcon name="search" />
                <input
                  aria-label="Search folders and conversations"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search"
                />
              </label>
              <div className="rail-heading">
                <h2>Projects</h2>
                <button
                  className="icon-button"
                  aria-label="New folder"
                  onClick={newFolder}
                >
                  ＋
                </button>
              </div>
              <nav
                className="folder-tree"
                aria-label="Project folders"
              >
                <button
                  className={"all-conversations " + (!folder && !session && !startingConversation ? "selected" : "")}
                  onClick={() => {
                    setStartingConversation(false);
                    setFolder(null);
                    setSession(null);
                  }}
                >
                  All conversations
                </button>
                {filteredFolders.roots.map((f) => folderRow(f))}
              </nav>
              <div className="rail-heading">
                <h2>Conversations</h2>
                <span>{listed.length || ""}</span>
              </div>
              <nav className="session-list" aria-label="Conversations">
                {listed.map((s) => (
                  <div
                    key={s.id}
                    className={
                      "session-row " + (session === s.id ? "selected" : "")
                    }
                  >
                    <button
                      title={s.title}
                      aria-current={session === s.id ? "page" : undefined}
                      onClick={() => {
                        setStartingConversation(false);
                        setSession(s.id);
                        setFolder(s.project);
                        setModel(s.arm);
                        setMobile(false);
                      }}
                    >
                      {s.title}
                    </button>
                    <button
                      className="session-options"
                      id={"conversation-options-" + s.id}
                      aria-label={"Actions for " + s.title}
                      title={"Actions for " + s.title}
                      aria-haspopup="menu"
                      aria-expanded={rowMenu?.kind === "conversation" && rowMenu.value.id === s.id}
                      aria-controls={rowMenu?.kind === "conversation" && rowMenu.value.id === s.id ? "row-actions" : undefined}
                      onClick={(event) => {
                        setMenu(null);
                        setRowMenu(rowMenu?.kind === "conversation" && rowMenu.value.id === s.id ? null : { kind: "conversation", value: s, anchor: event.currentTarget });
                      }}
                    >
                      <UIIcon name="more" />
                    </button>
                  </div>
                ))}
                {!listed.length && (
                  <p className="rail-empty">
                    {query
                      ? "No matches"
                      : "Your conversations will appear here."}
                  </p>
                )}
              </nav>
              <footer className="rail-footer">
                <span className="sr-only">Interface preferences</span>
                <button
                  id="sound-toggle"
                  className="icon-button"
                  aria-label="Mute interface sounds"
                  aria-pressed="true"
                >
                  <UIIcon name="sound" />
                </button>
              </footer>
            </aside>
            <div className="buddy-dock">
              <Buddy
                dark={theme === "dark"}
                toggle={() =>
                  setTheme((value) => (value === "dark" ? "light" : "dark"))
                }
              />
            </div>
            <section className="workspace-body">
              <header className="toolbar">
                <button
                  className="mobile-toggle icon-button"
                  aria-label="Open navigation"
                  onClick={() => setMobile(true)}
                >
                  ☰
                </button>
                <nav className="conversation-title" aria-label="Current location">
                  {folder && <><button className="workspace-location" title={folders.find(item => item.id === folder)?.label}
                    onClick={() => { setStartingConversation(false); setSession(null); }}>{folders.find(item => item.id === folder)?.label}</button><span aria-hidden="true">/</span></>}
                  <span aria-current="page" title={sessions.find(item => item.id === session)?.title}>
                    {sessions.find(item => item.id === session)?.title ?? (!startingConversation && folder ? "Overview" : "New conversation")}
                  </span>
                </nav>
                <div className="toolbar-actions">
                  <button
                    id="files-toggle"
                    aria-expanded={panel === "Files"}
                    onClick={() =>
                      panel === "Files" ? setPanel(null) : showFiles()
                    }
                  >
                    Files
                  </button>
                  <button
                    id="diagnostics"
                    aria-expanded={panel === "Details"}
                    onClick={() =>
                      setPanel(panel === "Details" ? null : "Details")
                    }
                  >
                    Details
                  </button>
                  <button
                    id="settings-toggle"
                    aria-expanded={panel === "Settings"}
                    onClick={() =>
                      setPanel(panel === "Settings" ? null : "Settings")
                    }
                  >
                    Settings
                  </button>
                </div>
              </header>
              {showActivity && (
                <div
                  className="activity-notch"
                  data-state={activity.state}
                  role="status"
                  style={{ width: notchWidth }}
                >
                  <div className="notch-meta" ref={notchContext}>
                    {activity.context}
                  </div>
                  <div className="notch-working">
                    <WorkingIndicator state={activity.state} />
                    <strong ref={notchLabel}>{activity.label}</strong>
                  </div>
                  {activity.cancellable ? (
                    <button
                      aria-label="Cancel current response"
                      onClick={cancelResponse}
                    >
                      ×
                    </button>
                  ) : activity.state === "failed" ? (
                    <button
                      aria-label="Dismiss response status"
                      onClick={() => setDismissedFailure(run?.id ?? null)}
                    >
                      ×
                    </button>
                  ) : null}
                </div>
              )}
              <main ref={reading.container} className="conversation" aria-label="Conversation">
                <div className="message-column">
                  {!messages.length && folder && !session && !startingConversation && (
                    <div className="project-dashboard">
                      <h1>{folders.find((f) => f.id === folder)?.label}</h1>
                      <p>
                        {sessions.filter((s) => s.project === folder).length}{" "}
                        {sessions.filter((s) => s.project === folder).length === 1 ? "conversation" : "conversations"} ·{" "}
                        {folders.filter((f) => f.parent === folder).length}{" "}
                        {folders.filter((f) => f.parent === folder).length === 1 ? "folder" : "folders"}
                      </p>
                      <div className="dashboard-actions">
                        <button onClick={newConversation}>
                          New conversation ↗
                        </button>
                        <button onClick={importFolder}>Import folder</button>
                        <button
                          onClick={(event) => {
                            managementEpoch.current++;
                            setManagementSaving(false);
                            setManagementFailure(null);
                            managementInvoker.current = event.currentTarget;
                            setManagementDelete(false);
                            setEditingFolder(
                              folders.find((f) => f.id === folder)!,
                            );
                            setPanel("Folder");
                          }}
                        >
                          Edit project
                        </button>
                      </div>
                      {folders
                        .filter((f) => f.parent === folder)
                        .map((f) => (
                          <button
                            className="dashboard-folder"
                            key={f.id}
                            onClick={() => { setStartingConversation(false); setFolder(f.id); }}
                          >
                            <span style={{ color: `var(--${f.color})` }}>
                              ▱
                            </span>
                            {f.label}
                            <span>↗</span>
                          </button>
                        ))}
                      {sessions
                        .filter((s) => s.project === folder)
                        .slice(0, 6)
                        .map((s) => (
                          <button
                            className="dashboard-conversation"
                            key={s.id}
                            onClick={() => setSession(s.id)}
                          >
                            {s.title}
                            <span>→</span>
                          </button>
                        ))}
                    </div>
                  )}
                  {!messages.length && (!folder || !!session || startingConversation) && (
                    <div className="empty-state">
                      <h1>New conversation</h1>
                    </div>
                  )}
                  {messages.map((m, i) => (
                    <article
                      className={"message " + m.role}
                      key={m.job + "-" + m.role + "-" + i}
                    >
                      {m.role === "assistant" && run && m.job === run.id && (
                        <AiStatus
                          state={
                            active
                              ? "thinking"
                              : run.state === "completed"
                                ? "done"
                                : "error"
                          }
                          label={label}
                          timer={false}
                          shimmer={active}
                        />
                      )}
                      <div className="message-text">
                        <MessageMarkdown
                          text={m.text}
                          sources={
                            m.role === "assistant"
                              ? turnCitationSources(
                                  m.job ? historyAttachments[m.job] : undefined,
                                  events,
                                  m.job,
                                )
                              : []
                          }
                        />
                      </div>
                      {m.role === "user" &&
                        m.job &&
                        historyAttachments[m.job]?.map((a) => (
                          <div className="history-attachment" key={a.id}>
                            {a.mime.startsWith("audio/") ? (
                              <VoiceNote
                                src={audioURL(a.id)}
                                duration={a.metadata.duration}
                                waveform={a.metadata.waveform ?? []}
                                size="sm"
                              />
                            ) : (
                              <a
                                href={audioURL(a.id)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {a.name}
                              </a>
                            )}
                          </div>
                        ))}
                    </article>
                  ))}
                  {active &&
                    !messages.some(
                      (m) => m.job === run?.id && m.role === "assistant",
                    ) && (
                      <AiStatus state="thinking" label={label} timer={false} />
                    )}
                  {run?.error && (
                    <div className="run-error" role="alert">
                      <p>
                        {run.error === "protected_text_admission_not_installed"
                          ? "Local model connection needs repair. Your conversation is preserved."
                          : run.error}
                      </p>
                      {run.state === "failed" && (
                        <button
                          className="secondary-button"
                          disabled={busy || !modelReady}
                          onClick={async () => {
                            setBusy(true);
                            try {
                              const retried = await rpc<Run>("chat.retry", {
                                run_id: run.id,
                              });
                              if (currentSession.current === run.session)
                                setRun((current) =>
                                  applyRetryResult(current, run, retried),
                                );
                              await load(run.session);
                            } catch (error) {
                              report(error);
                            } finally {
                              setBusy(false);
                            }
                          }}
                        >
                          Retry this turn
                        </button>
                      )}
                    </div>
                  )}
                  <ApprovalCards
                    actions={actionRows}
                    decide={decideAction}
                    execute={executeAction}
                    requestHost={(ticket) =>
                      requestAction({
                        type: "host.apply",
                        review_ticket: ticket,
                      })
                    }
                  />
                  {(tasks.length > 0 || actionRows.length > 0) && (
                    <details className="run-tasks">
                      <summary>Activity</summary>
                      <TaskList
                        tasks={[
                          ...tasks,
                          ...actionRows
                            .filter((action) => action.type !== "guest.submit")
                            .map((action) => ({
                              id: action.id,
                              label: `${action.summary || action.type} · ${action.state.replaceAll("_", " ")}`,
                              done: action.state === "completed",
                            })),
                        ]}
                        size="md"
                      />
                    </details>
                  )}
                </div>
              </main>
              <div className="composer-area">
                {!reading.atEnd && <button type="button" className="jump-latest" onClick={reading.jump}>Jump to latest ↓</button>}
                {error && (
                  <div className="error-banner" role="alert">
                    <span>{error}</span>
                    <button
                      aria-label="Dismiss error"
                      onClick={() => setError("")}
                    >
                      ×
                    </button>
                  </div>
                )}
                {readiness && !modelReady && !active && (
                  <div className="readiness-banner" role="status">
                    <span>
                      <strong>
                        {readiness.state === "repair_required"
                          ? "Local model connection needs repair"
                          : "Local model connection is unavailable"}
                      </strong>
                      <small>
                        {selectedReadiness?.detail || readiness.detail} Your
                        draft is preserved.
                      </small>
                    </span>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => refreshReadiness().catch(report)}
                    >
                      Check connection
                    </button>
                  </div>
                )}
                {run?.state === "searching" && (
                  <WebSearch
                    sources={[]}
                    query={String(
                      events.filter((e) => e.type === "search_state").at(-1)
                        ?.query ?? "",
                    )}
                    status="searching"
                  />
                )}
                {search && (
                  <WebSearch
                    label={
                      search.provider + " · " + search.sources.length + " pages"
                    }
                    sources={search.sources.map((s) => ({
                      ...s,
                      snippet: s.text,
                    }))}
                    query={search.query}
                    status="done"
                    defaultOpen={false}
                  />
                )}
                {connected && !draftReady && (
                  <div className="readiness-banner" role="status">
                    <span>Restoring this conversation's draft…</span>
                    <button
                      type="button"
                      onClick={() => setDraftRetry((value) => value + 1)}
                    >
                      Retry draft lookup
                    </button>
                  </div>
                )}
                {draftAttachments.issues.length > 0 && (
                  <div className="attachment-issues" role="alert">
                    {draftAttachments.issues.map((issue) => (
                      <div key={issue.id ?? "invalid"}>
                        <span>{issue.message}</span>
                        <button
                          type="button"
                          onClick={() => draftAttachments.remove(issue.id)}
                        >
                          {issue.id
                            ? "Remove unavailable attachment"
                            : "Clear saved selection"}
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={draftAttachments.retry}>
                      Retry attachment lookup
                    </button>
                  </div>
                )}
                <form className="composer" id="composer" onSubmit={submit}>
                  {searchQuery && (
                    <div className="search-intent">
                      Search Wikipedia: {searchQuery}
                      <button
                        type="button"
                        aria-label="Remove search"
                        onClick={() => setSearchQuery(null)}
                      >
                        ×
                      </button>
                    </div>
                  )}
                  {attachments.length > 0 && (
                    <div className="attachments">
                      {attachments.map((a) => (
                        <div key={a.id} className="attachment">
                          {a.mime.startsWith("image/") ? (
                            <img src={audioURL(a.id)} alt={a.name} />
                          ) : a.mime.startsWith("audio/") ? (
                            <VoiceNote
                              src={audioURL(a.id)}
                              duration={a.metadata.duration}
                              waveform={a.metadata.waveform ?? []}
                              size="sm"
                            />
                          ) : (
                            <span>▤</span>
                          )}
                          <span>{a.name}</span>
                          <button
                            type="button"
                            aria-label={"Remove " + a.name}
                            onClick={() => draftAttachments.remove(a.id)}
                          >
                            ×
                          </button>
                          {a.mime.startsWith("image/") && (
                            <small>
                              Preview only · selected model has no vision
                            </small>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  <label htmlFor="prompt" className="sr-only">
                    Message Hermes
                  </label>
                  <textarea
                    id="prompt"
                    ref={input}
                    rows={1}
                    maxLength={12000}
                    value={text}
                    placeholder="Message Hermes…"
                    onChange={(e) => editText(e.target.value)}
                    disabled={!connected || !draftReady}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        e.currentTarget.form?.requestSubmit();
                      }
                    }}
                  />
                  <div className="composer-toolbar">
                    <div className="composer-left">
                      <div data-menu className="menu-anchor">
                        <MetalButton
                          open={menu === "plus"}
                          toggle={() =>
                            setMenu(menu === "plus" ? null : "plus")
                          }
                        />
                        {menu === "plus" && (
                          <AnchoredPopover id="composer-actions" anchor={document.getElementById("plus-menu")!}
                            close={() => setMenu(null)} placement="top-start" className="action-menu" menu label="Add to conversation">
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => { setMenu(null); fileInput.current?.click(); }}
                            >
                              <UIIcon name="file" /> Photos and files
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={importFolder}
                            >
                              <UIIcon name="folder" /> Import folder
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={showFiles}
                            >
                              <UIIcon name="file" /> Project library
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              disabled={!caps?.recording}
                              onClick={startRecording}
                            >
                              <UIIcon name="mic" /> Record voice note
                            </button>
                            {caps?.search.configured && (
                              <button
                                type="button"
                                role="menuitem"
                                onClick={searchWeb}
                              >
                                <UIIcon name="search" /> Search Wikipedia
                              </button>
                            )}
                          </AnchoredPopover>
                        )}
                      </div>
                      <input
                        ref={fileInput}
                        type="file"
                        multiple
                        hidden
                        accept="text/plain,.py,.cpp,.md,.txt,.json,image/png,image/jpeg,image/webp,audio/webm,audio/ogg,audio/wav"
                        onChange={(e) => addFiles(e.target.files)}
                      />
                      <label className="sr-only" htmlFor="model-picker">
                        Local model
                      </label>
                      <select
                        id="model-picker"
                        title={
                          selectedModel
                            ? `${selectedModel.label} · ${selectedModel.state.replaceAll("_", " ")}`
                            : "No verified local models"
                        }
                        aria-describedby="model-readiness"
                        value={selectedModel ? model : ""}
                        onChange={(e) => setModel(e.target.value)}
                        disabled={active}
                        onFocus={() =>
                          rpc<Model[]>("models.list")
                            .then(setModels)
                            .catch(report)
                        }
                      >
                        {!models.length && (
                          <option value="">No verified local models</option>
                        )}
                        {models.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.label}
                          </option>
                        ))}
                      </select>
                      <span
                        id="model-readiness"
                        className="sr-only"
                        aria-live="polite"
                      >
                        {selectedModel
                          ? selectedModel.state.replaceAll("_", " ")
                          : "No verified local models"}
                      </span>
                      <div data-menu className="menu-anchor">
                        <button
                          type="button"
                          className="effort-button"
                          id="effort-toggle"
                          aria-haspopup="dialog"
                          aria-controls={menu === "effort" ? "effort-options" : undefined}
                          aria-label="Reasoning effort"
                          aria-expanded={menu === "effort"}
                          onClick={() =>
                            setMenu(menu === "effort" ? null : "effort")
                          }
                        >
                          <Brain on={effort === "on"} />
                        </button>
                        {menu === "effort" && (
                          <AnchoredPopover id="effort-options" anchor={document.getElementById("effort-toggle")!}
                            close={() => setMenu(null)} placement="top-end" className="effort-popover" label="Reasoning effort">
                            <Effort
                              value={effort}
                              change={setEffort}
                              supported={!!selectedModel?.reasoning.length}
                            />
                          </AnchoredPopover>
                        )}
                      </div>
                      <PermissionMode {...permissions} />
                    </div>
                    <div className="composer-right">
                      {busy && uploadController.current && (
                        <button
                          type="button"
                          onClick={() => uploadController.current?.abort()}
                        >
                          Cancel upload
                        </button>
                      )}
                      <button
                        type="button"
                        className="icon-button mic-button"
                        aria-label="Record voice note"
                        disabled={busy || active || !caps?.recording}
                        onClick={startRecording}
                      >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <rect x="9" y="3" width="6" height="12" rx="3" />
                          <path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6" />
                        </svg>
                      </button>
                      {active ? (
                        <button
                          type="button"
                          className="send-button cancel"
                          id="cancel-response"
                          aria-label="Cancel response"
                          disabled={run.state === "cancelling"}
                          onClick={cancelResponse}
                        >
                          ■
                        </button>
                      ) : (
                        <button
                          type="submit"
                          className="send-button"
                          id="send"
                          aria-label="Send message"
                          disabled={
                            !connected ||
                            !draftReady ||
                            !draftAttachments.ready ||
                            draftAttachments.issues.length > 0 ||
                            busy ||
                            !text.trim() ||
                            !selectedModel ||
                            !modelReady
                          }
                        >
                          ↑
                        </button>
                      )}
                    </div>
                  </div>
                </form>
                <span id="connection" className="sr-only">
                  {connected ? "Connected" : "Connecting"}
                </span>
              </div>
            </section>
            {rowMenu && <AnchoredPopover id="row-actions" anchor={rowMenu.anchor} close={() => setRowMenu(null)}
              className="row-action-menu" menu label={"Actions for " + (rowMenu.kind === "folder" ? rowMenu.value.label : rowMenu.value.title)}>
              <button role="menuitem" type="button" onClick={() => {
                managementEpoch.current++;
                setManagementSaving(false);
                setManagementFailure(null);
                managementInvoker.current = rowMenu.anchor;
                setManagementDelete(false);
                if (rowMenu.kind === "folder") { setEditingFolder(rowMenu.value); setPanel("Folder"); }
                else { setManagedSession(rowMenu.value); setManagedProject(rowMenu.value.project); setFormValue(rowMenu.value.title); setPanel("Conversation"); }
                setRowMenu(null);
              }}>{rowMenu.kind === "folder" ? "Edit folder…" : "Rename or move…"}</button>
              <button role="menuitem" type="button" className="danger-action" onClick={() => {
                managementEpoch.current++;
                setManagementSaving(false);
                setManagementFailure(null);
                managementInvoker.current = rowMenu.anchor;
                setManagementDelete(true);
                if (rowMenu.kind === "folder") { setEditingFolder(rowMenu.value); setPanel("Folder"); }
                else { setManagedSession(rowMenu.value); setManagedProject(rowMenu.value.project); setFormValue(rowMenu.value.title); setPanel("Conversation"); }
                setRowMenu(null);
              }}>Review deletion…</button>
            </AnchoredPopover>}
            <AnimatePresence initial={false}>
              {panel && (
                <Panel key={panel} title={managementDelete && (panel === "Folder" || panel === "Conversation") ? "Delete " + panel.toLowerCase() : panel} close={() => { managementEpoch.current++; if (panel === "Import folder") folderImport.reset(); setPanel(null); }}
                  returnFocusTo={panel === "Folder" || panel === "Conversation" ? managementInvoker.current : null}>
                  {(panel === "Folder" || panel === "Conversation") && <ManagementError failure={managementFailure} epoch={managementEpoch.current} />}
                  {panel === "Settings" ? (
                    <>
                      <section
                        className="settings-section"
                        aria-label="Interface preferences"
                      >
                        <label className="setting-line">
                          Less motion
                          <input
                            type="checkbox"
                            checked={reduced}
                            onChange={(e) => setReduced(e.target.checked)}
                          />
                        </label>
                        <label className="setting-line">
                          Click volume <output>{volume}%</output>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={volume}
                            onChange={(e) => {
                              const v = +e.target.value;
                              setVolume(v);
                              localStorage.setItem(
                                "hermes-ui:interface-volume",
                                String(v),
                              );
                              audio.current?.setVolume(v / 100);
                            }}
                          />
                        </label>
                      </section>
                      <PermissionSettings
                        controller={permissions}
                        workspace={
                          folders.find((item) => item.id === folder)?.label ??
                          "No project selected"
                        }
                      />
                      <details className="settings-disclosure">
                        <summary>Local models</summary>
                        {models.map((m) => (
                          <p key={m.id}>
                            <strong>{m.label}</strong>
                            <br />
                            <small>
                              {m.state.replaceAll("_", " ")} ·{" "}
                              {m.sha256.slice(0, 16)}…
                            </small>
                          </p>
                        ))}
                        {readiness && readiness.state !== "ready" && (
                          <p className="run-error">{readiness.detail}</p>
                        )}
                      </details>
                      <details className="settings-disclosure">
                        <summary>Capabilities</summary>
                        <p>
                          Text conversations. Images are preview-only. Voice
                          transcription:{" "}
                          {caps?.transcription ? "local CPU" : "not installed"}.
                          Search: Wikipedia.
                        </p>
                      </details>
                      <a
                        className="settings-credit"
                        href="https://www.rareui.com"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Six interface components by Rare UI
                      </a>
                    </>
                  ) : panel === "New folder" ? (
                    <form className="app-form" onSubmit={createFolder}>
                      <label>
                        Folder name
                        <input
                          autoFocus
                          value={formValue}
                          onChange={(event) => setFormValue(event.target.value)}
                          required
                          maxLength={80}
                        />
                      </label>
                      <button className="primary-button" type="submit">
                        Create folder
                      </button>
                    </form>
                  ) : panel === "Search Wikipedia" ? (
                    <form
                      className="app-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (!formValue.trim()) return;
                        if (!text.trim()) editText(formValue.trim());
                        setPanel(null);
                        requestAction({
                          type: "search.wikipedia",
                          query: formValue.trim(),
                        });
                        input.current?.focus();
                      }}
                    >
                      <label>
                        Search query
                        <input
                          autoFocus
                          value={formValue}
                          onChange={(event) => setFormValue(event.target.value)}
                          required
                          maxLength={200}
                        />
                      </label>
                      <p className="muted">
                        The server checks this conversation's permissions before
                        searching. Approved results can be included with your
                        next message.
                      </p>
                      <button className="primary-button" type="submit">
                        Review search
                      </button>
                    </form>
                  ) : panel === "Import folder" ? (
                    <div className="folder-import-panel">
                      <div className="folder-preview">
                        <FolderImport
                          size="md"
                          color={theme === "dark" ? "black" : "white"}
                        />
                      </div>
                      <p>
                        Select a host folder, review the file list, then copy it
                        into your selected project. Originals stay unchanged.
                      </p>
                      {!folder && (
                        <p className="run-error">
                          Select a project before importing.
                        </p>
                      )}
                      {folderImport.error && <p className="run-error" role="alert">{folderImport.error}</p>}
                      <button
                        className="primary-button"
                        disabled={busy || !!folderImport.pending || !folder}
                        onClick={folderImport.choose}
                      >
                        {folderImport.pending === "choosing" ? "Waiting for folder picker…" : "Choose folder"}
                      </button>
                      {folderImport.preview && (
                        <section className="import-review">
                          <h3>Review import</h3>
                          <p>
                            {folderImport.preview.files.length} files ·{" "}
                            {folderImport.preview.bytes.toLocaleString()} bytes
                          </p>
                          <ul>
                            {folderImport.preview.files.map((path) => (
                              <li key={path}>{path}</li>
                            ))}
                          </ul>
                          <button
                            className="primary-button"
                            disabled={busy || !!folderImport.pending}
                            onClick={folderImport.commit}
                          >
                            {folderImport.pending === "copying" ? "Copying reviewed files…" : "Copy reviewed files"}
                          </button>
                          <button
                            className="secondary-button"
                            disabled={!!folderImport.pending}
                            onClick={folderImport.reset}
                          >
                            Cancel import
                          </button>
                        </section>
                      )}
                    </div>
                  ) : panel === "Details" ? (
                    <>
                      <p>{selectedModel?.label ?? "No verified model"}</p>
                      <p>Run: {run?.state ?? "idle"}</p>
                      <pre>{JSON.stringify(run?.identity ?? {}, null, 2)}</pre>
                      <h3>Connection</h3>
                      <pre>{JSON.stringify(readiness, null, 2)}</pre>
                      <h3>Guest task</h3>
                      <p className="muted">
                        Guest model:{" "}
                        {models.find(
                          (item) =>
                            item.id ===
                            sessions.find((item) => item.id === session)?.arm,
                        )?.label || "Choose a conversation"}
                        . The guest uses this conversation’s assigned model.
                      </p>
                      <p className="muted">
                        Fixed supported tasks run only in a qualified isolated
                        guest. Host shell access is unavailable.
                      </p>
                      <form
                        className="app-form"
                        onSubmit={async (event) => {
                          event.preventDefault();
                          try {
                            const snapshot = await rpc<{
                              snapshot_sha256: string | null;
                              job_eligibility_reason?: string;
                            }>("workspace.files", { project_id: folder });
                            if (!snapshot.snapshot_sha256)
                              throw Error(
                                snapshot.job_eligibility_reason ||
                                  "A valid reviewed text workspace is required.",
                              );
                            await requestAction({
                              type: "guest.submit",
                              task_kind: taskKind,
                              prompt: actionPrompt,
                              snapshot_sha256: snapshot.snapshot_sha256,
                            });
                          } catch (error) {
                            report(error);
                          }
                        }}
                      >
                        <label>
                          Task
                          <select
                            value={taskKind}
                            onChange={(event) =>
                              setTaskKind(event.target.value)
                            }
                          >
                            <option value="python">
                              Python · clamp JSON values to 0–100
                            </option>
                            <option value="cpp">
                              C++ · square input integers
                            </option>
                            <option value="diagnostic">Diagnostic</option>
                          </select>
                        </label>
                        <small>
                          The Python and C++ checks use these fixed contracts.
                          Diagnostic results require manual review.
                        </small>
                        <label>
                          Task instructions
                          <textarea
                            value={actionPrompt}
                            onChange={(event) =>
                              setActionPrompt(event.target.value)
                            }
                            maxLength={12000}
                          />
                        </label>
                        <button
                          type="submit"
                          className="primary-button"
                          disabled={
                            !folder ||
                            !permissions.policy?.available.guest?.available ||
                            !actionPrompt.trim()
                          }
                        >
                          Review guest task
                        </button>
                        {!permissions.policy?.available.guest?.available && (
                          <small>
                            {permissions.policy?.available.guest?.reason ||
                              "Guest is unavailable"}
                          </small>
                        )}
                      </form>
                      <h3>Observed activity</h3>
                      {events
                        .filter((e) => e.type !== "delta")
                        .map((e) => (
                          <p key={e.seq}>
                            {e.type}:{" "}
                            {e.label ?? e.name ?? String(e.text ?? "")}
                          </p>
                        ))}
                    </>
                  ) : panel === "Files" ? (
                    <>
                      <p className="muted">
                        {folder
                          ? "App-owned workspace copy"
                          : "Select a project folder to browse its files."}
                      </p>
                      <button onClick={importFolder}>Import folder</button>
                      <ul className="file-list">
                        {fileNames.map((name) => (
                          <li key={name}>
                            <button onClick={() => readFile(name)}>
                              {name}
                            </button>
                          </li>
                        ))}
                      </ul>
                      {selectedFile && (
                        <>
                          <h3>{selectedFile.path}</h3>
                          <pre>{selectedFile.text}</pre>
                          <form
                            className="app-form"
                            onSubmit={(event) => {
                              event.preventDefault();
                              requestAction({
                                type: "workspace.write",
                                path: selectedFile.path,
                                text: editingText,
                                expected_sha256: selectedFile.sha256,
                              });
                            }}
                          >
                            <label>
                              Edit workspace copy
                              <textarea
                                value={editingText}
                                onChange={(event) =>
                                  setEditingText(event.target.value)
                                }
                                maxLength={200000}
                              />
                            </label>
                            <button
                              className="primary-button"
                              disabled={editingText === selectedFile.text}
                              type="submit"
                            >
                              Review changes
                            </button>
                          </form>
                          <button onClick={attachLibrary}>
                            Attach this file
                          </button>
                        </>
                      )}
                    </>
                  ) : panel === "Conversation" ? (
                    <>
                      {!managementDelete && <><form
                        className="app-form"
                        onSubmit={async (event) => {
                          event.preventDefault();
                          if (!managedSession || !formValue.trim() || managementPending.current === managementEpoch.current) return;
                          const epoch = managementEpoch.current;
                          const target = managedSession;
                          managementPending.current = epoch;
                          setManagementSaving(true);
                          setManagementFailure(null);
                          try {
                            const saved = await saveManagedConversation(target, { title: formValue, project: managedProject }, {
                              rename: (id, title) => rpc("session.rename", { session_id: id, title }),
                              move: (id, project) => rpc("session.move", { session_id: id, project_id: project }),
                            });
                            if (currentSession.current === target.id && saved.project !== target.project) setFolder(saved.project);
                            await refresh();
                            if (managementEpoch.current === epoch) {
                              setManagedSession(saved);
                              setPanel(null);
                            }
                          } catch (error) {
                            if (managementEpoch.current === epoch) setManagementFailure({ epoch, message: managementFailureMessage(error) });
                            else report(Error("An earlier conversation save failed: " + managementFailureMessage(error)));
                          } finally {
                            if (managementEpoch.current === epoch) {
                              managementPending.current = null;
                              setManagementSaving(false);
                            }
                          }
                        }}
                      >
                        <label>
                          Conversation name
                          <input
                            value={formValue}
                            disabled={managementSaving}
                            required
                            maxLength={80}
                            onChange={(event) =>
                              setFormValue(event.target.value)
                            }
                          />
                        </label>
                      <label className="setting-line">
                        Move to folder
                        <select
                          value={managedProject ?? ""}
                          title={folders.find(item => item.id === managedProject)?.label ?? "No folder"}
                          disabled={managementSaving}
                          onChange={event => setManagedProject(event.target.value || null)}
                        >
                          <option value="">No folder</option>
                          {folders.map((f) => (
                            <option key={f.id} value={f.id}>
                              {f.label}
                            </option>
                          ))}
                        </select>
                      </label>
                        <button className="primary-button" type="submit" disabled={managementSaving}>
                          {managementSaving ? "Saving…" : "Save changes"}
                        </button>
                        <button type="button" onClick={() => { managementEpoch.current++; setPanel(null); }}>Cancel</button>
                      </form></>}
                      {managementDelete && <><p><strong>{managedSession?.title}</strong></p>
                      <p>
                        Delete this conversation and its app-owned references.
                      </p>
                      {managedSession && (
                        <DeleteButton
                          onConfirm={async () => {
                            const epoch = managementEpoch.current;
                            await deleteRecord("conversation", managedSession.id);
                            if (managementEpoch.current === epoch) setPanel(null);
                          }}
                        />
                      )}</>}
                    </>
                  ) : (
                    editingFolder && (
                      <>
                        {!managementDelete && <><label className="setting-line">
                          Name
                          <input
                            value={editingFolder.label}
                            disabled={managementSaving}
                            maxLength={80}
                            onChange={(e) =>
                              setEditingFolder({
                                ...editingFolder,
                                label: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label className="setting-line">
                          Parent
                          <select
                            value={editingFolder.parent ?? ""}
                            disabled={managementSaving}
                            onChange={(e) =>
                              setEditingFolder({
                                ...editingFolder,
                                parent: e.target.value || null,
                              })
                            }
                          >
                            <option value="">Top level</option>
                            {folders
                              .filter((f) => f.id !== editingFolder.id)
                              .map((f) => (
                                <option key={f.id} value={f.id}>
                                  {f.label}
                                </option>
                              ))}
                          </select>
                        </label>
                        <fieldset className="color-picker">
                          <legend>Folder colour</legend>
                          {palette.map((color) => (
                            <button
                              key={color}
                              aria-label={color}
                              aria-pressed={editingFolder.color === color}
                              disabled={managementSaving}
                              style={{ background: `var(--${color})` }}
                              onClick={() =>
                                setEditingFolder({ ...editingFolder, color })
                              }
                            />
                          ))}
                        </fieldset>
                        <button
                          onClick={async () => {
                            const epoch = managementEpoch.current;
                            if (managementPending.current === epoch) return;
                            managementPending.current = epoch;
                            setManagementSaving(true);
                            setManagementFailure(null);
                            try {
                              await rpc("folder.update", {
                                project_id: editingFolder.id,
                                label: editingFolder.label,
                                parent: editingFolder.parent,
                                color: editingFolder.color,
                              });
                              await refresh();
                              if (managementEpoch.current === epoch) setPanel(null);
                            } catch (e) {
                              if (managementEpoch.current === epoch) setManagementFailure({ epoch, message: managementFailureMessage(e) });
                              else report(Error("An earlier folder save failed: " + managementFailureMessage(e)));
                            } finally {
                              if (managementEpoch.current === epoch) {
                                managementPending.current = null;
                                setManagementSaving(false);
                              }
                            }
                          }}
                          disabled={managementSaving}
                        >
                          Save folder
                        </button></>}
                        {managementDelete && <><p><strong>{editingFolder.label}</strong></p>
                        <p>
                          Deleting this folder includes its child folders and
                          conversations. Original host folders stay unchanged.
                        </p>
                        <DeleteButton
                          onConfirm={async () => {
                            const epoch = managementEpoch.current;
                            await deleteRecord("project", editingFolder.id);
                            if (managementEpoch.current === epoch) setPanel(null);
                          }}
                        /></>}
                      </>
                    )
                  )}
                </Panel>
              )}
            </AnimatePresence>
            {(recording || voice) && (
              <Panel
                title={recording ? "Recording" : "Voice note"}
                close={() => {
                  recordingSession.current.cancel();
                  setRecording(false);
                  setVoice(null);
                }}
              >
                {recording ? (
                  <>
                    <div className="recording-indicator" role="status">
                      <span />
                      Recording · {recordSeconds}s
                    </div>
                    <div
                      className="recording-levels"
                      role="meter"
                      aria-label="Microphone input level"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(
                        Math.max(0, ...recordLevels) * 100,
                      )}
                    >
                      {recordLevels.map((value, index) => (
                        <i
                          key={index}
                          style={{
                            height: `${Math.max(2, Math.min(100, value * 360))}%`,
                          }}
                        />
                      ))}
                    </div>
                    <button onClick={stopRecording}>Stop recording</button>
                    <button
                      onClick={() => {
                        recordingSession.current.cancel();
                        setRecording(false);
                      }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  voice && (
                    <>
                      <VoiceNote
                        src={voice.url}
                        duration={voice.duration}
                        waveform={voice.waveform}
                      />
                      <p>
                        {caps?.transcription
                          ? "Transcribe locally, then edit before sending."
                          : "Local transcription is not installed."}
                      </p>
                      <button
                        disabled={busy || !caps?.transcription}
                        onClick={useVoice}
                      >
                        {busy ? "Transcribing locally…" : "Use voice note"}
                      </button>
                      <button onClick={() => setVoice(null)}>
                        Delete recording
                      </button>
                    </>
                  )
                )}
              </Panel>
            )}
          </div>
        </VoiceNoteGroup>
      </MotionConfig>
    </ReducedMotionContext.Provider>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
