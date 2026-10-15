const svg =
  '<svg class="buddy-body theme-buddy" viewBox="0 0 64 64" aria-hidden="true"><defs><radialGradient id="buddy-material" cx="52%" cy="47%" r="61%"><stop offset=".48" stop-color="var(--buddy-body)"/><stop offset=".80" stop-color="var(--buddy-body)"/><stop offset="1" stop-color="var(--buddy-rim)"/></radialGradient><radialGradient id="buddy-light" cx="28%" cy="9%" r="76%"><stop stop-color="white" stop-opacity=".19"/><stop offset=".48" stop-color="white" stop-opacity="0"/></radialGradient></defs><path fill="url(#buddy-material)" d="M32 4C49 3 60 15 60 31C61 47 48 57 32 57C15 58 4 48 4 33C3 18 15 5 32 4Z"/><path fill="url(#buddy-light)" d="M32 4C49 3 60 15 60 31C61 47 48 57 32 57C15 58 4 48 4 33C3 18 15 5 32 4Z"/><g class="buddy-face" fill="var(--buddy-face)"><g class="buddy-awake"><circle cx="26" cy="25" r="3.6"/><circle cx="39" cy="25" r="3.6"/></g><g class="buddy-cross" fill="none" stroke="var(--buddy-face)" stroke-width="1.6" stroke-linecap="round"><path d="M23 23L29 29M29 23L23 29M36 23L42 29M42 23L36 29"/></g><g class="buddy-smile" fill="none" stroke="var(--buddy-face)" stroke-width="1.6" stroke-linecap="round"><path d="M22 26Q26 22 30 26M35 26Q39 22 43 26"/></g></g></svg>';
export function Buddy({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  return (
    <button
      id="theme-buddy"
      className="theme-buddy-control"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={dark}
      onClick={toggle}
    >
      <span dangerouslySetInnerHTML={{ __html: svg }} />
    </button>
  );
}
