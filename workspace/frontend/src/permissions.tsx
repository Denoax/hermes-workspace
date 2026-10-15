import { useCallback, useEffect, useRef, useState } from "react";
import { rpc } from "./api";
export type Capability = "read" | "write" | "guest" | "search" | "microphone";
export type Action = {
  id: string;
  ticket_id: string;
  state: string;
  type: string;
  resource: string;
  summary: string;
  expires: number;
  action: Record<string, unknown>;
  diff?: string;
  result?: unknown;
  error?: string;
};
export type Policy = {
  session_id: string | null;
  project_id: string | null;
  version: number;
  mode: string;
  capabilities: Record<Capability, boolean>;
  available: Record<Capability, { available: boolean; reason: string }>;
  pending: Action[];
  actions?: Action[];
  grants: unknown[];
};
export const modeLabels: Record<string, string> = {
  chat_only: "Chat only",
  ask: "Ask before actions",
  workspace_agent: "Workspace agent",
  custom: "Custom",
};
const labels: Record<Capability, string> = {
  read: "Read project files and attached context",
  write: "Edit app workspace copies",
  guest: "Run supported tasks in a qualified guest",
  search: "Search Wikipedia",
  microphone: "Record microphone",
};
export function usePermissions(
  session: string | null,
  ensureSession: () => Promise<string>,
  report: (e: unknown) => void,
) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [updating, setUpdating] = useState(false);
  const sessionOwner = useRef(session);
  sessionOwner.current = session;
  const refreshPolicy = useCallback(
    async (owner: string | null = session) => {
      const next = await rpc<Policy>("permissions.read", { session_id: owner });
      if (sessionOwner.current === next.session_id) setPolicy(next);
      return next;
    },
    [session],
  );
  useEffect(() => {
    let alive = true;
    setPolicy(null);
    rpc<Policy>("permissions.read", { session_id: session })
      .then((next) => {
        if (alive) setPolicy(next);
      })
      .catch(report);
    return () => {
      alive = false;
    };
  }, [session]);
  async function update(
    mode: string,
    capabilities?: Partial<Record<Capability, boolean>>,
  ) {
    setUpdating(true);
    try {
      const id = session ?? (await ensureSession());
      const current = await rpc<Policy>("permissions.read", { session_id: id });
      const selected =
        mode === "custom"
          ? { ...current.capabilities, ...capabilities }
          : {
              read: mode === "workspace_agent",
              write: mode === "workspace_agent",
              guest: mode === "workspace_agent",
              search: false,
              microphone: false,
            };
      const next = await rpc<Policy>("permissions.update", {
        session_id: id,
        expected_version: current.version,
        mode,
        capabilities: selected,
      });
      if (sessionOwner.current === id) setPolicy(next);
    } catch (error) {
      report(error);
    } finally {
      setUpdating(false);
    }
  }
  async function revoke() {
    if (!session) return;
    try {
      await rpc("permissions.revoke", { session_id: session });
      await refreshPolicy();
    } catch (error) {
      report(error);
    }
  }
  return {
    policy: policy?.session_id === session ? policy : null,
    updating,
    update,
    revoke,
    refreshPolicy,
  };
}
export function PermissionMode({
  policy,
  updating,
  update,
  id = "permissions-mode",
}: Pick<ReturnType<typeof usePermissions>, "policy" | "updating" | "update"> & {
  id?: string;
}) {
  return (
    <label
      className="permission-mode"
      title="Permissions are enforced by this local server"
    >
      <span className="sr-only">Permissions</span>
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M10 2 16 4.4v5.2c0 4-6 7.4-6 7.4s-6-3.4-6-7.4V4.4Z" />
      </svg>
      <select
        id={id}
        aria-label="Permissions"
        value={policy?.mode ?? "chat_only"}
        disabled={updating || !policy}
        onChange={(event) => update(event.target.value)}
      >
        {Object.entries(modeLabels).map(([id, label]) => (
          <option key={id} value={id} disabled={id === "custom"}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}
export function PermissionSettings({
  controller,
  workspace,
}: {
  controller: ReturnType<typeof usePermissions>;
  workspace: string;
}) {
  const { policy, updating, update, revoke } = controller;
  return (
    <section className="permission-settings">
      <h3>Permissions</h3>
      <PermissionMode {...controller} id="settings-permissions-mode" />
      <p className="permission-workspace">
        Workspace: <strong>{workspace}</strong>
      </p>
      <p className="muted">
        Chat and explicitly attached context work in every mode. Actions use the
        scopes below.
      </p>
      {policy &&
        (Object.keys(labels) as Capability[]).map((name) => (
          <label className="permission-setting" key={name}>
            <span>
              {labels[name]}
              {!policy.available[name]?.available && (
                <small>{policy.available[name]?.reason || "Unavailable"}</small>
              )}
            </span>
            <input
              type="checkbox"
              checked={!!policy.capabilities[name]}
              disabled={updating || !policy.available[name]?.available}
              onChange={(event) =>
                update("custom", { [name]: event.target.checked })
              }
            />
          </label>
        ))}
      <p className="muted">
        Applying a diff to original host files always needs a separate scoped
        review. Workspace agent never grants host changes or publication.
      </p>
      <button
        type="button"
        className="secondary-button"
        disabled={!policy?.session_id || updating}
        onClick={revoke}
      >
        Revoke session grants
      </button>
    </section>
  );
}
export function ApprovalCards({
  actions,
  decide,
  execute,
  requestHost,
}: {
  actions: Action[];
  decide: (action: Action, decision: string) => void;
  execute: (action: Action) => void;
  requestHost: (ticket: string) => void;
}) {
  return (
    <div className="approval-list">
      {actions.map((action) => (
        <article
          className="approval-card"
          key={action.id}
          data-state={action.state}
        >
          <div className="approval-heading">
            <strong>{action.summary || action.type}</strong>
            <span>
              {action.type === "guest.submit" && action.state === "completed"
                ? "Guest admitted"
                : action.state.replaceAll("_", " ")}
            </span>
          </div>
          <p>{action.resource}</p>
          <p className="action-consequence">
            {
              {
                "workspace.read": "Read the selected app workspace file.",
                "workspace.write":
                  "Edit this app-owned workspace copy. Original host files stay unchanged.",
                "search.wikipedia":
                  "Send this query to Wikipedia and retrieve public source text.",
                "guest.submit":
                  "Run the supported task in a qualified disposable guest. No host shell fallback.",
                "host.apply":
                  "Apply this reviewed diff to the original host file. This changes the original file.",
              }[action.type]
            }
          </p>
          {action.state === "pending" && (
            <small>
              Approval expires at{" "}
              {new Date(action.expires * 1000).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
              . Session approval covers only this action and resource scope.
            </small>
          )}
          <details>
            <summary>Normalized action</summary>
            <pre>{JSON.stringify(action.action, null, 2)}</pre>
          </details>
          {action.diff && <pre className="action-diff">{action.diff}</pre>}
          {action.state === "pending" && (
            <div className="approval-buttons">
              <button onClick={() => decide(action, "allow_once")}>
                Allow once
              </button>
              <button onClick={() => decide(action, "session")}>
                Allow for this session
              </button>
              <button onClick={() => decide(action, "deny")}>Deny</button>
            </div>
          )}
          {action.state === "allowed" && (
            <button onClick={() => execute(action)}>Run approved action</button>
          )}
          {action.result != null && (
            <details>
              <summary>Result</summary>
              <pre>{JSON.stringify(action.result, null, 2)}</pre>
            </details>
          )}
          {action.type === "guest.submit" &&
            action.state === "completed" &&
            !!(action.result as { job?: { id: string } } | undefined)?.job
              ?.id && (
              <GuestJob
                id={(action.result as { job: { id: string } }).job.id}
                requestHost={requestHost}
              />
            )}{" "}
          {action.error && <p role="alert">{action.error}</p>}
        </article>
      ))}
    </div>
  );
}

type GuestRecord = {
  id: string;
  state: string;
  reason?: string;
  answer?: string;
  validation?: unknown;
  events?: { sequence: number; detail: string }[];
};
function GuestJob({
  id,
  requestHost,
}: {
  id: string;
  requestHost: (ticket: string) => void;
}) {
  const [record, setRecord] = useState<GuestRecord | null>(null);
  const [error, setError] = useState("");
  const [review, setReview] = useState<{
    diff: string;
    validation: unknown;
    review_ticket: string | null;
    apply_scope: string;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const update = async () => {
      try {
        const latest = await rpc<GuestRecord>("job.read", { job_id: id });
        if (!alive) return;
        setRecord(latest);
        setError("");
        failures = 0;
        if (
          ["review_ready", "failed", "cancelled", "blocked"].includes(
            latest.state,
          )
        )
          return;
      } catch (failure) {
        if (!alive) return;
        setError(
          failure instanceof Error
            ? failure.message
            : "Guest status could not be read",
        );
        if (++failures >= 3) return;
      }
      if (alive) timer = setTimeout(update, 3000);
    };
    update();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [id, retry]);
  async function prepare() {
    try {
      setReview(await rpc("patch.prepare", { job_id: id }));
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Diff review unavailable",
      );
    }
  }
  return (
    <section className="guest-result">
      <h4>
        Guest task · {record?.state.replaceAll("_", " ") ?? "Reading status"}
      </h4>
      {record?.reason && <p>{record.reason}</p>}
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => setRetry((value) => value + 1)}>
            Check status
          </button>
        </p>
      )}
      {record?.answer && <pre>{record.answer}</pre>}
      {record?.events?.map((event) => (
        <p key={event.sequence}>{event.detail}</p>
      ))}
      {!!record?.validation && (
        <details>
          <summary>Validation</summary>
          <pre>{JSON.stringify(record.validation, null, 2)}</pre>
        </details>
      )}
      {record &&
        !["review_ready", "failed", "cancelled", "blocked"].includes(
          record.state,
        ) && (
          <button
            onClick={async () => {
              try {
                await rpc("job.cancel", { job_id: id });
                setRetry((value) => value + 1);
              } catch (failure) {
                setError(
                  failure instanceof Error
                    ? failure.message
                    : "Guest cancellation unavailable",
                );
              }
            }}
          >
            Cancel owned guest task
          </button>
        )}
      {record?.state === "review_ready" && (
        <button onClick={prepare}>Review changes</button>
      )}
      {review && (
        <div className="host-diff-review">
          <h4>Original-file review</h4>
          <pre>{review.diff || "No changes"}</pre>
          <p>{review.apply_scope}</p>
          {review.review_ticket ? (
            <button onClick={() => requestHost(review.review_ticket!)}>
              Request separate approval for original file
            </button>
          ) : (
            <p>
              Applying these results to original host files is unavailable. No
              original file has changed.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
