/** Independently authored SVGs with one optical size/stroke family.
 * Reference: James McDonald's consistency principles in Raycast's original
 * redesign article. No Raycast icon asset or path was copied.
 */
export function UIIcon({ name }: { name: "more" | "search" | "folder" | "file" | "mic" | "sound" | "add" }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="ui-icon">
    {name === "more" ? <><circle cx="5" cy="12" r=".8" fill="currentColor" /><circle cx="12" cy="12" r=".8" fill="currentColor" /><circle cx="19" cy="12" r=".8" fill="currentColor" /></>
    : name === "search" ? <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5" /></>
    : name === "folder" ? <path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3Z" />
    : name === "file" ? <><path d="M6 3h8l4 4v14H6Z" /><path d="M14 3v5h4M9 12h6M9 16h6" /></>
    : name === "mic" ? <><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6" /></>
    : name === "sound" ? <><path d="m11 5-5 4H3v6h3l5 4Z" /><path className="sound-wave" d="M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14" /><path className="sound-mute" d="m16 9 5 6m0-6-5 6" /></>
    : <path d="M12 5v14M5 12h14" />}
  </svg>;
}
