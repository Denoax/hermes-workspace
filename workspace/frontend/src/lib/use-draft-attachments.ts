import { useEffect, useRef, useState } from "react";
import { rpc, type Attachment } from "../api";
import {
  attachmentIds,
  clearInvalidSelection,
  moveNewSelection,
  readSelection,
  replaceSelection,
  restoreMetadata,
  sameSelection,
  selectionKey,
  type AttachmentIssue,
  type DraftSelection,
} from "./draft-selection";
export type AttachmentToken = {
  scope: string | null;
  epoch: number;
  selection: DraftSelection;
};
type State = AttachmentToken & {
  items: Attachment[];
  issues: AttachmentIssue[];
  ready: boolean;
};
export function useDraftAttachments(scope: string | null, connected: boolean) {
  const owner = useRef({ scope, epoch: 0 });
  if (owner.current.scope !== scope)
    owner.current = { scope, epoch: owner.current.epoch + 1 };
  const state = useRef<State | null>(null),
    alive = useRef(true);
  const [view, setView] = useState<State | null>(null),
    [reload, setReload] = useState(0);
  function publish(next: State) {
    state.current = next;
    setView(next);
  }
  function owns(token: Pick<AttachmentToken, "scope" | "epoch">) {
    return (
      alive.current &&
      owner.current.scope === token.scope &&
      owner.current.epoch === token.epoch
    );
  }
  function capture(): AttachmentToken {
    const current = state.current;
    if (!current || !owns(current) || !current.ready)
      throw Error("Attachment draft is still loading.");
    if (current.issues.length)
      throw Error(
        "Resolve unavailable attachments before sending or adding files.",
      );
    return {
      scope: current.scope,
      epoch: current.epoch,
      selection: readSelection(localStorage, current.scope),
    };
  }
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (!connected) return;
    let current = true;
    const token = { ...owner.current };
    const restore = async () => {
      try {
        const selection = readSelection(localStorage, scope);
        publish({ ...token, selection, items: [], issues: [], ready: false });
        const result = await restoreMetadata(selection.ids, (id) =>
          rpc<Attachment>("attachment.metadata", { id }),
        );
        if (
          current &&
          owns(token) &&
          sameSelection(selection, readSelection(localStorage, scope))
        )
          publish({ ...token, selection, ...result, ready: true });
      } catch {
        if (current && owns(token))
          publish({
            ...token,
            selection: { version: 1, revision: "", ids: [] },
            items: [],
            issues: [
              {
                id: null,
                message:
                  "Saved attachment selection could not be restored. Clear the selection and attach the files again.",
              },
            ],
            ready: true,
          });
      }
    };
    void restore();
    const changed = (event: StorageEvent) => {
      if (event.key === selectionKey(scope)) setReload((value) => value + 1);
    };
    addEventListener("storage", changed);
    return () => {
      current = false;
      removeEventListener("storage", changed);
    };
  }, [scope, connected, reload]);
  async function verify(ids: string[]) {
    const result = await restoreMetadata(ids, (id) =>
      rpc<Attachment>("attachment.metadata", { id }),
    );
    if (result.issues.length) {
      const current = state.current;
      if (
        current &&
        owns(current) &&
        JSON.stringify(current.selection.ids) === JSON.stringify(ids)
      )
        publish({ ...current, ...result });
      throw Error(
        "An attachment is unavailable. Retry, or remove it and attach the file again.",
      );
    }
    return result.items;
  }
  function add(
    item: Attachment,
    token: AttachmentToken,
  ): { token: AttachmentToken; background: boolean } | null {
    if (!alive.current) return null;
    attachmentIds([item.id]);
    const ids = attachmentIds([
      ...token.selection.ids.filter((id) => id !== item.id),
      item.id,
    ]);
    const next = replaceSelection(
      localStorage,
      token.scope,
      token.selection,
      ids,
    );
    if (!next) return null;
    const nextToken = { ...token, selection: next },
      background = !owns(token);
    if (!background) {
      const current = state.current;
      if (
        current &&
        owns(current) &&
        sameSelection(current.selection, token.selection) &&
        !current.issues.length &&
        token.selection.ids.every((id) =>
          current.items.some((row) => row.id === id),
        )
      )
        publish({
          ...nextToken,
          items: [...current.items.filter((row) => row.id !== item.id), item],
          issues: [],
          ready: true,
        });
      else setReload((value) => value + 1);
    }
    return { token: nextToken, background };
  }
  function remove(id: string | null) {
    const current = state.current;
    if (!current || !owns(current)) return;
    const next =
      id === null
        ? clearInvalidSelection(localStorage, scope)
        : replaceSelection(
            localStorage,
            scope,
            current.selection,
            current.selection.ids.filter((value) => value !== id),
          );
    if (!next) {
      setReload((value) => value + 1);
      return;
    }
    publish({
      ...current,
      selection: next,
      items: id === null ? [] : current.items.filter((item) => item.id !== id),
      issues: current.issues.filter((issue) => issue.id !== id),
      ready: true,
    });
  }
  function clearAccepted(token: AttachmentToken): DraftSelection | null {
    const next = replaceSelection(
      localStorage,
      token.scope,
      token.selection,
      [],
    );
    if (!next) return null;
    const current = state.current;
    if (
      current &&
      owns(current) &&
      current.scope === token.scope &&
      sameSelection(current.selection, token.selection)
    )
      publish({
        ...current,
        selection: next,
        items: [],
        issues: [],
        ready: true,
      });
    return next;
  }
  function resetNew() {
    const next = clearInvalidSelection(localStorage, null);
    if (scope === null) {
      owner.current = { scope: null, epoch: owner.current.epoch + 1 };
      publish({
        ...owner.current,
        selection: next,
        items: [],
        issues: [],
        ready: true,
      });
    }
  }
  const visible = view && owns(view) ? view : null;
  return {
    items: visible?.items ?? [],
    issues: visible?.issues ?? [],
    ready: !!visible?.ready,
    capture,
    owns,
    add,
    remove,
    verify,
    clearAccepted,
    resetNew,
    addForScope: (item: Attachment, expected: string) => {
      if (owner.current.scope !== expected) return null;
      return add(item, {
        ...owner.current,
        selection: readSelection(localStorage, expected),
      });
    },
    migrateNew: (destination: string) =>
      moveNewSelection(localStorage, destination),
    retry: () => setReload((value) => value + 1),
  };
}
