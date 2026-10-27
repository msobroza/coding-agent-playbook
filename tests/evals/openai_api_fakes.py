"""Named fakes of an OpenAI-shaped API for the API judge's tests: no network, no key.

:class:`FakeOpenAIServer` is a real HTTP server on ``127.0.0.1`` that speaks just
enough of the Responses and Chat Completions APIs, so a test drives the judge's
real ``urllib`` path. :class:`FakeJsonPost` stands in for ``post_json`` when a
test only needs the judge's logic.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.judge import JudgeError

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


def responses_payload(text: str) -> dict[str, Any]:
    """A completed Responses API payload answering ``text``, after a reasoning item."""
    message = {"type": "message", "content": [{"type": "output_text", "text": text}]}
    return {"status": "completed", "output": [{"type": "reasoning", "summary": []}, message]}


def chat_payload(text: str) -> dict[str, Any]:
    """A Chat Completions payload answering ``text``."""
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}


@dataclass
class RecordedRequest:
    """One request :class:`FakeOpenAIServer` received."""

    path: str
    headers: dict[str, str]
    body: dict[str, Any]


@dataclass
class FakeOpenAIServer:
    """A local OpenAI-shaped server: answers ``answer`` unless a scripted reply is queued.

    ``replies`` holds ``(status, raw body)`` pairs served first, in order;
    ``delay`` (seconds) holds every answer back, to provoke a client timeout.
    """

    answer: str = "1"
    replies: list[tuple[int, bytes]] = field(default_factory=list)
    delay: float = 0.0
    requests: list[RecordedRequest] = field(default_factory=list)
    port: int = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def reply(self, path: str) -> tuple[int, bytes]:
        """The next scripted reply, else ``answer`` in the shape the path's API uses."""
        if self.replies:
            return self.replies.pop(0)
        payload = responses_payload if path.endswith("/responses") else chat_payload
        return 200, json.dumps(payload(self.answer)).encode("utf-8")


@contextmanager
def serving(server: FakeOpenAIServer) -> Iterator[FakeOpenAIServer]:
    """Serve ``server`` on a free local port for the block, then shut it down."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(server))
    server.port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _handler_for(server: FakeOpenAIServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            server.requests.append(RecordedRequest(self.path, dict(self.headers), body))
            time.sleep(server.delay)
            status, raw = server.reply(self.path)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:
            return  # keep test output quiet

    return Handler


@dataclass
class FakeJsonPost:
    """Stands in for ``post_json``: records each call and plays ``outcomes`` in order.

    An outcome is a payload to return, or a :class:`JudgeError` to raise; the
    last one repeats once the list runs out.
    """

    outcomes: list[dict[str, Any] | JudgeError]
    calls: list[tuple[str, dict[str, str], dict[str, Any], float]] = field(default_factory=list)

    def __call__(
        self, url: str, headers: Mapping[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        self.calls.append((url, dict(headers), body, timeout))
        outcome = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        if isinstance(outcome, JudgeError):
            raise outcome
        return outcome
