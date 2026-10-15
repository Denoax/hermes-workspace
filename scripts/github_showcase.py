"""Capture the real workspace and compose repository media from owned evidence.

Run on the configured workstation with its existing authenticated browser harness.
All content mutations are isolated renderer fixtures, never production RPCs.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workspace import parity_browser

OUTPUT = ROOT / "showcase/github"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*arguments):
    subprocess.run(arguments, check=True, timeout=90, capture_output=True)


def documentation_fixture():
    """Change only the harness's explicitly isolated illustrative content."""
    fixture = parity_browser.FIXTURE
    fixture = fixture.replace("'Review fixture'", "'Hermes workspace'")
    fixture = fixture.replace("'Source examples'", "'Examples'")
    fixture = fixture.replace("'Interface review'", "'Review a helper'")
    fixture = fixture.replace(
        "Review [program.py](program.py). Keep the original files.",
        "Review [program.py](program.py). Keep the original files intact.",
    )
    fixture = fixture.replace(
        "Renderer fixture only. No model response.",
        "Illustrative review · documentation fixture.\\n\\n"
        "This helper keeps integer values inside the inclusive range 0–100.",
    )
    fixture = fixture.replace(
        "Literal text: <img src=x onerror=window.__xss=1>",
        "The source stays unchanged until you explicitly save or apply a review.",
    )
    fixture = fixture.replace("read_file fixture", "Read program.py · documentation fixture")
    fixture = fixture.replace(
        "Renderer fixture · no model or native job", "Documentation fixture · no live model response"
    )
    return fixture


