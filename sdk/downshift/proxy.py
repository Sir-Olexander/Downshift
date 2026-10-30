"""An OpenAI-compatible endpoint in front of one Downshift run.

Agents that take a base URL (LiteLLM, the OpenAI SDK, LangChain...) can be recorded, replayed and
optimized without an adapter that reaches into their internals: point the agent's model client at
`proxy.base_url` and every chat completion goes through `run.chat`, so

  - the harness decides the model, temperature, max_tokens and reasoning (whatever the agent asks for),
  - the system prompt is the harness's `system_prompt`, where `{original_system_prompt}` stands for the
    one the agent sent (a harness without the placeholder gets the agent's prompt first, its own after),
  - tool descriptions the harness lists replace the agent's descriptions for the same tool names,
  - the step's runtime repairs (final_format, recover_tool_calls) apply,
  - every call is recorded with tokens and cost like any other Downshift model call.

    with ChatProxy(run, harness) as proxy:
        subprocess.run([... "--api-base", proxy.base_url ...])

Streaming requests get the whole reply as one chunk. The proxy listens on 127.0.0.1 only.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .adapter import render
from .harness import Harness
from .tracing import Run

PLACEHOLDER = "{original_system_prompt}"


def apply_harness(harness: Harness, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """The agent's request with the harness's system prompt and tool descriptions applied."""
    msgs = [dict(m) for m in messages]
    template = harness.system_prompt or PLACEHOLDER
    if msgs and msgs[0].get("role") == "system":
        original = msgs[0].get("content") or ""
        if isinstance(original, list):
            original = "".join(p.get("text", "") for p in original if isinstance(p, dict))
        msgs[0]["content"] = render(template, original_system_prompt=original) if PLACEHOLDER in template else (original + "\n\n" + template if template.strip() else original)
    elif template.strip() and template != PLACEHOLDER:
        msgs.insert(0, {"role": "system", "content": render(template, original_system_prompt="")})
    if tools:
        out = []
        for t in tools:
            t = json.loads(json.dumps(t))
            fn = t.get("function") or {}
            spec = harness.tools.get(fn.get("name", ""))
            if spec is not None and spec.description:
                fn["description"] = spec.description
            out.append(t)
        tools = out
    return msgs, tools


class ChatProxy:
    def __init__(self, run: Run, harness: Harness, step: str | None = None, host: str = "127.0.0.1", port: int = 0):
        self.run = run
        self.harness = harness
        self.step = step or harness.steps[0].id
        self.calls = 0
        self.errors: list[str] = []
        self._lock = threading.Lock()
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # keep the agent's output clean
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path.rstrip("/").endswith("/models"):
                    self._send(200, json.dumps({"object": "list", "data": [{"id": "downshift", "object": "model"}]}).encode())
                else:
                    self._send(404, b'{"error": {"message": "not found"}}')

            def do_POST(self) -> None:
                if not self.path.rstrip("/").endswith("/chat/completions"):
                    self._send(404, b'{"error": {"message": "only /chat/completions is served"}}')
                    return
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                    reply = proxy._complete(body)
                except Exception as e:  # report to the agent as a server error; the run records it
                    proxy.errors.append(f"{type(e).__name__}: {e}"[:500])
                    self._send(500, json.dumps({"error": {"message": f"downshift proxy: {type(e).__name__}: {e}"[:500], "type": "server_error"}}).encode())
                    return
                if body.get("stream"):
                    chunk = {**reply, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": reply["choices"][0]["message"], "finish_reason": reply["choices"][0]["finish_reason"]}]}
                    data = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()
                    self._send(200, data, "text/event-stream")
                else:
                    self._send(200, json.dumps(reply).encode())

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def _complete(self, body: dict[str, Any]) -> dict[str, Any]:
        messages, tools = apply_harness(self.harness, body.get("messages") or [], body.get("tools"))
        with self._lock:  # one agent conversation: keep its calls in order
            res = self.run.chat(self.step, messages, tools=tools or None, tool_choice=body.get("tool_choice") if tools else None)
            self.calls += 1
        message: dict[str, Any] = {"role": "assistant", "content": res.content or None}
        if res.tool_calls:
            message["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.raw_arguments}} for tc in res.tool_calls]
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": res.model,
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if res.tool_calls else (res.finish_reason or "stop")}],
            "usage": {"prompt_tokens": res.tokens_in, "completion_tokens": res.tokens_out, "total_tokens": res.tokens_in + res.tokens_out},
        }

    def __enter__(self) -> ChatProxy:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
