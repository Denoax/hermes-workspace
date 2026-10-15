"""Allowlisted review export with checksums and a clean extraction audit.

The operator must inspect the staged text before delivery. This script cannot
certify semantic sanitization by itself. It excludes all private state.
"""
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

SOURCE_DIRS = {"lab", "guest", "native", "starter", "bench", "configs", "tests", "scripts", "contracts", "policy"}
SOURCE_TOP = {"AGENTS.md", "README.md", "CODEX_TASK.md", "ARCHITECTURE.md", "MODEL_COMPARISON.md",
              "SOURCE_NOTES.md", "RETURN_CONTRACT.md", "EXPERIMENT_LADDER.md", "PREPARATION_CHECKS.md",
              "00_READ_ME.md", "START_HERE.txt", "manifest.json", "labctl", ".gitignore", "CONTINUATION_STATUS.md"}
SUFFIXES = {".py", ".md", ".txt", ".json", ".csv", ".jsonl", ".log", ".yaml", ".svg", ".c", ".patch"}


def source_files(root):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in relative.parts):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if (len(relative.parts) == 1 and relative.name in SOURCE_TOP) or (
            relative.parts[0] in SOURCE_DIRS and (path.suffix in SUFFIXES or path.name == "__init__.py")
        ):
            yield path, relative


def verify_zip(archive):
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory(prefix="mani-lab-review-check-") as directory:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate_archive_member")
        for item in source.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("unsafe_archive_member")
        if source.testzip() is not None:
            raise ValueError("zip_CRC_failure")
        source.extractall(directory)
        root = Path(directory) / "MANI_HERMES_VM_LAB_REVIEW"
        entries = (root / "SHA256SUMS.txt").read_text().splitlines()
        verified = set()
        for line in entries:
            expected, name = line.split("  ", 1)
            relative = PurePosixPath(name)
            if not re.fullmatch(r"[0-9a-f]{64}", expected) or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("invalid_checksum_record")
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("payload_checksum_mismatch")
            verified.add("MANI_HERMES_VM_LAB_REVIEW/" + name)
        payload = set(names) - {"MANI_HERMES_VM_LAB_REVIEW/SHA256SUMS.txt"}
        if payload != verified:
            raise ValueError("unverified_archive_payload")
        return {"clean_extraction_verified": True, "payload_checksums_verified": len(verified)}


def package(project, review_docs, output):
    payload = {}
    for path, relative in source_files(Path(project)):
        payload["source/" + relative.as_posix()] = path.read_bytes()
    for path in sorted((Path(project) / "results").rglob("*")):
        if path.is_file() and not path.is_symlink() and path.suffix in SUFFIXES:
            payload["results/" + path.relative_to(Path(project) / "results").as_posix()] = path.read_bytes()
    for path in sorted(Path(review_docs).iterdir()):
        if path.is_file() and path.suffix in SUFFIXES:
            payload[path.name] = path.read_bytes()
    for name, data in payload.items():
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("review_file_too_large")
        text = data.decode("utf-8")
        if re.search(r"(?m)^-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----", text):
            raise ValueError("private_key_in_review")
    checksums = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n" for name, data in sorted(payload.items()))
    payload["SHA256SUMS.txt"] = checksums.encode()
    output = Path(output)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            item = zipfile.ZipInfo("MANI_HERMES_VM_LAB_REVIEW/" + name)
            item.external_attr = (stat.S_IFREG | (0o700 if name == "source/labctl" else 0o600)) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    output.chmod(0o600)
    verification = verify_zip(output)
    return {"path": str(output), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), **verification}