def record_motion(browser):
    """Keep the original frame timestamps of a short real interface tour."""
    with tempfile.TemporaryDirectory(prefix="hermes-doc-motion-") as directory:
        frames = []

        def event(message):
            if message["method"] != "Page.screencastFrame":
                return
            data = message["params"]
            path = Path(directory) / f"{len(frames):05d}.jpg"
            path.write_bytes(base64.b64decode(data["data"]))
            frames.append((path, data["metadata"]["timestamp"]))
            browser.pipe.counter += 1
            reply = json.dumps({"id": browser.pipe.counter, "method": "Page.screencastFrameAck",
                                "params": {"sessionId": data["sessionId"]}, "sessionId": browser.session}).encode() + b"\0"
            while reply:
                reply = reply[os.write(browser.pipe.write, reply):]

        def hold(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                browser.evaluate("document.visibilityState")
                time.sleep(.015)

        browser.pipe.on_event = event
        browser.call("Page.startScreencast", {"format": "jpeg", "quality": 94,
                                            "maxWidth": 1440, "maxHeight": 720, "everyNthFrame": 1})
        try:
            hold(.7)
            for _ in range(2):
                browser.click("#settings-toggle")
                browser.wait("document.getElementById('appearance').open")
                browser.settle()
                hold(.9)
                browser.key("Escape")
                browser.wait("!hermesPaneMetrics.rafPending")
                hold(.5)
            browser.click("#settings-toggle")
            browser.wait("document.getElementById('appearance').open")
            browser.settle()
            browser.click("#theme-buddy")
            browser.settle()
            hold(.8)
            browser.click("#theme-buddy")
            browser.settle()
            hold(.4)
            browser.key("Escape")
            browser.wait("!hermesPaneMetrics.rafPending")
            hold(.8)
        finally:
            browser.call("Page.stopScreencast")
            browser.pipe.on_event = None
        rows = []
        for i, (path, timestamp) in enumerate(frames):
            rows.append(f"file '{path}'")
            if i + 1 < len(frames):
                rows.append("duration " + str(max(.001, frames[i + 1][1] - timestamp)))
        rows.append(f"file '{frames[-1][0]}'")
        concat = Path(directory) / "frames.txt"
        concat.write_text("\n".join(rows) + "\n")
        command("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-fps_mode", "vfr", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                str(OUTPUT / "workspace-motion.mp4"))
        return {"frames": len(frames), "seconds": frames[-1][1] - frames[0][1],
                "sha256": digest(OUTPUT / "workspace-motion.mp4"),
                "scope": "Actual trusted pointer/keyboard tour of labelled renderer fixtures; source frame timestamps preserved; silent"}


def capture():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    parity_browser.FIXTURE = documentation_fixture()
    browser = parity_browser.Browser("github-showcase")
    records = []
    try:
        browser.evaluate("localStorage.setItem('hermes-ui:sounds','off')")
        browser.call("Page.reload")
        browser.wait("document.getElementById('connection')?.textContent==='Connected'")
        for width, height in [(1440, 720), (390, 844)]:
            browser.metric(width, height)
            browser.key("Escape")
            browser.wait("!globalThis.hermesPaneMetrics?.rafPending")
            if width == 1440:
                if browser.evaluate("!!document.querySelector('dialog[open]')"):
                    raise RuntimeError("preview_requires_closed_settings_and_panels")
                browser.capture(OUTPUT / "workspace-dark.png")
                motion = record_motion(browser)
            browser.click("#settings-toggle")
            browser.wait("document.getElementById('appearance').open")
            browser.settle()
            browser.capture(OUTPUT / f"settings-dark-{width}.png")
            browser.click("#theme-buddy")
            browser.settle()
            time.sleep(.15)
            browser.capture(OUTPUT / f"settings-light-{width}.png")
            browser.click("#theme-buddy")
            browser.settle()
            browser.key("Escape")
            browser.wait("!hermesPaneMetrics.rafPending")
            if width == 1440:
                browser.click("#files-toggle")
                browser.wait("document.getElementById('files-panel').open")
                browser.settle()
                browser.click("#tree button[data-path]")
                browser.wait("!document.getElementById('file-preview').hidden")
                browser.capture(OUTPUT / "files.png")
                browser.key("Escape")
                browser.wait("!hermesPaneMetrics.rafPending")
        runtime = browser.served_hashes()
        errors = browser.evaluate("window.__parityErrors")
        if errors:
            raise RuntimeError("showcase_runtime_errors")
        captures = ["workspace-dark", "files", "settings-dark-1440", "settings-light-1440",
                    "settings-dark-390", "settings-light-390"]
        for name in captures:
            path = OUTPUT / (name + ".png")
            target = path.with_suffix(".webp")
            command("ffmpeg", "-v", "error", "-y", "-i", str(path), "-frames:v", "1",
                    "-c:v", "libwebp", "-lossless", "1", str(target))
            records.append({"path": target.name, "source_sha256": digest(path),
                            "sha256": digest(target), "operation": "Actual native browser capture; lossless WebP conversion"})
            path.unlink()
        mark = ROOT / "workspace/ui/brand/hermes.png"
        (OUTPUT / "hermes-mark.png").write_bytes(mark.read_bytes())
        (OUTPUT / "capture-sources.json").write_text(json.dumps({
            "scope": "Real current interface with labelled, isolated documentation fixtures; no live inference or production mutation",
            "fixture_source": "scripts/github_showcase.py:documentation_fixture",
            "served_assets": runtime, "captures": records, "brand_sha256": digest(mark),
            "recording": motion,
            "references": ["https://github.com/Denoax/portfolio", "https://github.com/Denoax/konata-hyprland-dotfiles"],
        }, indent=2) + "\n")
    finally:
        browser.close()


def prepare_motion():
    source = OUTPUT / "workspace-motion.mp4"
    # Retain the actual closed-pane capture; a settled Settings frame is not
    # the repository preview requested by the owner.
    shutil.copyfile(OUTPUT / "workspace-dark.webp", OUTPUT / "banner-still.webp")
    command("ffmpeg", "-v", "error", "-y", "-i", str(source), "-an", "-filter_complex",
            "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
            "[b][p]paletteuse=dither=sierra2_4a", "-loop", "0", str(OUTPUT / "interaction.gif"))
    (OUTPUT / "motion-source.json").write_text(json.dumps({
        "source": "showcase/github/workspace-motion.mp4", "source_sha256": digest(source),
        "interaction.gif": {"sha256": digest(OUTPUT / "interaction.gif"),
                            "operation": "Full original recording at original pace, silent, 15fps and960px wide; GIF palette conversion"},
        "banner-still.webp": {"sha256": digest(OUTPUT / "banner-still.webp"),
                              "operation": "Byte-identical fresh workspace-dark.webp capture with all panes closed; no crop or retouch"},
    }, indent=2) + "\n")


def compose(origin):
    """Render the authored banner; seeking preserves the source playback pace."""
    browser = parity_browser.Browser("github-banner", fixture=False)
    frame_prefix = "_frame-" + os.urandom(5).hex() + "-"
    try:
        browser.metric(1280, 460)
        browser.call("Page.navigate", {"url": origin + "/banner.html"})
        browser.wait("typeof window.bannerImage==='function'")
        browser.evaluate("window.bannerReady.then(()=>true)")
        native_still = OUTPUT / (frame_prefix + "still.png")
        browser.capture(native_still)
        fit = "scale=990:352:force_original_aspect_ratio=decrease,pad=990:352:(ow-iw)/2:(oh-ih)/2:color=0xeaece8"
        command("ffmpeg", "-v", "error", "-y", "-i", str(native_still), "-vf", fit,
                "-frames:v", "1", str(OUTPUT / "banner.png"))
        native_still.unlink()
        browser.metric(1280, 640)
        browser.call("Page.navigate", {"url": origin + "/banner.html?format=social"})
        browser.wait("typeof window.bannerImage==='function'")
        browser.evaluate("window.bannerReady.then(()=>true)")
        browser.capture(OUTPUT / "social-preview.png")
        if (OUTPUT / "social-preview.png").stat().st_size >= 1_000_000:
            raise ValueError("social_preview_exceeds_GitHub_size_limit")
        browser.metric(1280, 460)
        browser.call("Page.navigate", {"url": origin + "/banner.html"})
        browser.wait("typeof window.bannerImage==='function'")
        source = OUTPUT / "workspace-motion.mp4"
        duration = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(source)], text=True))
        with tempfile.TemporaryDirectory(prefix="hermes-banner-") as directory:
            count = math.floor(duration * 15)
            command("ffmpeg", "-v", "error", "-y", "-i", str(source), "-vf", "fps=15",
                    "-frames:v", str(count), "-start_number", "0", str(OUTPUT / (frame_prefix + "%05d.png")))
            for index in range(count):
                browser.evaluate("window.bannerImage(" + json.dumps(frame_prefix + f"{index:05d}.png") + ").then(()=>true)")
                browser.capture(Path(directory) / f"{index:05d}.png")
            command("ffmpeg", "-v", "error", "-y", "-framerate", "15", "-i",
                    directory + "/%05d.png", "-filter_complex",
                    fit + ",split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
                    "[b][p]paletteuse=dither=sierra2_4a", "-loop", "0", str(OUTPUT / "banner.gif"))
        record = {
            "source": "showcase/github/banner.html", "source_sha256": digest(OUTPUT / "banner.html"),
            "video_sha256": digest(source), "frames": count, "fps": 15,
            "operation": "Original HTML/CSS composition with a real interface recording; sampled at source pace, no interpolation or retiming; a presentation asset, not unedited app evidence",
            "files": {name: {"sha256": digest(OUTPUT / name), "bytes": (OUTPUT / name).stat().st_size}
                      for name in ["banner.gif", "banner.png", "social-preview.png"]},
            "social_preview": {"width": 1280, "height": 640, "under_1_MB": True},
            "banner_canvas": {"width": 990, "height": 352, "fit": "Full1280x460 authored composition fitted without crop or stretch to the existing profile canvas"},
        }
        (OUTPUT / "banner-sources.json").write_text(json.dumps(record, indent=2) + "\n")
    finally:
        for path in OUTPUT.glob(frame_prefix + "*.png"):
            path.unlink()
        browser.close()


def serve():
    """Expose only the documentation directory and two fonts on loopback."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = urlsplit(self.path).path
            fonts = {"/fonts/BebasNeue.ttf": "BebasNeue.ttf", "/fonts/DMSans.ttf": "DMSans.ttf"}
            if name in fonts:
                path = ROOT / "workspace/ui/fonts" / fonts[name]
            elif name == "/":
                path = OUTPUT / "README-preview.html"
            elif "/" not in name[1:] and ".." not in name:
                path = OUTPUT / name[1:]
            else:
                self.send_error(404)
                return
            if not path.is_file() or path.is_symlink():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    print("Documentation only: http://127.0.0.1:18794/", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", 18794), Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["capture", "motion", "compose", "serve"])
    parser.add_argument("--origin", default="http://127.0.0.1:18794")
    arguments = parser.parse_args()
    if arguments.operation == "capture":
        capture()
    elif arguments.operation == "motion":
        prepare_motion()
    elif arguments.operation == "compose":
        if arguments.origin != "http://127.0.0.1:18794":
            parser.error("Use the documented loopback-only asset server.")
        compose(arguments.origin)
    else:
        serve()
