"""Real isolated owned host-process/loopback tests. No models, VMs or candidates."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from lab.process import register, start_watchdog, stop_owned
from lab.relay import Relay
from lab.state import RunStore


class WatchdogIntegration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = RunStore(Path(self.temporary.name) / "state")

    def fleet(self, run_id):
        child = subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (child.kill(), child.wait()) if child.poll() is None else child.wait())
        register(self.store, run_id, child, "synthetic_owned_workload")
        return child

    def test_absolute_deadline_stops_owned_workload_independently(self):
        run_id = self.store.create(ttl=0.4, heartbeat_timeout=0.4)
        child = self.fleet(run_id)
        watcher = start_watchdog(self.store, run_id)
        self.addCleanup(lambda: (watcher.kill(), watcher.wait()) if watcher.poll() is None else watcher.wait())
        watcher.wait(timeout=3)
        child.wait(timeout=1)
        self.assertEqual(self.store.read(run_id)["reason"], "absolute_expiry")
        self.assertIn(child.returncode, (-signal.SIGTERM, -signal.SIGKILL))
        result = json.loads((self.store.directory(run_id) / "watchdog_result.json").read_text())
        print("CONTROL_METRIC " + json.dumps({"scenario": "absolute_expiry", "evidence": result["evidence_kind"],
              "stop_after_deadline_seconds": result["stopped_monotonic"] - self.store.read(run_id)["deadline"],
              "owned_workload_exited": True}))

    def test_heartbeat_loss_stops_without_absolute_expiry(self):
        run_id = self.store.create(ttl=5, heartbeat_timeout=0.2)
        child = self.fleet(run_id)
        watcher = start_watchdog(self.store, run_id)
        watcher.wait(timeout=3)
        child.wait(timeout=1)
        self.assertEqual(self.store.read(run_id)["reason"], "heartbeat_lost")
        print('CONTROL_METRIC {"scenario":"heartbeat_loss","owned_workload_exited":true,"real_VM":false}')

    def test_killed_owner_does_not_kill_watchdog_or_leave_workload(self):
        run_id = self.store.create(ttl=5, heartbeat_timeout=5)
        child = self.fleet(run_id)
        owner = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
        owner_fd = os.pidfd_open(owner.pid)
        self.addCleanup(os.close, owner_fd)
        watcher = start_watchdog(self.store, run_id, owner.pid)
        started = time.monotonic()
        owner.kill()
        owner.wait(timeout=1)
        watcher.wait(timeout=3)
        child.wait(timeout=1)
        self.assertIn(self.store.read(run_id)["reason"], ("owner_crashed", "owner_absent"))
        print("CONTROL_METRIC " + json.dumps({"scenario": "owner_crash", "stop_wall_seconds": time.monotonic() - started,
                                             "owned_workload_exited": True, "real_VM": False}))

    def test_stop_preserves_unregistered_process_and_is_idempotent(self):
        run_id = self.store.create()
        owned = self.fleet(run_id)
        other = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
        self.addCleanup(lambda: (other.kill(), other.wait()) if other.poll() is None else other.wait())
        self.store.revoke(run_id, "operator_stop")
        stop_owned(self.store, run_id)
        owned.wait(timeout=1)
        stop_owned(self.store, run_id)
        self.assertIsNone(other.poll())
        print('CONTROL_METRIC {"scenario":"identity_stop","unregistered_process_preserved":true,"idempotent_stop":true}')


class RelayIntegration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = RunStore(Path(self.temporary.name) / "state")
        self.run_id = self.store.create(ttl=5, heartbeat_timeout=5)
        self.backend_entered = threading.Event()
        self.backend_release = threading.Event()
        self.addCleanup(self.backend_release.set)
        owner = self

        class FixtureBackend(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.backend_entered.set()
                if body["messages"][0]["content"] == "stall":
                    owner.backend_release.wait(timeout=3)
                payload = json.dumps({"model": "fixture_backend_not_a_model",
                                      "choices": [{"message": {"content": '{"stale_workers":["B"]}'}, "finish_reason": "stop"}],
                                      "usage": {"prompt_tokens": 5, "completion_tokens": 8}}).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), FixtureBackend)
        self.backend.daemon_threads = True
        self.start_server(self.backend)
        self.relay = Relay(self.store, self.run_id, "arm", self.backend.server_port, job_seconds=1)
        self.server = self.relay.server()
        self.start_server(self.server)
        self.token = self.store.token(self.run_id)

    def start_server(self, server):
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(timeout=2))
        self.addCleanup(server.shutdown)

    def request(self, path="/v1/chat/completions", content="synthetic", token=None, job_id=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + (self.token if token is None else token),
                   "Content-Type": "application/json", "X-Lab-Job": job_id or uuid.uuid4().hex}
        body = json.dumps({"model": "arm", "messages": [{"role": "user", "content": content}], "max_tokens": 32})
        connection.request("POST", path, body, headers)
        result = connection.getresponse()
        payload = json.loads(result.read())
        connection.close()
        return result.status, payload

    def test_authenticated_allowed_path_and_native_stop_reason(self):
        status, response = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(response["choices"][0]["finish_reason"], "stop")
        self.assertIsNone(self.relay.events[0]["ttft_seconds"])
        print("CONTROL_METRIC " + json.dumps({"scenario": "allowed_relay", "model_evaluation": False,
                                             "wall_seconds": self.relay.events[0]["wall_seconds"], "finish_reason": "stop"}))

    def test_denied_admin_url_and_token_paths_do_not_reach_backend(self):
        for path in ("/slots", "/load", "/v1/images/generations", "/proxy?url=http://outside"):
            self.assertEqual(self.request(path=path)[0], 404)
        self.assertEqual(self.request(token="wrong")[0], 403)
        self.assertFalse(self.backend_entered.is_set())
        print('CONTROL_METRIC {"scenario":"denied_relay_routes","fixture_backend_reached":false,"VM_network_evidence":false}')

    def test_replay_denied_across_actual_HTTP(self):
        job_id = uuid.uuid4().hex
        self.assertEqual(self.request(job_id=job_id)[0], 200)
        self.assertEqual(self.request(job_id=job_id)[0], 403)
        self.assertEqual(self.store.read(self.run_id)["calls"], 1)
        print('CONTROL_METRIC {"scenario":"HTTP_replay","second_dispatch_denied":true}')

    def test_stalled_inference_interrupted_by_revocation(self):
        future = []
        worker = threading.Thread(target=lambda: future.append(self.request(content="stall")))
        worker.start()
        self.assertTrue(self.backend_entered.wait(timeout=1))
        started = time.monotonic()
        self.store.revoke(self.run_id, "operator_stop")
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(future[0][0], 504)
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(self.relay.events[0]["cancelled"])
        print("CONTROL_METRIC " + json.dumps({"scenario": "stalled_inference_revocation", "model_evaluation": False,
                                             "cancellation_wall_seconds": time.monotonic() - started}))

    def test_stalled_inference_job_timeout_retains_attempt(self):
        self.relay.job_seconds = 0.15
        self.assertEqual(self.request(content="stall")[0], 504)
        self.assertEqual(self.store.read(self.run_id)["calls"], 1)
        print("CONTROL_METRIC " + json.dumps({"scenario": "stalled_inference_job_expiry", "model_evaluation": False,
                                             "attempt_counted": True, "wall_seconds": self.relay.events[0]["wall_seconds"]}))


if __name__ == "__main__":
    unittest.main()
