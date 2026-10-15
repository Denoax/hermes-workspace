import { mountIcons, icon } from './icons.mjs';
import { installPortfolioNav } from './portfolio-nav.mjs';
import { revealPane, cancelPaneMotion, dismissPane, refreshPane, positionPane } from './pane-motion.mjs';
import { installInterfaceAudio } from './interface-audio.mjs';
import { installPortfolioSettings } from './portfolio-settings.mjs';
const $ = id => document.getElementById(id);
const terminal = new Set(['review_ready', 'cancelled', 'failed', 'blocked']);
let csrf = '', project = null, session = null, snapshot = null, file = null, job = null;
let projects = [], sessions = [], filePaths = [], lastStatus = null, jobState = null;
let connected = false, polling = false, submitting = false, navigating = false;
let actionError = null;
let navigationQueue = Promise.resolve();
let viewQueue = Promise.resolve(), saveTimer, editorTimer, noticeTimer, inputAction;
const dialogFocus = new WeakMap();
mountIcons();
const selectNav = installPortfolioNav();
const audio = installInterfaceAudio();
const portfolioSettings = installPortfolioSettings(audio, () => { applyAppearance(); persistView(); });
document.documentElement.dataset.input = 'pointer';
document.addEventListener('pointerdown', () => { document.documentElement.dataset.input = 'pointer'; }, {capture:true});
document.addEventListener('keydown', event => { if (['Tab','Enter','Escape'].includes(event.key) || event.key.startsWith('Arrow')) document.documentElement.dataset.input = 'keyboard'; }, {capture:true});

