"""One unprivileged, parented directory chooser; no compositor intervention."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

CAPTION = "Select files to copy into Hermes Lab"
MAX_SECONDS = 120


def resolve_parent():
    # Keep the existing XRes/profile/class/bounds checks authoritative. In its
    # own process this resolver can use the supplied desktop environment and
    # temporary Xlib error handler without mutating the threaded HTTP runtime.
    from workspace.capture import owned_x11_window

    return owned_x11_window()


def choose_directory(deadline: float) -> dict[str, str]:
    if os.getuid() != 1000 or os.geteuid() != 1000:
        return {"status": "error", "code": "operator_required"}
    remaining = deadline - time.monotonic()
    if not math.isfinite(deadline) or not 0 < remaining <= MAX_SECONDS:
        return {"status": "error", "code": "deadline_exceeded"}
    try:
        xid, display = resolve_parent()
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return {"status": "error", "code": "parent_unavailable"}
    if type(xid) is not int or not 0 < xid <= 0xFFFFFFFF or not isinstance(display, str) or not re.fullmatch(r":\d+(?:\.\d+)?", display):
        return {"status": "error", "code": "parent_unavailable"}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {"status": "error", "code": "deadline_exceeded"}
    environment = os.environ.copy()
    environment.update(DISPLAY=display, QT_QPA_PLATFORM="xcb")
    try:
        selected = subprocess.run(
            ["/usr/bin/kdialog", "--title", CAPTION, "--attach", str(xid),
             "--getexistingdirectory", str(Path.home())],
            env=environment, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=remaining, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "code": "deadline_exceeded"}
    except (OSError, UnicodeError):
        return {"status": "error", "code": "dialog_failed"}
    if selected.returncode == 1:
        return {"status": "cancelled"}
    if selected.returncode != 0:
        return {"status": "error", "code": "dialog_failed"}
    # KDialog terminates the path with a newline. Preserve legitimate spaces;
    # the existing catalog import preview remains the host-path validator.
    path = selected.stdout.removesuffix("\n")
    if not path.startswith("/") or "\0" in path or len(path.encode()) > 4096:
        return {"status": "error", "code": "invalid_selection"}
    return {"status": "selected", "path": path}


def main() -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        deadline = float(sys.argv[1]) if len(sys.argv) == 2 else float("nan")
    except ValueError:
        deadline = float("nan")
    print(json.dumps(choose_directory(deadline), ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
