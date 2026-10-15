"""Pinned data-only acquisition, separate from guest/agent execution."""
import hashlib
import os
from pathlib import Path
import re
import secrets
import time
import urllib.request

REVISION = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FILENAME = re.compile(r"[A-Za-z0-9_.-]+\.gguf\Z")
REPOSITORY = "mradermacher/Qwen3.6-35B-A3B-abliterated-GGUF"


def fetch_candidate(pin, destination, dry_run=False):
    if type(pin) is not dict or set(pin) != {"repo", "revision", "filename", "sha256", "bytes"}:
        raise ValueError("exact_candidate_pin_required")
    if any(type(pin[key]) is not str for key in ("repo", "revision", "filename", "sha256")):
        raise ValueError("invalid_candidate_pin_types")
    if pin["repo"] != REPOSITORY or not REVISION.fullmatch(pin["revision"]) or not SHA256.fullmatch(pin["sha256"]):
        raise ValueError("unapproved_repository_or_pin")
    if not FILENAME.fullmatch(pin["filename"]) or type(pin["bytes"]) is not int or not 1 <= pin["bytes"] <= 30_000_000_000:
        raise ValueError("invalid_candidate_artifact")
    destination = Path(destination)
    if not destination.is_dir() or destination.is_symlink() or destination.stat().st_mode & 0o077:
        raise ValueError("private_artifact_directory_required")
    target = destination / pin["filename"]
    url = f"https://huggingface.co/{REPOSITORY}/resolve/{pin['revision']}/{pin['filename']}"
    if dry_run:
        return {"dry_run": True, "url": url, "expected_bytes": pin["bytes"], "sha256": pin["sha256"]}
    if target.exists():
        from lab.doctor import verify_artifact
        return verify_artifact({"path": str(target), "sha256": pin["sha256"], "bytes": pin["bytes"]})
    temporary = destination / ("download-" + secrets.token_hex(16) + ".part")
    checksum = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + 3600
    try:
        # This is data acquisition only. No transformers/pickle/repository code is run.
        with urllib.request.urlopen(url, timeout=30) as source, temporary.open("xb") as output:
            temporary.chmod(0o600)
            while chunk := source.read(4 * 1024 * 1024):
                if time.monotonic() >= deadline:
                    raise TimeoutError("candidate_download_deadline")
                total += len(chunk)
                if total > pin["bytes"]:
                    raise ValueError("candidate_size_exceeded")
                output.write(chunk)
                checksum.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total != pin["bytes"] or checksum.hexdigest() != pin["sha256"]:
            raise ValueError("candidate_integrity_failed")
        # Never overwrite an existing artifact during a concurrent preparation.
        os.link(temporary, target)
        return {"verified": True, "bytes": total, "sha256": checksum.hexdigest()}
    finally:
        temporary.unlink(missing_ok=True)
