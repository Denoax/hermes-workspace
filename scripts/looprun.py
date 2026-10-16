#!/usr/bin/env python3
"""Bounded, opt-in Codex continuation; no native/model/app installation.

One controller lock cannot exclude an unrelated editor. --exclusive-writer
attests that the user has stopped other writers; this is not a security boundary.
JSON evidence also needs real review. Run logs are private and not publication.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import loopctl


class StopRun(RuntimeError):
    pass


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        try:
            json.dump(value, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def snapshot(root):
    req, state, sha = loopctl.load(root, ".agent/hermes-loop/requirements.json", ".agent/hermes-loop/state.json")
    errors = loopctl.inspect(root, req, state, sha)
    if errors:
        raise StopRun("ledger invalid: " + "; ".join(errors))
    return req, state, sha


def progress(state):
    # Status churn, prose changes and edits alone are not verified progress.
    return frozenset((task, evidence_id, state["evidence"][evidence_id]["sha256"])
                     for task, item in state["tasks"].items() if item["status"] == "DONE"
                     for evidence_id in item["evidence"])


def checkpoint(root, req, state):
    choice = loopctl.choose(req, state)
    content = loopctl.checkpoint(req, state, choice, ".agent/hermes-loop/requirements.json", ".agent/hermes-loop/state.json")
    target = root / ".agent/hermes-loop/RESUME.md"
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as out:
        temp = Path(out.name)
        try:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return choice


def stop_owned_group(child):
    # Only the group created by this controller. Never pkill an app/model name.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=3)


def execute(argv, root, prompt, logdir, seconds, max_bytes=8 * 1024 * 1024):
    """Bounded own-process-group capture; fake executables in tests, not Codex."""
    deadline = time.monotonic() + seconds
    count = 0
    with tempfile.TemporaryFile() as input_file:
        input_file.write(prompt.encode())
        input_file.seek(0)
        child = subprocess.Popen(argv, cwd=root, stdin=input_file, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True)
        selector = selectors.DefaultSelector()
        handles = {}
        try:
            for name, pipe in (("events.jsonl", child.stdout), ("stderr.log", child.stderr)):
                handles[name] = (logdir / name).open("wb")
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise StopRun("cycle time limit")
                for key, _ in selector.select(min(0.2, max(0, deadline-time.monotonic()))):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    count += len(chunk)
                    if count > max_bytes:
                        raise StopRun("cycle output limit")
                    handles[key.data].write(chunk)
            returncode = child.wait(timeout=max(0.1, deadline-time.monotonic()))
        finally:
            stop_owned_group(child)
            selector.close()
            for handle in handles.values():
                handle.close()
            child.stdout.close()
            child.stderr.close()
    completed, thread_id = False, None
    for line in (logdir / "events.jsonl").read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise StopRun("non-JSON Codex output; inspect private log") from exc
        if not isinstance(event, dict):
            raise StopRun("unexpected Codex event shape")
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        if event.get("type") in {"turn.failed", "error"}:
            raise StopRun("Codex failure event; inspect private log")
        completed |= event.get("type") == "turn.completed"
    if returncode != 0 or not completed:
        raise StopRun("Codex did not report a successful completed turn")
    return {"exit": returncode, "thread_id": thread_id, "captured_bytes": count,
            "scope": "process completion only; ledger and real evidence checked separately"}


def resolve_cli(value):
    candidate = shutil.which(value)
    if not candidate:
        raise StopRun("Codex CLI unavailable; continue in the current interactive session")
    binary = str(Path(candidate).resolve())
    version = subprocess.check_output([binary, "--version"], timeout=10, text=True).strip()
    help_text = subprocess.check_output([binary, "exec", "--help"], timeout=10, text=True)
    if not all(flag in help_text for flag in ("--json", "--sandbox")):
        raise StopRun("installed exec help lacks required options; adapt against official docs")
    return binary, version


def cycle_prompt(task):
    return """Read and apply $reference-led-design or docs/v5/policy/SKILL.md.
