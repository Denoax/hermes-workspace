export type Folder = {
  id: string;
  label: string;
  parent: string | null;
  color: string;
};
export type Session = {
  id: string;
  project: string | null;
  arm: string;
  title: string;
};
export type Model = {
  id: string;
  label: string;
  state: string;
  sha256: string;
  reasoning: string[];
  vision: boolean;
};
export type Run = {
  id: string;
  session: string;
  model: string;
  state: string;
  error: string | null;
  created: number;
  identity: unknown;
};
export type Event = {
  run_id: string;
  seq: number;
  type: string;
  state?: string;
  label?: string;
  error?: string;
  text?: string;
  name?: string;
  lines?: number;
  [key: string]: unknown;
};
export type Attachment = {
  id: string;
  name: string;
  mime: string;
  bytes: number;
  metadata: {
    transcript?: string;
    duration?: number;
    waveform?: number[];
    search?: Search;
  };
};
export type Search = {
  query: string;
  provider: string;
  sources: { id: string; title: string; url: string; text: string }[];
  attachment?: Attachment;
};
let csrf = "";
let bootstrapping: Promise<{ csrf: string; version: number }> | null = null;
export async function bootstrap() {
  if (!bootstrapping)
    bootstrapping = (async () => {
      const r = await fetch("/hermes-workspace/api/bootstrap");
      const d = await r.json();
      if (!r.ok) throw Error(d.error);
      csrf = d.csrf;
      return d;
    })().finally(() => {
      bootstrapping = null;
    });
  return bootstrapping;
}
async function authorizedFetch(path: string, options: RequestInit) {
  if (!csrf) await bootstrap();
  for (let attempt = 0; ; attempt++) {
    const token = csrf;
    const response = await fetch(path, {
      ...options,
      headers: { ...options.headers, "X-Hermes-CSRF": token },
    });
    // The server rejects this specific refusal before dispatch. A service
    // restart rotates CSRF; retrying the unchanged operation once is safe.
    if (
      response.status !== 403 ||
      attempt ||
      (await response.clone().json()).error !== "session_or_CSRF_denied"
    )
      return response;
    if (csrf === token) {
      csrf = "";
      await bootstrap();
    } else if (!csrf) await bootstrap();
  }
}
export async function rpc<T = unknown>(
  method: string,
  fields: Record<string, unknown> = {},
): Promise<T> {
  // The server rejects bursts before executing a method. Only that explicit
  // refusal is safe to retry; transport failures retain Send's idempotency ID.
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await authorizedFetch("/hermes-workspace/api/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hermes-CSRF": csrf },
      body: JSON.stringify({ version: 1, method, fields }),
    });
    const d = await r.json();
    if (r.status === 429 && attempt < 2) {
      await new Promise((resolve) => setTimeout(resolve, 600 * (attempt + 1)));
      continue;
    }
    if (!r.ok || d.error) throw Error(d.error || "Request failed");
    return d.result;
  }
  throw Error("Local request rate exceeded; retry shortly.");
}
export async function upload(
  file: Blob,
  name: string,
  signal?: AbortSignal,
): Promise<Attachment> {
  const r = await authorizedFetch("/hermes-workspace/api/upload", {
    method: "POST",
    headers: {
      "Content-Type": file.type || "text/plain",
      "X-Hermes-CSRF": csrf,
      "X-Filename": encodeURIComponent(name),
    },
    body: file,
    signal,
  });
  const d = await r.json();
  if (!r.ok) throw Error(d.error);
  return d.result;
}
export async function stream(
  run: string,
  after: number,
  onEvent: (e: Event) => void,
  signal: AbortSignal,
) {
  const r = await authorizedFetch("/hermes-workspace/api/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Hermes-CSRF": csrf },
    body: JSON.stringify({ run_id: run, after }),
    signal,
  });
  if (!r.ok) throw Error("Stream connection failed");
  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 1);
      if (line) {
        const e = JSON.parse(line);
        if (e.type !== "keepalive") onEvent(e);
      }
    }
  }
}
export const terminal = (state: string) =>
  ["completed", "cancelled", "failed"].includes(state);
export const audioURL = (id: string) =>
  "/hermes-workspace/api/attachment/" + id;
