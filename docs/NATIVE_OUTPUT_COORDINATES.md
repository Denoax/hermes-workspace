# Native coordinates and chooser observation

Hyprland and XWayland can expose the same named outputs at different origins.
On this PC, read-only metadata measured HDMI-A-1 at compositor x0/X11 x3840,
HDMI-A-5 at compositor x3840/X11 x0, and DP-4 at x1920 in both protocols.
The former equal-origin assumption caused stale native events and prevented
strict bounds attestation on the outer monitors.

`workspace/native_coordinates.py` matches output names and equal coordinate
units using only `hyprctl monitors -j` and `xrandr --query --current`. Native test
input translates its XTEST point; capture/chooser parent discovery translates
expected bounds before the same XRes/profile/class/visibility checks. Layout
changes during input or attestation fail closed. Unknown outputs or unequal
units are refused; mixed-scale physical coverage remains unverified. No monitor
settings, screen lock, global browser options or permissions are changed.

The unassisted chooser observer distinguishes its Hermes-parented window from
KDE completion popups. When the compositor activates a completion surface,
actual X input focus must retain the chooser's XRes PID and a bounded parent/
transient ancestry to that exact chooser. It never focuses or floats a chooser.
The original25-second phase and native120-second helper budgets remain intact.

The actual three-phase run passed cancel, preview-cancel and reviewed copy.
Both harmless files matched the expected snapshot and the original source stayed
unchanged. Earlier calibration, ambiguity and focus failures remain evidence.
This is native synthesized input and scoped technical verification, not physical
input, uninterrupted motion review or human visual approval.

The installed X.Org RandR manual documents read-only XWayland configuration
reporting: https://man.archlinux.org/man/xrandr.1.en.