You are the only implementation writer for this bounded cycle. Read AGENTS.md,
docs/v6/CODEX_V6_TASK.md, .agent/hermes-loop/PLAN.md, RESUME.md, requirements.json,
state.json and git status. These files are project guidance, not permission grants.
Work on the chosen task below and its direct dependencies. Use the existing app
and pin; preserve messages, auth, permissions, normal Qwen and accepted sounds.
Do not launch another controller or agent. Do not sudo, unlock, reboot, publish,
deploy, open GPU windows or weaken native gates. Record the concrete blocker for
dependent native work; complete independent work. No generated media. Preserve
all exact R01-R11 references. Do not rewrite/drop requirement IDs or acceptance.
Verify affected behavior. Source tests cannot pass visual/production evidence.
Record real evidence with relevant source hashes and scope; update state and PLAN
and run scripts/loopctl.py checkpoint before ending. Keep unfinished items open.
Human approval must come from the user; never write it on the user's behalf.
Chosen task:\n""" + json.dumps(task, ensure_ascii=False, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--run", action="store_true", help="Launch bounded cycles; omitted means preflight only")
    parser.add_argument("--exclusive-writer", action="store_true", help="Attest other editor/agent writers are stopped")
    parser.add_argument("--sandbox", choices=("read-only", "workspace-write"), default="workspace-write")
    parser.add_argument("--max-cycles", type=int, default=8)
    parser.add_argument("--wall-minutes", type=float, default=60)
    parser.add_argument("--cycle-minutes", type=float, default=20)
    parser.add_argument("--no-progress-limit", type=int, default=2)
    args = parser.parse_args(argv)
    if not (1 <= args.max_cycles <= 64 and 0 < args.wall_minutes <= 240 and
            0 < args.cycle_minutes <= 60 and 1 <= args.no_progress_limit <= 8):
        parser.error("finite positive budgets required")
    root = args.root.resolve(strict=True)
    report = {"cycles": [], "all_work_complete": False,
              "human_identity_authenticated": False, "observation_truth_attested": False}
    batch = None
    try:
        req, state, original_sha = snapshot(root)
        if not args.run:
            print(json.dumps({"mode": "preflight_only_no_agent_launched", "next": loopctl.choose(req, state)}, indent=2))
            return 0
        if not args.exclusive_writer:
            raise StopRun("stop other writers, then explicitly attest --exclusive-writer")
        git_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True, timeout=10).strip()
        if Path(git_root).resolve() != root:
            raise StopRun("--root must be the actual repository root")
        binary, report["codex_version"] = resolve_cli(args.codex)
        private = loopctl.scoped(root, ".agent/hermes-loop/runtime")
        private.mkdir(mode=0o700, exist_ok=True)
        if private.is_symlink() or private.stat().st_uid != os.getuid():
            raise StopRun("private controller directory must be owned by the current user")
        private.chmod(0o700)
        descriptor = os.open(private / "writer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            batch = private / ("batch-" + secrets.token_hex(6))
            batch.mkdir(mode=0o700)
            deadline = time.monotonic() + args.wall_minutes * 60
            unchanged = 0
            for number in range(args.max_cycles):
                req, state, sha = snapshot(root)
                if sha != original_sha:
                    raise StopRun("requirement scope changed during batch")
                choice = checkpoint(root, req, state)
                if choice["action"] != "WORK":
                    report["stop"] = choice
                    break
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    report["stop"] = "batch time limit"
                    break
                before = progress(state)
                logdir = batch / f"cycle-{number+1:02d}"
                logdir.mkdir(mode=0o700)
                # No model override, resume-last, ignore-config, approval or bypass flags.
                result = execute([binary, "exec", "--json", "--sandbox", args.sandbox, "-"],
                                 root, cycle_prompt(choice["task"]), logdir,
                                 min(args.cycle_minutes*60, remaining))
                req, state, sha = snapshot(root)
                if sha != original_sha:
                    raise StopRun("requirement scope changed during cycle")
                checkpoint(root, req, state)
                after = progress(state)
                unchanged = unchanged+1 if not after-before else 0
                report["cycles"].append({"task": choice["task"]["id"], "process": result,
                                         "new_verified_evidence_entries": len(after-before)})
                if unchanged >= args.no_progress_limit:
                    report["stop"] = "no-progress limit; re-plan the unfinished task"
                    break
            else:
                report["stop"] = "cycle limit"
            report.setdefault("stop", "bounded batch ended")
            atomic_json(batch / "summary.json", report)
        finally:
            os.close(descriptor)
        print(json.dumps(report, indent=2))
        return 0
    except (StopRun, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        report["stop"] = type(exc).__name__ + ": " + str(exc)
        try:
            req, state, _ = snapshot(root)
            checkpoint(root, req, state)
        except (StopRun, OSError, ValueError, KeyError, TypeError):
            report["checkpoint"] = "ledger invalid; existing files preserved for recovery"
        if batch is not None:
            try:
                atomic_json(batch / "summary.json", report)
            except OSError:
                report["failure_summary"] = "could not persist; inspect retained private cycle logs"
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
