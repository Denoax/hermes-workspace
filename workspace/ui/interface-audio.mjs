// Kenney Interface Sounds, CC0; natural-rate softened samples. Provenance in sounds/.
export function soundChoice(action) { return action === 'close-dialog' || action === 'close-files' ? 'soft-close' : 'soft-press'; }
export function soundEligible(event, button) { return event.isTrusted === true && !!button && !button.disabled && button.getAttribute('aria-disabled') !== 'true'; }
export function installInterfaceAudio() {
    let enabled = true, volume = .12, active;
    try {
        enabled = localStorage.getItem('hermes-ui:sounds') !== 'off';
    }
    catch { }
    const toggle = document.getElementById('sound-toggle');
    const paint = () => { toggle.setAttribute('aria-pressed', String(enabled)); toggle.title = enabled ? 'Mute interface sounds' : 'Enable interface sounds'; toggle.setAttribute('aria-label', toggle.title); toggle.dataset.sound = enabled ? 'on' : 'off'; };
    const clips = new Map();
    document.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!soundEligible(event, button))
            return;
        if (button === toggle) {
            enabled = !enabled;
            try {
                localStorage.setItem('hermes-ui:sounds', enabled ? 'on' : 'off');
            }
            catch { }
            if (!enabled)
                active?.pause();
            paint();
            return;
        }
        if (!enabled || document.hidden)
            return;
        const name = soundChoice(button.dataset.action);
        if (!clips.has(name))
            clips.set(name, new Audio('/sounds/' + name + '.wav'));
        active?.pause();
        active = clips.get(name);
        active.currentTime = 0;
        active.volume = volume;
        active.play().catch(() => { toggle.dataset.audioState = 'playback-unavailable'; });
    }, { capture: true });
    document.addEventListener('visibilitychange', () => { if (document.hidden)
        active?.pause(); });
    paint();
    return { setVolume(value) { volume = Math.max(0, Math.min(1, value)); }, setEnabled(value) { enabled = value; try {
            localStorage.setItem('hermes-ui:sounds', enabled ? 'on' : 'off');
        }
        catch { } if (!enabled)
            active?.pause(); paint(); } };
}
