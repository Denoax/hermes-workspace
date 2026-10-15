"""One loopback backend, bounded text-only API, durable lease and quotas.

This is a transport component, not proof of VM/host network containment. It is
disabled for agents until outside readiness tests establish that boundary.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import socket
import threading
import time
import uuid
from starter.json_limits import bounded_json

ALLOWED_FIELDS = {"model", "messages", "max_tokens", "temperature", "top_p", "seed", "stream", "reasoning_effort"}


def validate_request(raw, alias, tool_profile=False):
    if tool_profile not in (False,True,'read','candidate'):raise ValueError('unknown_tool_authority')
    data = bounded_json(raw, max_bytes=32768)
    allowed=ALLOWED_FIELDS | ({'tools','tool_choice','parallel_tool_calls'} if tool_profile else set())
    if type(data) is not dict or set(data) - allowed or not {"model", "messages"} <= set(data):
        raise ValueError("invalid_request_fields")
    if data["model"] != alias:
        raise ValueError("wrong_model")
    messages = data["messages"]
    if type(messages) is not list or not 1 <= len(messages) <= 32:
        raise ValueError("invalid_messages")
    for message in messages:
        if tool_profile:
            from lab.workspace_contract import tool_call,READ_TOOLS,TOOL_NAMES
            names={'lab_read_file'} if tool_profile=='read' else TOOL_NAMES
            role=message.get('role') if type(message) is dict else None
            fields={'role','content'} | ({'tool_calls','reasoning_content'} if role=='assistant' else {'tool_call_id','name'} if role=='tool' else set())
            if type(message) is not dict or set(message)-fields or role not in ('system','user','assistant','tool'):
                raise ValueError('invalid_tool_message')
            if not isinstance(message.get('content'),str) and not (role=='assistant' and message.get('content') is None):
                raise ValueError('invalid_tool_content')
            if role=='tool' and (type(message.get('tool_call_id')) is not str or len(message['tool_call_id'])>128):
                raise ValueError('invalid_tool_correlation')
            if role=='tool' and 'name' in message and message['name'] not in names:raise ValueError('unapproved_tool_result_name')
            if 'tool_calls' in message:
                if type(message['tool_calls']) is not list or not 1<=len(message['tool_calls'])<=4:raise ValueError('tool_call_limit')
                for call in message['tool_calls']:tool_call(call,names)
            continue
        if type(message) is not dict or set(message) != {"role", "content"}:
            raise ValueError("text_messages_only")
        if message["role"] not in ("system", "user", "assistant") or type(message["content"]) is not str:
            raise ValueError("text_messages_only")
    if tool_profile:
        from lab.workspace_contract import TOOLS,READ_TOOLS
        expected=READ_TOOLS if tool_profile=='read' else TOOLS
        # Pinned Hermes omits tools for its bounded final-summary request.
        # That can only reduce authority; any supplied tool set stays exact.
        if ('tools' in data and data['tools'] not in (expected,[])) or data.get('tool_choice','auto') not in ('auto','none') or data.get('parallel_tool_calls',False) is not False:
            raise ValueError('fixed_guest_tools_required')
    tokens = data.get("max_tokens", 1024)
    if type(tokens) is not int or not 1 <= tokens <= 1024:
        raise ValueError("output_budget")
    if data.get("stream", False) is not False:
        raise ValueError("streaming_not_implemented")
    if 'reasoning_effort' in data and data['reasoning_effort']!='none':
        raise ValueError('unsupported_reasoning_effort')
    if type(data.get("seed", 41)) is not int or not 0 <= data.get("seed", 41) < 2**31:
        raise ValueError("invalid_seed")
    for key, default, lower, upper in (("temperature", 0.0, 0, 2), ("top_p", 1.0, 0, 1)):
        value = data.get(key, default)
        if type(value) not in (int, float) or not lower <= value <= upper:
            raise ValueError("invalid_sampling")
    normalized={**data, "max_tokens": tokens, "stream": False,
            "temperature": data.get("temperature", 0.0), "top_p": data.get("top_p", 1.0),
            "seed": data.get("seed", 41)}
    if normalized.pop('reasoning_effort',None)=='none':
        # Pinned Hermes emits this for a thinking-only length continuation.
        # b9980 documents the equivalent fixed template switch, not this field.
        normalized['chat_template_kwargs']={'enable_thinking':False}
    return normalized


class Relay:
    def __init__(self, store, run_id, alias, backend_port, job_seconds=480,
                 connection_factory=None, cancel_backend=None, tool_profile=False):
        if type(backend_port) is not int or not 1 <= backend_port <= 65535:
            raise ValueError("invalid_backend_port")
        if type(job_seconds) not in (int, float) or not 0 < job_seconds <= 480:
            raise ValueError("invalid_job_duration")
        self.store, self.run_id, self.alias = store, run_id, alias
        self.backend_port, self.job_seconds = backend_port, job_seconds
        self.busy = threading.Lock()
        self.events = []
        self.connection_factory = connection_factory
        self.cancel_backend = cancel_backend
        self.tool_profile=tool_profile

    def authorized(self, token):
        if type(token) is not str:
            return False
        reason = self.store.mutate(self.run_id, lambda m: self.store.active(m))
        if reason:
            return False
        return secrets.compare_digest(token, self.store.token(self.run_id))

    def infer(self, raw, token, job_id):
        try:
            data = validate_request(raw, self.alias, self.tool_profile)
        except (ValueError,UnicodeError) as error:
            # Authenticated malformed retries also consume an attempt and a
            # conservative reservation; invalid requests never reach the backend.
            reason=self.store.admit(self.run_id,token,job_id,1024)
            codes={'invalid_request_fields','wrong_model','invalid_messages','text_messages_only',
                   'output_budget','streaming_not_implemented','unsupported_reasoning_effort','invalid_seed','invalid_sampling'}
            code=str(error) if str(error) in codes else 'invalid_request_data'
            self.events.append({'kind':'request_denied','outcome':'denied',
                                'reason':code,'attempt_reservation':'retained' if reason is None else reason})
            if reason:raise PermissionError(reason)
            raise
        reason = self.store.admit(self.run_id, token, job_id, data["max_tokens"])
        if reason:
            raise PermissionError(reason)
        if not self.busy.acquire(blocking=False):
            raise PermissionError("parallel_job_denied_attempt_counted")
        started = time.monotonic()
        connection = None
        cancellation = threading.Event()
        completed = threading.Event()
        event = {"job_id": job_id, "kind": "backend_request", "ttft_seconds": None,
                 "ttft_reason": "nonstreaming_transport", "model": self.alias}
        deadline = min(started + self.job_seconds, self.store.read(self.run_id)["deadline"])

        def monitor():
            while not completed.wait(0.025):
                expired = time.monotonic() >= deadline
                revoked = self.store.mutate(self.run_id, lambda m: self.store.active(m))
                if expired or revoked:
                    cancellation.set()
                    if connection is not None and connection.sock is not None:
                        try:
                            connection.sock.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                    if self.cancel_backend is not None:
                        self.cancel_backend()
                    return

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("job_expired")
            # HTTPConnection does not follow redirects or proxy environment variables.
            connection = (self.connection_factory(remaining) if self.connection_factory is not None else
                          http.client.HTTPConnection("127.0.0.1", self.backend_port, timeout=remaining))
            monitor_thread.start()
            connection.request("POST", "/v1/chat/completions", json.dumps(data).encode(),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            content = response.read(262145)
            if cancellation.is_set():
                raise TimeoutError("lease_or_job_cancelled")
            if len(content) > 262144 or response.status != 200:
                raise ValueError("backend_response_limit_or_status")
            reply = bounded_json(content, max_bytes=262144)
            choices = reply.get("choices") if type(reply) is dict else None
            if type(choices) is not list or len(choices) != 1:
                raise ValueError("invalid_backend_choices")
            message = choices[0].get("message", {})
            if message.get("tool_calls"):
                if not self.tool_profile:raise ValueError("unexpected_native_tool_call_no_tool_runner")
                from lab.workspace_contract import tool_call,TOOL_NAMES
                if type(message['tool_calls']) is not list or not 1<=len(message['tool_calls'])<=4:raise ValueError('tool_call_limit')
                for call in message['tool_calls']:tool_call(call,{'lab_read_file'} if self.tool_profile=='read' else TOOL_NAMES)
            if type(message.get("content")) is not str and not (self.tool_profile and message.get('content') is None and message.get('tool_calls')):
                raise ValueError("invalid_backend_content")
            event.update(outcome="completed", finish_reason=choices[0].get("finish_reason"),
                         usage=reply.get("usage"), backend_reported_model=reply.get("model"))
            return reply
        except (OSError, ValueError, TimeoutError, http.client.HTTPException) as exc:
            # A transport timeout may race the monitor's next tick. Ending the
            # socket alone cannot certify compute cancellation.
            if self.cancel_backend is not None:
                cancellation.set()
                self.cancel_backend()
            event.update(outcome="failed", error=type(exc).__name__, cancelled=cancellation.is_set())
            raise
        finally:
            completed.set()
            if monitor_thread.ident is not None:
                monitor_thread.join(timeout=0.5)
            if connection is not None:
                connection.close()
            event["wall_seconds"] = time.monotonic() - started
            self.events.append(event)
            self.busy.release()

    def server(self, port=0):
        relay = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                # Never log Authorization headers, raw requests or ephemeral tokens.
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def reply(self, status, data):
                body = json.dumps(data, allow_nan=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def token(self):
                header = self.headers.get("Authorization", "")
                return header[7:] if header.startswith("Bearer ") else ""

            def do_GET(self):
                if not relay.authorized(self.token()):
                    self.reply(403, {"error": "authorization_denied"})
                elif self.path == "/v1/models":
                    self.reply(200, {"object": "list", "data": [{"id": relay.alias, "object": "model"}]})
                else:
                    self.reply(404, {"error": "route_denied"})

            def do_POST(self):
                try:
                    if self.path != "/v1/chat/completions":
                        self.reply(404, {"error": "route_denied"})
                        return
                    if not relay.authorized(self.token()):
                        self.reply(403, {"error": "authorization_denied"})
                        return
                    lengths = self.headers.get_all("Content-Length", [])
                    if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get("Transfer-Encoding"):
                        raise ValueError("invalid_content_length")
                    length = int(lengths[0])
                    if not 0 < length <= 32768:
                        raise ValueError("request_size")
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError("truncated_request")
                    # Explicit IDs allow a transport retry to be rejected. No ID is a new attempt.
                    ids = self.headers.get_all("X-Lab-Job", [])
                    if len(ids) > 1:
                        raise ValueError("duplicate_job_header")
                    job_id = ids[0] if ids else uuid.uuid4().hex
                    self.reply(200, relay.infer(raw, self.token(), job_id))
                except PermissionError:
                    self.reply(403, {"error": "dispatch_denied"})
                except (ValueError, UnicodeError):
                    self.reply(400, {"error": "invalid_request_or_backend_response"})
                except (OSError, TimeoutError, http.client.HTTPException):
                    self.reply(504, {"error": "backend_failed_or_deadline"})

        class BoundedServer(ThreadingHTTPServer):
            daemon_threads = True
            request_queue_size = 4

            def __init__(self, *args):
                self.slots = threading.BoundedSemaphore(4)
                super().__init__(*args)

            def process_request(self, request, client_address):
                if not self.slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, client_address)
                except BaseException:
                    self.slots.release()
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self.slots.release()

        return BoundedServer(("127.0.0.1", port), Handler)
