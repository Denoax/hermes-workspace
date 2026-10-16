import { useEffect, useRef, useState } from "react";
import { rpc } from "../api";

type Preview = { ticket: string; files: string[]; bytes: number };
type Owner = { project: string | null; visible: boolean; epoch: number };
type View = {
  owner: Owner;
  preview: Preview | null;
  pending: "choosing" | "copying" | null;
  error: string | null;
};
const detail = (error: unknown) => error instanceof Error ? error.message : String(error);

/** The native chooser cannot be cancelled here. Its replies belong only to the
 * project and dialog opening that requested them, never a later selection. */
export function useFolderImport(project: string | null, visible: boolean,
  onImported: (files: string[]) => void) {
  const owner = useRef<Owner>({ project, visible, epoch: 0 });
  if (owner.current.project !== project || owner.current.visible !== visible)
    owner.current = { project, visible, epoch: owner.current.epoch + 1 };
  const state = useRef<View | null>(null), alive = useRef(true);
  const [view, setView] = useState<View | null>(null);
  function owns(token: Owner) { return alive.current && token.visible && owner.current === token; }
  function publish(next: View) { state.current = next; setView(next); }
  function empty(token: Owner): View { return { owner: token, preview: null, pending: null, error: null }; }
  function reset() {
    owner.current = { ...owner.current, epoch: owner.current.epoch + 1 };
    publish(empty(owner.current));
  }
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  async function choose() {
    const token = owner.current;
    if (!owns(token) || (state.current?.owner === token && state.current.pending)) return;
    if (!token.project) {
      publish({ ...empty(token), error: "Create or select a project before importing a workspace copy." });
      return;
    }
    publish({ ...empty(token), pending: "choosing" });
    try {
      const preview = await rpc<Preview & { cancelled?: boolean }>("workspace.import.request", { project_id: token.project });
      if (owns(token)) publish({ ...empty(token), preview: preview.cancelled ? null : preview });
    } catch (error) {
      if (owns(token)) publish({ ...empty(token), error: "Could not choose an import folder: " + detail(error) });
    }
  }
  async function commit() {
    const token = owner.current, current = state.current;
    if (!owns(token) || !token.project || current?.owner !== token || !current.preview || current.pending) return;
    // Copy the reviewed ticket before awaiting. Changing the sidebar cannot
    // redirect this admitted operation to a different project.
    const preview = current.preview;
    publish({ ...current, pending: "copying", error: null });
    let copied = false;
    try {
      await rpc("workspace.import.commit", { project_id: token.project, ticket: preview.ticket });
      copied = true;
      if (!owns(token)) return;
      publish({ ...empty(token), pending: "copying" });
      const result = await rpc<{ files: string[] }>("workspace.files", { project_id: token.project });
      if (!owns(token)) return;
      publish(empty(token));
      onImported(result.files);
    } catch (error) {
      if (owns(token)) publish({ ...empty(token), preview: copied ? null : preview,
        error: (copied ? "Files were copied, but the project file list could not be loaded: " : "Could not copy the reviewed files: ") + detail(error) });
    }
  }
  const current = view?.owner === owner.current && visible ? view : empty(owner.current);
  return { preview: current.preview, pending: current.pending, error: current.error, choose, commit, reset };
}
