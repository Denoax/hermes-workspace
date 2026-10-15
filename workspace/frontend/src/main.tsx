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
import { AnimatePresence, MotionConfig } from "motion/react";
import Markdown from "react-markdown";
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
import { sourceCitations } from "./lib/citations";
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
    [attachments, setAttachments] = useState<Attachment[]>([]),
    [search, setSearch] = useState<Search | null>(null),
    [searchQuery, setSearchQuery] = useState<string | null>(null);
  const [panel, setPanel] = useState<string | null>(null),
    [menu, setMenu] = useState<string | null>(null),
    [mobile, setMobile] = useState(false),
    [editingFolder, setEditingFolder] = useState<Folder | null>(null);
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
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [notchWidth, setNotchWidth] = useState(210);
  const notchContext = useRef<HTMLDivElement>(null);
  const notchLabel = useRef<HTMLElement>(null);
  const [recordLevels, setRecordLevels] = useState<number[]>([]);
  const [formValue, setFormValue] = useState("");
  const [importPreview, setImportPreview] = useState<{
    ticket: string;
    files: string[];
    bytes: number;
  } | null>(null);
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
    nextCursor = useRef(0),
    messageEnd = useRef<HTMLDivElement>(null);
  currentSession.current = session;
  const active = !!run && !terminal(run.state);
  const selectedModel = models.find((m) => m.id === model);
  const selectedReadiness = readiness?.models?.[model];
  const modelReady =
    readiness?.state === "ready" && selectedReadiness?.available !== false;
  const report = useCallback(
    (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
    [],
  );
  const permissions = usePermissions(session, ensureSession, report);
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
    return () => recorder.current.cancel();
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
        const result = await rpc<{ actions: Action[]; pending: Action[] }>(
          "permissions.read",
          { session_id: session },
        );
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
  }, [theme, reduced, connected, folder, session, model]);
  useEffect(() => {
    if (!connected) return;
    setDraftReady(false);
    let alive = true;
    if (!session) {
      setMessages([]);
      setRun(null);
      setEvents([]);
      setText(localStorage.getItem("hermes:new-draft") ?? "");
      setDraftReady(true);
      return;
    }
    load(session)
      .then(() => rpc<{ text: string }>("draft.read", { session_id: session }))
      .then((d) => {
        if (alive) {
          setText(d.text);
          setDraftReady(true);
        }
      })
      .catch(report);
    return () => {
      alive = false;
    };
  }, [session, connected]);
  useEffect(() => {
    setSelectedFile(null);
    setEditingText("");
    setFileNames([]);
  }, [folder]);
  useEffect(() => {
    if (!connected || !draftReady) return;
    const id = setTimeout(() => {
      if (session)
        rpc("draft.write", { session_id: session, text, mode: "chat" }).catch(
          report,
        );
      else localStorage.setItem("hermes:new-draft", text);
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
  useEffect(() => {
    messageEnd.current?.scrollIntoView({ block: "end", behavior: "instant" });
  }, [messages.length, actionRows.length]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: PointerEvent) => {
      if (!(event.target as HTMLElement).closest("[data-menu]")) setMenu(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenu(null);
        input.current?.focus();
      }
    };
    addEventListener("pointerdown", close);
    addEventListener("keydown", escape);
    return () => {
      removeEventListener("pointerdown", close);
      removeEventListener("keydown", escape);
    };
  }, [menu]);
  useEffect(() => {
    if (!recording) return;
    const tick = setInterval(
      () =>
        setRecordSeconds(
          Math.floor((performance.now() - recorder.current.started) / 1000),
        ),
      1000,
    );
    const hidden = () => {
      if (document.hidden) {
        recorder.current.cancel();
        setRecording(false);
        setError("Recording cancelled when the app became hidden.");
      }
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      clearInterval(tick);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [recording]);
  useEffect(() => {
    const pause = () => {
      if (document.hidden)
        document.querySelectorAll("audio").forEach((a) => a.pause());
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
    setSession(null);
    setMessages([]);
    setRun(null);
    setAttachments([]);
    setSearch(null);
    setMobile(false);
    setText("");
    setTimeout(() => input.current?.focus(), 0);
  }
  async function ensureSession(): Promise<string> {
    if (currentSession.current) return currentSession.current;
    if (!sessionCreation.current)
      sessionCreation.current = (async () => {
        const created = await rpc<Session>("session.create", {
          project_id: folder,
          arm: model,
        });
        await rpc("draft.write", {
          session_id: created.id,
          text,
          mode: "chat",
        });
        currentSession.current = created.id;
        setSession(created.id);
        return created.id;
      })().finally(() => {
        sessionCreation.current = null;
      });
    return sessionCreation.current;
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current || busy || active || !text.trim() || !selectedModel)
      return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      const ready = await refreshReadiness();
      if (ready.state !== "ready" || ready.models?.[model]?.available === false)
        throw Error(
          ready.models?.[model]?.detail ||
            ready.detail ||
            "Local model connection needs repair. Your draft is preserved.",
        );
      const id = await ensureSession();
      const pendingKey = "hermes:pending:" + id;
      let pending: Record<string, unknown> | null = null;
      try {
        pending = JSON.parse(localStorage.getItem(pendingKey) || "null");
      } catch {}
      if (
        pending &&
        (pending.prompt !== text ||
          pending.model_id !== model ||
          pending.reasoning !== effort ||
          JSON.stringify(pending.attachments) !==
            JSON.stringify(attachments.map((a) => a.id)) ||
          pending.search_query !== searchQuery)
      )
        pending = null;
      const fields = pending ?? {
        session_id: id,
        request_id: crypto.randomUUID().replaceAll("-", ""),
        model_id: model,
        prompt: text,
        reasoning: effort,
        attachments: attachments.map((a) => a.id),
        search_query: searchQuery,
      };
      localStorage.setItem(pendingKey, JSON.stringify(fields));
      await rpc<Run>("chat.submit", fields);
      localStorage.removeItem(pendingKey);
      await rpc("draft.write", { session_id: id, text: "", mode: "chat" });
      if (currentSession.current === id) {
        localStorage.removeItem("hermes:new-draft");
        setText("");
        setAttachments([]);
        setSearch(null);
        setSearchQuery(null);
      }
      await load(id);
      await refresh();
    } catch (e) {
      report(e);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  async function addFiles(files: FileList | null) {
    if (!files) return;
    setMenu(null);
    setBusy(true);
    setError("");
    uploadController.current = new AbortController();
    try {
      if (attachments.length + files.length > 8)
        throw Error("At most eight attachments per turn.");
      for (const file of Array.from(files)) {
        if (attachments.length >= 8)
          throw Error("At most eight attachments per turn.");
        let item = await upload(
          /\.(py|cpp|c|h|md|json|txt)$/i.test(file.name)
            ? new Blob([file], { type: "text/plain" })
            : file,
          file.name,
          uploadController.current.signal,
        );
        if (item.mime.startsWith("audio/")) {
          if (!caps?.transcription)
            throw Error(
              "Audio stored, but local transcription is unavailable.",
            );
          item = await rpc<Attachment>("attachment.transcribe", {
            id: item.id,
          });
          setText(
            (t) => (t ? t + "\n" : "") + (item.metadata.transcript ?? ""),
          );
        }
        setAttachments((a) => [...a, item]);
      }
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
      uploadController.current = null;
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  async function startRecording() {
    setMenu(null);
    setError("");
    try {
      const id = await ensureSession();
      try {
        await rpc("recording.authorize", { session_id: id });
      } catch (error) {
        setPanel("Settings");
        throw error;
      }
      await recorder.current.start(
        () => {
          setRecording(false);
          setError(
            "Recording stopped at the two-minute limit; microphone released.",
          );
        },
        setRecordLevels,
        () => {
          setRecording(false);
          setError(
            "Microphone disconnected or recording failed; capture released. Reconnect the device and start again.",
          );
        },
      );
      setRecording(true);
      setRecordSeconds(0);
      setRecordLevels([]);
    } catch (e) {
      recorder.current.cancel();
      report(e);
    }
  }
  async function stopRecording() {
    try {
      const blob = await recorder.current.stop();
      setRecording(false);
      const measured = await waveform(blob);
      setVoice({ blob, ...measured, url: URL.createObjectURL(blob) });
    } catch (e) {
      setRecording(false);
      report(e);
    }
  }
  async function useVoice() {
    if (!voice) return;
    setBusy(true);
    try {
      const item = await upload(voice.blob, "Voice note.webm");
      const transcribed = await rpc<Attachment>("attachment.transcribe", {
        id: item.id,
      });
      setAttachments((a) => [...a, transcribed]);
      setText(transcribed.metadata.transcript ?? "");
      setVoice(null);
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
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
    setImportPreview(null);
    setPanel("Import folder");
  }
  async function chooseImportFolder() {
    if (!folder) {
      setError("Create or select a project before importing a workspace copy.");
      return;
    }
    setBusy(true);
    try {
      const preview = await rpc<{
        cancelled?: boolean;
        ticket: string;
        files: string[];
        bytes: number;
      }>("workspace.import.request", { project_id: folder });
      if (!preview.cancelled) setImportPreview(preview);
    } catch (error) {
      report(error);
    } finally {
      setBusy(false);
    }
  }
  async function commitImport() {
    if (!importPreview || !folder) return;
    setBusy(true);
    try {
      await rpc("workspace.import.commit", {
        project_id: folder,
        ticket: importPreview.ticket,
      });
      setImportPreview(null);
      await showFiles();
    } catch (error) {
      report(error);
    } finally {
      setBusy(false);
    }
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
    if (!selectedFile) return;
    try {
      const item = await upload(
        new Blob([selectedFile.text], { type: "text/plain" }),
        selectedFile.path.split("/").at(-1)!,
      );
      setAttachments((a) => [...a, item]);
      setPanel(null);
    } catch (e) {
      report(e);
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
        if (result.attachment)
          setAttachments((old) =>
            old.some((item) => item.id === result.attachment!.id)
              ? old
              : [...old, result.attachment!],
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
    if (id === session || (kind === "project" && id === folder)) {
      currentSession.current = null;
      setSession(null);
      if (kind === "project") setFolder(null);
    }
    const current = await refresh();
    if (session && !current.sessions.some((s) => s.id === session)) {
      currentSession.current = null;
      setSession(null);
    }
    if (folder && !current.folders.some((f) => f.id === folder))
      setFolder(null);
  }
  function folderRow(row: Folder, depth = 0): React.ReactNode {
    const open = expanded.has(row.id),
      children = folders.filter((f) => f.parent === row.id);
    return (
      <div
        key={row.id}
        role="treeitem"
        aria-expanded={children.length ? open : undefined}
        aria-selected={folder === row.id}
      >
        <div
          className={"folder-row " + (folder === row.id ? "selected" : "")}
          style={
            {
              "--depth": depth,
              "--folder-color": `var(--${row.color})`,
            } as CSSProperties
          }
        >
          <button
            className="branch-toggle"
            aria-label={(open ? "Collapse " : "Expand ") + row.label}
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
            onClick={() => {
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
            aria-label={"Edit " + row.label}
            onClick={() => {
              setEditingFolder(row);
              setPanel("Folder");
            }}
          >
            ···
          </button>
        </div>
        {open && (
          <div role="group">{children.map((f) => folderRow(f, depth + 1))}</div>
        )}
      </div>
    );
  }
  const listed = sessions.filter(
    (s) =>
      (query || folder === null ? true : s.project === folder) &&
      s.title.toLowerCase().includes(query.toLowerCase()),
  );
  const lastEvent = events.filter((e) => e.type !== "delta").at(-1);
  const label =
    events.filter((e) => e.type === "state").at(-1)?.label ??
    run?.state ??
    "Working";
  useLayoutEffect(() => {
    if (!active) return;
    const context = notchContext.current?.scrollWidth ?? 0;
    const status = (notchLabel.current?.scrollWidth ?? 0) + 19;
    setNotchWidth(Math.max(210, Math.min(340, Math.max(context, status) + 47)));
  }, [active, label, lastEvent?.name, selectedModel?.label, elapsed]);
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
                <span aria-hidden="true">⌕</span>
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
              <div
                className="folder-tree"
                role="tree"
                aria-label="Project folders"
              >
                <button
                  className={"all-conversations " + (!folder ? "selected" : "")}
                  onClick={() => {
                    setFolder(null);
                    setSession(null);
                  }}
                >
                  All conversations
                </button>
                {(query
                  ? folders.filter((f) =>
                      f.label.toLowerCase().includes(query.toLowerCase()),
                    )
                  : folders.filter((f) => !f.parent)
                ).map((f) => folderRow(f))}
              </div>
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
                      onClick={() => {
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
                      aria-label={"Manage " + s.title}
                      onClick={() => {
                        setSession(s.id);
                        setFolder(s.project);
                        setFormValue(s.title);
                        setPanel("Conversation");
                      }}
                    >
                      ···
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
                <span>{theme === "dark" ? "Dark" : "Light"} workspace</span>
                <button
                  id="sound-toggle"
                  className="icon-button"
                  aria-label="Mute interface sounds"
                  aria-pressed="true"
                >
                  ♫
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
                <span
                  className="conversation-title"
                  title={
                    folders.find((item) => item.id === folder)?.label ??
                    "No project selected"
                  }
                >
                  <span className="workspace-location">
                    {folders.find((item) => item.id === folder)?.label ??
                      "No project"}
                  </span>
                  <span aria-hidden="true"> / </span>
                  {sessions.find((item) => item.id === session)?.title ??
                    "New conversation"}
                </span>
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
              {active && (
                <div
                  className="activity-notch"
                  role="status"
                  style={{ width: notchWidth }}
                >
                  <div className="notch-meta" ref={notchContext}>
                    {lastEvent?.type === "file"
                      ? lastEvent.name + " · " + lastEvent.lines + " lines"
                      : (selectedModel?.label ?? "Local model")}
                  </div>
                  <div className="notch-working">
                    <WorkingIndicator state={run?.state ?? "queued"} />
                    <strong ref={notchLabel}>
                      {label}
                      {run?.state === "admitting" && model === "abliterated"
                        ? ` · ${elapsed}s`
                        : ""}
                    </strong>
                  </div>
                  <button
                    aria-label="Cancel current response"
                    onClick={() =>
                      run &&
                      rpc("chat.cancel", { run_id: run.id })
                        .then(() => setRun({ ...run, state: "cancelling" }))
                        .catch(report)
                    }
                  >
                    ×
                  </button>
                </div>
              )}
              <main className="conversation" aria-label="Conversation">
                <div className="message-column">
                  {!messages.length && folder && (
                    <div className="project-dashboard">
                      <h1>{folders.find((f) => f.id === folder)?.label}</h1>
                      <p>
                        {sessions.filter((s) => s.project === folder).length}{" "}
                        conversations ·{" "}
                        {folders.filter((f) => f.parent === folder).length}{" "}
                        folders
                      </p>
                      <div className="dashboard-actions">
                        <button onClick={newConversation}>
                          New conversation ↗
                        </button>
                        <button onClick={importFolder}>Import folder</button>
                        <button
                          onClick={() => {
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
                            onClick={() => setFolder(f.id)}
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
                  {!messages.length && !folder && (
                    <div className="empty-state">
                      <span className="empty-mark">H</span>
                      <h1>
                        {folder
                          ? folders.find((f) => f.id === folder)?.label
                          : "What are we working on?"}
                      </h1>
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
                        <Markdown
                          skipHtml
                          remarkPlugins={[
                            sourceCitations(
                              m.role === "assistant"
                                ? ((m.job
                                    ? historyAttachments[m.job]?.find(
                                        (a) => a.metadata.search,
                                      )?.metadata.search?.sources
                                    : undefined) ??
                                    (m.job === run?.id
                                      ? search?.sources
                                      : undefined) ??
                                    [])
                                : [],
                            ),
                          ]}
                        >
                          {m.text}
                        </Markdown>
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
                              setRun(retried);
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
                  <div ref={messageEnd} />
                </div>
              </main>
              <div className="composer-area">
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
                            onClick={() =>
                              setAttachments((old) =>
                                old.filter((x) => x.id !== a.id),
                              )
                            }
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
                    onChange={(e) => setText(e.target.value)}
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
                          <div className="action-menu" role="menu">
                            <button
                              type="button"
                              role="menuitem"
                              onClick={() => fileInput.current?.click()}
                            >
                              ↗ Photos and files
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={importFolder}
                            >
                              ▱ Import folder
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              onClick={showFiles}
                            >
                              ▤ Project library
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              disabled={!caps?.recording}
                              onClick={startRecording}
                            >
                              ♩ Record voice note
                            </button>
                            {caps?.search.configured && (
                              <button
                                type="button"
                                role="menuitem"
                                onClick={searchWeb}
                              >
                                ⌕ Search Wikipedia
                              </button>
                            )}
                          </div>
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
                            {m.label} · {m.state.replaceAll("_", " ")}
                          </option>
                        ))}
                      </select>
                      <div data-menu className="menu-anchor">
                        <button
                          type="button"
                          className="effort-button"
                          aria-label="Reasoning effort"
                          aria-expanded={menu === "effort"}
                          onClick={() =>
                            setMenu(menu === "effort" ? null : "effort")
                          }
                        >
                          <Brain on={effort === "on"} />
                        </button>
                        {menu === "effort" && (
                          <div className="effort-popover">
                            <Effort
                              value={effort}
                              change={setEffort}
                              supported={!!selectedModel?.reasoning.length}
                            />
                          </div>
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
                        ♩
                      </button>
                      {active ? (
                        <button
                          type="button"
                          className="send-button cancel"
                          id="cancel-response"
                          aria-label="Cancel response"
                          disabled={run.state === "cancelling"}
                          onClick={() =>
                            rpc("chat.cancel", { run_id: run.id })
                              .then(() =>
                                setRun({ ...run, state: "cancelling" }),
                              )
                              .catch(report)
                          }
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
            <AnimatePresence initial={false}>
              {panel && (
                <Panel key={panel} title={panel} close={() => setPanel(null)}>
                  {panel === "Settings" ? (
                    <>
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
                      <PermissionSettings
                        controller={permissions}
                        workspace={
                          folders.find((item) => item.id === folder)?.label ??
                          "No project selected"
                        }
                      />
                      <h3>Local models</h3>
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
                      <h3>Capabilities</h3>
                      <p>
                        Text conversations. Images are preview-only. Voice
                        transcription:{" "}
                        {caps?.transcription ? "local CPU" : "not installed"}.
                        Search: Wikipedia.
                      </p>
                      <h3>About</h3>
                      <p>Hermes × your local model.</p>
                      <a
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
                          maxLength={120}
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
                        if (!text.trim()) setText(formValue.trim());
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
                      <button
                        className="primary-button"
                        disabled={busy || !folder}
                        onClick={chooseImportFolder}
                      >
                        {busy ? "Waiting for folder picker…" : "Choose folder"}
                      </button>
                      {importPreview && (
                        <section className="import-review">
                          <h3>Review import</h3>
                          <p>
                            {importPreview.files.length} files ·{" "}
                            {importPreview.bytes.toLocaleString()} bytes
                          </p>
                          <ul>
                            {importPreview.files.map((path) => (
                              <li key={path}>{path}</li>
                            ))}
                          </ul>
                          <button
                            className="primary-button"
                            disabled={busy}
                            onClick={commitImport}
                          >
                            Copy reviewed files
                          </button>
                          <button
                            className="secondary-button"
                            onClick={() => setImportPreview(null)}
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
                      <form
                        className="app-form"
                        onSubmit={async (event) => {
                          event.preventDefault();
                          if (!session || !formValue.trim()) return;
                          try {
                            await rpc("session.rename", {
                              session_id: session,
                              title: formValue.trim(),
                            });
                            await refresh();
                            setPanel(null);
                          } catch (error) {
                            report(error);
                          }
                        }}
                      >
                        <label>
                          Conversation name
                          <input
                            value={formValue}
                            required
                            maxLength={120}
                            onChange={(event) =>
                              setFormValue(event.target.value)
                            }
                          />
                        </label>
                        <button className="primary-button" type="submit">
                          Save name
                        </button>
                      </form>
                      <label className="setting-line">
                        Move to folder
                        <select
                          value={folder ?? ""}
                          onChange={async (e) => {
                            if (!session) return;
                            try {
                              await rpc("session.move", {
                                session_id: session,
                                project_id: e.target.value || null,
                              });
                              setFolder(e.target.value || null);
                              await refresh();
                            } catch (e) {
                              report(e);
                            }
                          }}
                        >
                          <option value="">No folder</option>
                          {folders.map((f) => (
                            <option key={f.id} value={f.id}>
                              {f.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <p>
                        Delete this conversation and its app-owned references.
                      </p>
                      {session && (
                        <DeleteButton
                          onConfirm={() =>
                            deleteRecord("conversation", session)
                          }
                        />
                      )}
                    </>
                  ) : (
                    editingFolder && (
                      <>
                        <label className="setting-line">
                          Name
                          <input
                            value={editingFolder.label}
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
                              style={{ background: `var(--${color})` }}
                              onClick={() =>
                                setEditingFolder({ ...editingFolder, color })
                              }
                            />
                          ))}
                        </fieldset>
                        <button
                          onClick={async () => {
                            try {
                              await rpc("folder.update", {
                                project_id: editingFolder.id,
                                label: editingFolder.label,
                                parent: editingFolder.parent,
                                color: editingFolder.color,
                              });
                              await refresh();
                              setPanel(null);
                            } catch (e) {
                              report(e);
                            }
                          }}
                        >
                          Save folder
                        </button>
                        <p>
                          Deleting this folder includes its child folders and
                          conversations. Original host folders stay unchanged.
                        </p>
                        <DeleteButton
                          onConfirm={async () => {
                            await deleteRecord("project", editingFolder.id);
                            setPanel(null);
                          }}
                        />
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
                  recorder.current.cancel();
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
                        recorder.current.cancel();
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
