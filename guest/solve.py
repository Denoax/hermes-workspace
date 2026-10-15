"""Guest-only Hermes diagnostic runner. Never invoke this on the personal host.

Requires a root-owned guest marker and root-owned pinned Hermes installation.
Each invocation receives only a synthetic case and an ephemeral relay credential.
"""
import contextlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid
sys.path.insert(0, '/opt/mani-vmlab')
from json_limits import bounded_json

HERMES_REVISION = "63279301bcbdc185c1b07b98a9312eb0c862f26d"
RELAY = "http://127.0.0.1:18081/v1"


def configuration(alias, token):
    route = {"provider": "custom", "model": alias, "base_url": RELAY, "api_key": token,
             "timeout": 30}
    auxiliary = {name: dict(route) for name in
                 ("vision", "compression", "skills_hub", "approval", "review", "mcp", "title_generation")}
    auxiliary["title_generation"]["enabled"] = False
    auxiliary["transient_retries"] = 0
    return {"model": {"provider": "custom", "default": alias, "base_url": RELAY, "streaming": False},
            "fallback_model": [], "compression": {"enabled": False}, "auxiliary": auxiliary,
            "delegation": {**route, "max_concurrent": 1}, "mcp_servers": {},
            "agent": {"max_turns": 2}, "memory": {"memory_enabled": False, "user_profile_enabled": False}}


def trusted_guest():
    if os.geteuid() == 0:
        raise RuntimeError("solver_must_be_nonroot_guest_user")
    for name in ("/etc/mani-vmlab/guest.json", "/opt/mani-vmlab/solve.py", "/opt/hermes/run_agent.py"):
        path = Path(name)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError("guest_trusted_installation_required")
    marker = json.loads(Path("/etc/mani-vmlab/guest.json").read_text())
    if marker.get('role') != 'controller' or marker.get('Hermes_revision') != HERMES_REVISION:
        raise RuntimeError("guest_pinned_installation_required")
    # This marker describes installation only. The outside supervisor authorizes
    # execution and supplies a lease-bound relay token after live qualification.


def main():
    trusted_guest()
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError("input_limit")
    request = bounded_json(raw, max_bytes=32768)
    if type(request) is not dict or set(request) != {"prompt", "model", "relay_token"}:
        raise ValueError("invalid_solver_request")
    if any(type(request[key]) is not str for key in request) or len(request["prompt"].encode()) > 8192:
        raise ValueError("invalid_solver_fields")
    with tempfile.TemporaryDirectory(prefix="mani-lab-session-") as directory:
        os.environ.clear()
        os.environ.update(PATH='/usr/bin:/bin', LANG='C.UTF-8', HOME=directory, HERMES_HOME=directory,
                          PYTHONDONTWRITEBYTECODE='1')
        os.chdir(directory)
        config = configuration(request["model"], request["relay_token"])
        path = Path(directory) / "config.yaml"
        path.write_text(json.dumps(config))  # JSON is a YAML subset; no template interpolation.
        path.chmod(0o600)
        sys.path.insert(0, "/opt/hermes")
        sys.path.insert(1, "/opt/hermes-deps")
        # Unreviewed Hermes output remains guest-local and never contaminates JSON transport.
        with tempfile.TemporaryFile(mode="w+") as logs, contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            from run_agent import AIAgent
            agent = AIAgent(base_url=RELAY, api_key=request["relay_token"], provider="custom",
                            model=request["model"], enabled_toolsets=[], max_iterations=2,
                            max_tokens=1024, session_id=uuid.uuid4().hex, quiet_mode=True,
                            verbose_logging=False, save_trajectories=False,
                            skip_context_files=True, load_soul_identity=False, skip_memory=True,
                            skip_background_review=True, fallback_model=None, run_budget_seconds=480,
                            # Hermes boosts output on length continuations. Keep
                            # every request inside the same outside 1024-token cap.
                            request_overrides={"max_tokens":1024,"temperature":0.0,"top_p":1.0,"seed":41})
            try:
                response = agent.run_conversation(request["prompt"],
                                                  system_message="Solve the provided owned synthetic diagnostic. Return the requested JSON only.")
            finally:
                agent.close()
        answer = response.get("final_response")
        if type(answer) is not str or len(answer.encode()) > 32768:
            raise RuntimeError("invalid_Hermes_final_response")
        print(json.dumps({"answer": answer, "Hermes_revision": HERMES_REVISION,
                          "toolsets": [], "memory_imported": False}))


if __name__ == "__main__":
    main()