function notice(text) {
  clearTimeout(noticeTimer);
  $('notice').textContent = text;
  $('notice').hidden = false;
  noticeTimer = setTimeout(() => $('notice').hidden = true, 7000);
}
function failure(error, target = 'composer-state') { if (target === 'composer-state') actionError = error.message; const node = $(target); node.textContent = error.message; node.hidden = false; node.classList.remove('sr-only'); }
function openDialog(dialog, trigger = document.activeElement, modal = innerWidth < 820 || dialog.id === 'input-dialog') {
  const parent = trigger?.closest?.('dialog');
  if (parent && parent !== dialog) trigger = dialogFocus.get(parent) || $('project-label').closest('button');
  // Dismiss the previous surface before opening another; native dialog owns focus trapping.
  document.querySelectorAll('dialog[open]').forEach(d => { if (d !== dialog) closeDialog(d); });
  dialogFocus.set(dialog, trigger);
  if (!dialog.open) modal ? dialog.showModal() : dialog.show();
  revealPane(dialog, trigger, $('motion').value === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches);
  selectNav(dialog.id);
}
function closeDialog(dialog) {
  if (!dialog.open) return;
  dismissPane(dialog);
  dialog.close();
  selectNav(null);
  const trigger = dialogFocus.get(dialog);
  if (trigger?.isConnected && trigger.getClientRects().length) trigger.focus({preventScroll:true});
}
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab' || !dialog.matches(':modal')) return;
    const controls = [...dialog.querySelectorAll('button:not(:disabled),input,select,textarea,[href],[tabindex]')]
      .filter(node => node.tabIndex >= 0 && node.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  });
  dialog.addEventListener('cancel', e => { e.preventDefault(); closeDialog(dialog); });
  dialog.addEventListener('close', () => {
    if (dialog.id === 'files-panel') {
      $('app').classList.remove('files-open'); $('files-toggle').setAttribute('aria-expanded', 'false');
      persistView();
    }
  });
});
async function bootstrap() {
  const response = await fetch('/hermes-workspace/api/bootstrap');
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Open with the Hermes launcher');
  csrf = data.csrf;
}
async function rpc(method, fields = {}, retry = true, rateRetry = true) {
  const response = await fetch('/hermes-workspace/api/rpc', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Hermes-CSRF': csrf },
    body: JSON.stringify({ version: 1, method, fields })
  });
  const data = await response.json();
  if (response.status === 403 && data.error === 'session_or_CSRF_denied' && retry) {
    await bootstrap(); return rpc(method, fields, false, rateRetry);
  }
  if (response.status === 429 && rateRetry) {
    // The server denies these requests before dispatch, so one bounded retry is safe.
    await new Promise(resolve => setTimeout(resolve, 1100));
    return rpc(method, fields, retry, false);
  }
  if (!response.ok) {
    const messages = {file_drift: 'File changed since review. Reopen the file before saving.', rate_limit: 'Too many requests. Try again in a moment.', path_outside_workspace: 'Choose a relative path inside this project.', import_requires_empty_project: 'Import into an empty project.', job_not_ready_for_review: 'The job is not ready for review.'};
    throw Error(messages[data.error] || data.error || 'Request failed');
  }
  return data.result;
}
function viewState() {
  const text = $('file-text').value;
  return { project_id: project?.id || null, session_id: session?.id || null,
    file_path: file?.path || null,
    editor: file && new TextEncoder().encode(text).length <= 32768 ? { text, sha256: file.sha256 } : null,
    files_open: $('files-panel').open, arm: $('arm').value, task_kind: $('task-kind').value,
    theme: $('theme').value, motion: $('motion').value };
}
function persistView() {
  if (!csrf) return Promise.resolve();
  const state = viewState();
  viewQueue = viewQueue.catch(() => {}).then(() => rpc('view.write', { state }));
  viewQueue.catch(e => failure(e));
  return viewQueue;
}
async function saveDraft() {
  clearTimeout(saveTimer);
  if (session) await rpc('draft.write', { session_id: session.id, text: $('prompt').value, mode: $('task-kind').value });
}
function applyAppearance() {
  // Swap semantic ink/surfaces together; independent CSS color interpolation
  // otherwise crosses through unreadable grey text on grey selected rows.
  document.documentElement.dataset.themeChanging = 'true';
  portfolioSettings.sync();
  document.documentElement.dataset.theme = $('theme').value;
  document.documentElement.dataset.motion = $('motion').value;
  getComputedStyle(document.documentElement).color;
  requestAnimationFrame(() => delete document.documentElement.dataset.themeChanging);
  document.querySelectorAll('dialog[open]').forEach(d => refreshPane(d, dialogFocus.get(d)));
}
function row(text, callback, selected, id, index, caption) {
  const button = document.createElement('button');
  button.className = index === undefined ? 'session-row' : 'project-row';
  button.dataset.id = id; button.setAttribute('aria-current', String(selected));
  if (index !== undefined) { const number = document.createElement('span'); number.className = 'row-index'; number.textContent = String(index + 1).padStart(2, '0'); button.append(number); }
  const label = document.createElement('span'); label.className = 'row-title'; label.textContent = text;
  button.title = text;
  const copy = document.createElement('span'); copy.className = 'row-copy'; copy.append(label);
  if (caption) { const detail = document.createElement('span'); detail.className = 'row-caption'; detail.textContent = caption; copy.append(detail); }
  button.append(copy);
  button.onclick = () => callback().catch(e => failure(e));
  return button;
}
function emptyList(text) { const p = document.createElement('p'); p.className = 'quiet'; p.textContent = text; return p; }
function renderLists() {
  $('projects').replaceChildren(...(projects.length ? projects.map((p, i) => row(p.label, () => chooseProject(p), p.id === project?.id, p.id, i, sessions.filter(s => s.project === p.id).length + ' conversations')) : [emptyList('No projects yet.')]));
  const list = sessions.filter(s => s.project === project?.id);
  for (const id of ['sessions', 'mobile-sessions']) $(''+id).replaceChildren(...(list.length ? list.map(s => row(s.title || 'New conversation', () => chooseSession(s), s.id === session?.id, s.id)) : [emptyList('No conversations yet.')]));
  $('rename').disabled = !session;
  renderProjectResults();
}
function renderProjectResults() {
  const query = $('project-search').value.toLocaleLowerCase();
  const found = projects.filter(p => p.label.toLocaleLowerCase().includes(query));
  $('project-results').replaceChildren(...(found.length ? found.map((p, i) => row(p.label, async () => { closeDialog($('project-dialog')); await chooseProject(p); }, p.id === project?.id, p.id, i)) : [emptyList('No projects found.')]));
}
async function refreshLists() { [projects, sessions] = await Promise.all([rpc('workspace.list'), rpc('session.list')]); renderLists(); }
function resetJob() {
  job = null; jobState = null; $('diff').textContent = ''; $('apply').hidden = true;
  $('view-diff').disabled = true; $('validation').textContent = 'Select a completed job to review its changes.';
}
function chooseProject(p, restore = false) {
  navigationQueue = navigationQueue.catch(() => {}).then(() => loadProject(p, restore));
  return navigationQueue;
}
async function loadProject(p, restore) {
  navigating = true; updateControls();
  try {
    if (!restore && file && $('file-text').value !== file.original && !confirm('Discard this unsaved file draft?')) return;
    if (!restore) await saveDraft();
    project = p; session = null; file = null; resetJob();
    $('prompt').value = ''; $('project-label').textContent = p.label; $('file-preview').hidden = true;
    await files(); renderLists(); emptyView(); updateControls();
    if (!restore) await persistView();
  } finally { navigating = false; updateControls(); }
}
function chooseSession(s, restore = false) {
  navigationQueue = navigationQueue.catch(() => {}).then(() => loadSession(s, restore));
  return navigationQueue;
}
async function loadSession(s, restore) {
  navigating = true; updateControls();
  try {
    if (!restore) await saveDraft();
    if (project?.id !== s.project) {
      project = projects.find(p => p.id === s.project); file = null; $('file-preview').hidden = true;
      $('project-label').textContent = project.label; await files();
    }
    session = s; resetJob(); $('arm').value = s.arm;
    const [draft, jobs] = await Promise.all([rpc('draft.read', { session_id: s.id }), rpc('session.jobs', { session_id: s.id })]);
    $('prompt').value = draft.text; $('task-kind').value = draft.mode;
    job = jobs.at(-1)?.id || null;
    renderLists(); await history(); await poll(); updateControls();
    if (!restore) await persistView();
  } finally { navigating = false; updateControls(); }
}
function emptyView() {
  const empty = document.createElement('section'); empty.className = 'empty-state';
  if (!project || !session) {
    const button = document.createElement('button'); button.className = 'primary';
    button.textContent = project ? 'New conversation' : 'Open project';
    button.dataset.action = project ? 'new-session' : 'projects'; empty.append(button);
  }
  $('messages').replaceChildren(empty);
}
function appendInline(parent, text) {
  // Only registered file links and absolute HTTP(S) URLs become links. HTML stays literal.
  const pattern = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(offset, match.index)));
    const target = match[2];
    if (filePaths.includes(target)) {
      const b = document.createElement('button'); b.className = 'file-link'; b.textContent = match[1];
      b.onclick = () => readFile(target).then(() => openFiles()).catch(e => failure(e)); parent.append(b);
    } else if (/^https?:\/\//i.test(target)) {
      const a = document.createElement('a'); a.textContent = match[1]; a.href = target; a.target = '_blank'; a.rel = 'noopener noreferrer'; parent.append(a);
    } else parent.append(document.createTextNode(match[0]));
    offset = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(offset)));
}
function message(m) {
  const article = document.createElement('article'); article.className = 'message ' + m.role;
  if (m.role === 'event') {
    const disclosure = document.createElement('details'); const summary = document.createElement('summary');
    summary.textContent = m.text.split('\n')[0].slice(0, 100); const body = document.createElement('pre'); body.textContent = m.text;
    disclosure.append(summary, body); article.append(disclosure); return article;
  }
  const role = document.createElement('span'); role.className = 'role sr-only'; role.textContent = m.role === 'user' ? 'You' : 'Hermes'; article.append(role);
  const parts = m.text.split(/```[^\n]*\n([\s\S]*?)```/g);
  parts.forEach((text, i) => {
    if (i % 2) { const pre = document.createElement('pre'); const code = document.createElement('code'); code.textContent = text; pre.append(code); article.append(pre); }
    else if (text) { const p = document.createElement('p'); appendInline(p, text); article.append(p); }
  });
  return article;
}
async function history() {
  if (!session) return emptyView();
  const id = session.id; const data = await rpc('session.history', { session_id: id });
  if (id !== session?.id) return;
  if (!data.length) return emptyView();
  const bottom = $('messages').scrollHeight - $('messages').scrollTop - $('messages').clientHeight < 80;
  $('messages').replaceChildren(...data.map(message)); if (bottom) $('messages').scrollTop = $('messages').scrollHeight;
}
async function files() {
  if (!project) return;
  const id = project.id; const data = await rpc('workspace.files', { project_id: id });
  if (id !== project?.id) return;
  snapshot = data.snapshot_sha256; filePaths = data.files; renderTree(data.files);
  $('no-files').hidden = !!data.files.length; $('no-files').textContent = 'No files in this project. Add a file or import a folder.';
}
function renderTree(paths) {
  const focusedPath = $('tree').contains(document.activeElement) ? document.activeElement.dataset.path : null;
  const nested = paths.some(p => p.includes('/')); $('tree').replaceChildren(); $('tree').setAttribute('role', nested ? 'tree' : 'list');
  let groupCounter = 0;
  const root = {};
  for (const path of paths) { let node = root; const parts = path.split('/'); parts.forEach((name, i) => { node[name] ||= { children: {}, path: i === parts.length - 1 ? path : null }; node = node[name].children; }); }
  function branch(nodes, parent) {
    for (const [name, node] of Object.entries(nodes)) {
      const folder = !node.path; const wrapper = document.createElement('div'); wrapper.setAttribute('role', nested ? 'none' : 'listitem');
      const b = document.createElement('button'); b.className = 'file-row'; const label = document.createElement('span'); label.textContent = name; b.append(icon(folder ? 'folder' : 'file'), label); b.title = node.path || name;
      if (nested) b.setAttribute('role', 'treeitem'); b.setAttribute(nested ? 'aria-selected' : 'aria-current', String(node.path === file?.path));
      b.dataset.path = node.path || ''; if (folder) b.setAttribute('aria-expanded', 'true');
      let group;
      b.onclick = () => {
        if (folder) { group.hidden = !group.hidden; b.setAttribute('aria-expanded', String(!group.hidden)); }
        else readFile(node.path).catch(e => failure(e, 'file-error'));
      };
      wrapper.append(b); parent.append(wrapper);
      if (folder) { group = document.createElement('div'); group.id = 'file-group-' + (++groupCounter); group.setAttribute('role', 'group'); b.setAttribute('aria-owns', group.id); wrapper.append(group); branch(node.children, group); }
    }
  }
  branch(root, $('tree'));
  const buttons = [...$('tree').querySelectorAll('button')];
  const entry = buttons.find(b => b.dataset.path === (focusedPath || file?.path)) || buttons[0];
  buttons.forEach(b => b.tabIndex = b === entry ? 0 : -1);
  if (focusedPath) entry?.focus();
  $('tree').onkeydown = event => {
    const visible = buttons.filter(b => b.getClientRects().length); const current = document.activeElement; const i = visible.indexOf(current); let target;
    if (event.key === 'ArrowDown') target = visible[Math.min(i + 1, visible.length - 1)];
    if (event.key === 'ArrowUp') target = visible[Math.max(i - 1, 0)];
    if (event.key === 'Home') target = visible[0]; if (event.key === 'End') target = visible.at(-1);
    if (event.key === 'ArrowRight' && current.hasAttribute('aria-expanded')) { if (current.getAttribute('aria-expanded') === 'false') current.click(); else target = visible[i + 1]; }
    if (event.key === 'ArrowLeft') { if (current.getAttribute('aria-expanded') === 'true') current.click(); else target = current.parentElement.parentElement.closest('[role=none]')?.querySelector('button'); }
    if (event.key.length === 1 && /\S/.test(event.key)) target = [...visible.slice(i + 1), ...visible.slice(0, i + 1)].find(b => b.textContent.replace(/^⌄ /, '').toLowerCase().startsWith(event.key.toLowerCase()));
    if (target) { buttons.forEach(b => b.tabIndex = -1); target.tabIndex = 0; target.focus(); }
    if (target || event.key.startsWith('Arrow')) event.preventDefault();
  };
}
async function readFile(path, restore = null) {
  if (!restore && file && $('file-text').value !== file.original && !confirm('Discard this unsaved file draft?')) return;
  const id = project.id; const data = await rpc('workspace.file.read', { project_id: id, relative_path: path });
  if (id !== project?.id) return;
  file = { path, sha256: restore?.sha256 || data.sha256, original: data.text }; $('file-label').textContent = path;
  $('file-text').value = restore?.text ?? data.text; $('file-preview').hidden = false; $('file-error').hidden = true;
  $('file-state').textContent = restore && restore.text !== data.text ? 'Unsaved draft' : 'Workspace copy';
  renderTree(filePaths); await persistView();
}
function openFiles(trigger = $('files-toggle')) {
  $('app').classList.add('files-open');
  openDialog($('files-panel'), trigger, innerWidth <= 1200); $('files-toggle').setAttribute('aria-expanded', 'true'); persistView();
}
function changeTab(changes) {
  $('file-content').hidden = changes; $('changes-content').hidden = !changes;
  $('files-tab').setAttribute('aria-selected', String(!changes)); $('changes-tab').setAttribute('aria-selected', String(changes));
}
function updateControls(error = null) {
  const active = lastStatus?.native?.observed_facts?.inference_window_active === true;
  const busy = submitting || (job && jobState && !terminal.has(jobState.state));
  let reason = error || (navigating ? 'Opening conversation…' : !connected ? 'Connection lost. Reconnecting…' : !project ? 'Choose a project to begin.' : !session ? 'Create a conversation to begin.' : lastStatus?.tool_profile !== 'guest_scoped_v1' ? 'Native setup needed. Open Details for the prepared command.' : !active ? 'Start lab to send this request.' : busy ? (jobState?.state === 'recovery_pending' ? 'Recovery pending. Stop remains available.' : 'Job ' + (jobState?.state || 'starting') + '.') : '');
  if (!reason && !snapshot) reason = 'Stage at most 16 text files and 32 KiB to send.';
  $('composer-state').textContent = error || actionError || reason;
  $('composer-state').classList.toggle('sr-only', !(error || actionError));
  $('start-window').textContent = active ? 'Lab open' : lastStatus?.tool_profile !== 'guest_scoped_v1' ? 'Set up lab' : 'Start lab';
  $('send').disabled = !!reason || !$('prompt').value.trim(); $('send').title = reason || 'Send message';
  $('stop').disabled = !job || (jobState && terminal.has(jobState.state)); $('stop').title = $('stop').disabled ? 'No active job' : 'Cancel the current job';
  $('start-window').disabled = active || !connected; $('start-window').title = active ? 'The current window is already open' : 'Show the explicit native window command';
  $('new-file').disabled = $('import').disabled = $('open-folder').disabled = !project;
}
async function poll() {
  if (!csrf || polling) return;
  polling = true;
  try {
    lastStatus = await rpc('status.read'); connected = true;
    const native = lastStatus.native; const active = native.observed_facts?.inference_window_active === true;
    $('connection').textContent = active ? 'Lab open' + (native.remaining_seconds != null ? ' · ' + Math.ceil(native.remaining_seconds / 60) + ' min' : '') : 'Connected';
    if (job) {
      const id = job; const state = await rpc('job.read', { job_id: id });
      if (id === job) {
        if (jobState?.state !== state.state) { jobState = state; await history(); }
        else jobState = state;
        $('view-diff').disabled = state.state !== 'review_ready';
        if (state.state === 'failed' || state.state === 'blocked') $('validation').textContent = state.reason || state.state;
      }
    }
    updateControls();
  } catch (e) { connected = false; $('connection').textContent = 'Connection lost'; updateControls('Connection lost. ' + e.message); }
  finally { polling = false; }
}
function requestInput(title, label, value, max, submitLabel, action) {
  $('input-title').textContent = title; $('input-label').textContent = label; $('input-value').value = value;
  $('input-value').maxLength = max; $('input-error').hidden = true; $('input-submit').textContent = submitLabel; inputAction = action;
  openDialog($('input-dialog')); $('input-value').focus();
}
$('input-form').onsubmit = async e => {
  e.preventDefault(); $('input-submit').disabled = true;
  try { await inputAction($('input-value').value); closeDialog($('input-dialog')); }
  catch (error) { failure(error, 'input-error'); }
  finally { $('input-submit').disabled = false; }
};
async function newSession() {
  if (!project) { openDialog($('project-dialog')); return; }
  const mode = $('task-kind').value;
  const s = await rpc('session.create', { project_id: project.id, arm: $('arm').value });
  await refreshLists(); closeDialog($('project-dialog')); await chooseSession(s); $('task-kind').value = mode; await saveDraft(); await persistView(); $('prompt').focus();
}
function showDetails(title = 'Details', text = null) {
  $('details-title').textContent = title; $('details-summary').replaceChildren();
  if (text === null) {
    for (const content of [
      lastStatus?.normal_model_available ? 'Homebrew: normal Qwen available.' : 'Homebrew: normal Qwen is unavailable or paused.',
      'Lab: ' + (lastStatus?.tool_profile === 'guest_scoped_v1' ? 'Guest tools installed.' : 'Native setup needed.'),
      session ? 'Conversation model: ' + (session.arm === 'normal' ? 'Normal Qwen' : 'Abliterated Qwen') + '. Mode: ' + $('task-kind').selectedOptions[0].textContent + '.' : 'No conversation selected.',
      ({chat: 'Chat uses scoped read-only file tools.', python: 'Python contract: program.py reads a JSON integer list and clamps each value to 0..100.', cpp: 'C++ contract: solution.cpp reads integers and prints their squares.'})[$('task-kind').value],
      'Historical paired smoke: Normal 2/3, Abliterated 2/3. B08 failed. The larger matrix remains withheld.'
    ]) { const p = document.createElement('p'); p.textContent = content; $('details-summary').append(p); }
    const p = document.createElement('p'); p.className = 'quiet'; p.textContent = 'Read at ' + new Date().toLocaleString() + '. Historical results are separate from current readiness.'; $('details-summary').append(p);
    text = 'No-GPU native setup (requires authentication in your terminal):\nsh /home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1/native/run_workspace_setup.sh\n\n' + JSON.stringify(lastStatus, null, 2);
  }
  $('details-text').textContent = text; openDialog($('details'));
}
const actions = {
  projects: () => { renderProjectResults(); openDialog($('project-dialog')); $('project-search').focus(); },
  'new-project': () => requestInput('New project', 'Project name', '', 80, 'Create', async label => { const p = await rpc('workspace.create', { label }); await refreshLists(); await chooseProject(p); }),
  'new-session': newSession,
  rename: () => { if (session) requestInput('Rename', 'Conversation title', sessions.find(s => s.id === session.id)?.title || '', 80, 'Save', async title => { await rpc('session.rename', { session_id: session.id, title }); await refreshLists(); }); },
  appearance: () => openDialog($('appearance')),
  'close-dialog': event => closeDialog(event.target.closest('dialog')),
  files: () => $('files-panel').open ? closeDialog($('files-panel')) : openFiles(),
  'close-files': () => closeDialog($('files-panel')),
  'files-tab': () => changeTab(false), 'changes-tab': () => changeTab(true),
  details: () => showDetails(),
  start: async () => { if (lastStatus?.tool_profile !== 'guest_scoped_v1') return showDetails('Set up lab'); const result = await rpc('window.request'); showDetails('Start lab', result.message + '\n\n' + result.command + '\n\nRun only after native setup and choosing a bounded window.'); },
  stop: async () => { if (job) { $('stop').textContent = 'Stopping'; try { await rpc('job.cancel', { job_id: job }); await poll(); } finally { $('stop').textContent = 'Stop'; } } },
  homebrew: async () => { await rpc('homebrew.open'); notice('Homebrew opened.'); },
  'open-folder': async () => { if (project) await rpc('workspace.open', { project_id: project.id }); },
  import: async () => { if (!project) return; const preview = await rpc('workspace.import.request', { project_id: project.id }); if (preview.cancelled) return; if (confirm(`Copy ${preview.files.length} reviewed text files (${preview.bytes} bytes)?\n\n${preview.files.slice(0, 15).join('\n')}\n\nSensitive metadata and dependencies are excluded. Original files stay in place.`)) { await rpc('workspace.import.commit', { project_id: project.id, ticket: preview.ticket }); await files(); } },
  'new-file': () => { if (project) requestInput('New file', 'Relative filename', '', 512, 'Create', async path => { await rpc('workspace.file.write', { project_id: project.id, relative_path: path, text: '', expected_sha256: null }); await files(); await readFile(path); openFiles(); }); },
  'save-file': async () => { if (!project || !file) return; const data = await rpc('workspace.file.write', { project_id: project.id, relative_path: file.path, text: $('file-text').value, expected_sha256: file.sha256 }); file.sha256 = data.sha256; file.original = $('file-text').value; $('file-state').textContent = 'Workspace copy'; $('file-error').hidden = true; await files(); await persistView(); notice('Saved the workspace copy.'); },
  diff: async () => { if (!job) return; const data = await rpc('patch.prepare', { job_id: job }); $('diff').textContent = data.diff || 'No file changes.'; $('validation').textContent = data.validation?.passed ? 'Independent validation passed.' : 'Validation did not pass.'; $('apply').hidden = !data.review_ticket; $('apply').dataset.ticket = data.review_ticket || ''; changeTab(true); },
  apply: async () => { if (confirm('Apply only this reviewed change to the selected original project?')) { await rpc('patch.apply', { review_ticket: $('apply').dataset.ticket }); $('apply').hidden = true; notice('Applied the reviewed change.'); } }
};
document.addEventListener('click', e => {
  const button = e.target.closest('[data-action]'); if (!button || button.disabled) return;
  actionError = null;
  Promise.resolve().then(() => actions[button.dataset.action](e)).catch(error => failure(error, button.closest('#files-panel') ? 'file-error' : 'composer-state'));
});
$('composer').onsubmit = async event => {
  event.preventDefault(); if ($('send').disabled || submitting || !session || !project) return;
  actionError = null;
  const text = $('prompt').value.trim(); submitting = true; updateControls();
  try {
    await files(); const result = await rpc('job.submit', { session_id: session.id, client_job_id: crypto.randomUUID().replaceAll('-', ''), prompt: text, snapshot_sha256: snapshot, task_kind: $('task-kind').value });
    job = result.id; jobState = { state: result.state }; $('prompt').value = ''; await saveDraft(); await history(); await refreshLists(); await poll();
  } catch (e) { failure(e); } finally { submitting = false; updateControls(); }
};
$('prompt').oninput = () => { actionError = null; updateControls(); clearTimeout(saveTimer); saveTimer = setTimeout(() => saveDraft().catch(e => failure(e)), 350); };
$('prompt').onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $('composer').requestSubmit(); } };
$('task-kind').onchange = async () => { await saveDraft(); await persistView(); };
$('arm').onchange = async () => { try { if (project) await newSession(); else await persistView(); } catch (e) { if (session) $('arm').value = session.arm; failure(e); } };
$('file-text').oninput = () => { $('file-state').textContent = 'Unsaved draft'; clearTimeout(editorTimer); editorTimer = setTimeout(() => persistView(), 350); };
$('project-search').oninput = renderProjectResults;
$('context').onchange = async () => { if ($('context').value === 'homebrew') try { await actions.homebrew(); } catch (e) { failure(e); } finally { $('context').value = 'lab'; } };
for (const id of ['theme', 'motion']) $(id).onchange = () => { applyAppearance(); persistView(); };
for (const id of ['files-tab', 'changes-tab']) $(id).onkeydown = e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); const changes = id === 'files-tab'; changeTab(changes); $(changes ? 'changes-tab' : 'files-tab').focus(); } };
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); actions.projects(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') { e.preventDefault(); $('prompt').focus(); }
  if (e.key === 'Escape') {
    const nonmodal = [...document.querySelectorAll('dialog[open]')].at(-1);
    if (nonmodal) { e.preventDefault(); closeDialog(nonmodal); }
  }
});
document.addEventListener('pointerdown', event => {
  document.querySelectorAll('dialog[open]').forEach(dialog => {
    if (dialog.id === 'files-panel' || dialog.matches(':modal')) return;
    const trigger = dialogFocus.get(dialog);
    if (!dialog.contains(event.target) && !trigger?.contains?.(event.target)) closeDialog(dialog);
  });
});
let narrow = innerWidth <= 1200;
window.addEventListener('resize', () => {
  document.querySelectorAll('dialog[open]').forEach(dialog => { refreshPane(dialog, dialogFocus.get(dialog)); });
  const next = innerWidth <= 1200;
  if (next !== narrow && $('files-panel').open) { const trigger = dialogFocus.get($('files-panel')); $('files-panel').close(); openFiles(trigger); }
  narrow = next;
});
emptyView();
try {
  await Promise.all([document.fonts.load('500 14px "Portfolio Inter"'), document.fonts.load('16px Rubik')]);
  await bootstrap(); await refreshLists();
  const view = await rpc('view.read');
  if (view) {
    $('theme').value = view.theme; $('motion').value = view.motion; applyAppearance();
    const p = projects.find(p => p.id === view.project_id); if (p) await chooseProject(p, true);
    const s = sessions.find(s => s.id === view.session_id); if (s) await chooseSession(s, true);
    $('arm').value = session?.arm || view.arm; $('task-kind').value = view.task_kind;
    if (project && view.file_path) try { await readFile(view.file_path, view.editor); } catch (e) { failure(e, 'file-error'); }
    if (view.files_open) openFiles();
  }
  await poll(); setInterval(poll, 2000);
} catch (e) { $('connection').textContent = 'Open with Hermes'; updateControls(e.message); }
