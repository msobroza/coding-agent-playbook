---
id: a2a-client-deadlines
name: A2A client deadlines
description: "Poll another agent's task with capped backoff under an overall deadline, handle every terminal state, and authenticate through the shared token flow."
scope: scoped
section: a2a
priority: 62
globs:
  - "**/a2a.py"
  - "**/*agent*.py"
  - "**/main.py"
  - "**/chat_app.py"
applies_if:
  domino_project: true
  any_dependency: ["fasta2a", "a2a-sdk", "pydantic-ai", "pydantic-ai-slim"]
tags: [python, domino, a2a, httpx]
---

# A2A client deadlines

`message/send` may answer with a task instead of a message, and the caller then polls `tasks/get`. Poll with capped exponential backoff under one overall deadline taken from settings, handle the `completed`, `failed`, `canceled`, `rejected`, `input-required` and `auth-required` states explicitly, bound each request by the time left, turn a JSON-RPC error object into a typed error, and raise a typed error that carries the task id when the deadline passes. Every call to another Domino App carries a bearer token from the shared token provider, attached by the auth flow of one long-lived client (domino-agent-endpoint-auth). Self-registration with a registry is optional and best effort: a timeout and a logged warning on failure, never a silent pass; propose a registry dependency instead of adding it unasked.

## Bad Example

```python
token = requests.get(TOKEN_URL).text  # blocking, no timeout, fetched once, then expires
headers = {"Authorization": f"Bearer {token}"}
task = send_message(question, headers)
while task["status"]["state"] in ("submitted", "working"):  # no deadline: loops forever
    time.sleep(1)
    task = get_task(task["id"], headers)
try:
    register_with_registry(card)
except Exception:
    pass  # the agent silently never appears
```

## Good Example

```python
import asyncio
import time
from dataclasses import dataclass

import httpx

TERMINAL = frozenset({"completed", "failed", "canceled", "rejected"})
NEEDS_CALLER = frozenset({"input-required", "auth-required"})


class TaskDeadlineError(Exception):
    def __init__(self, task_id: str, deadline_s: float) -> None:
        super().__init__(f"task {task_id} not finished within {deadline_s} s")
        self.task_id = task_id


class RemoteAgentError(Exception):
    def __init__(self, task_id: str, error: object) -> None:
        super().__init__(f"tasks/get for {task_id} failed: {error}")
        self.task_id = task_id


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    state: str
    artifacts: tuple[object, ...]


async def poll_task(
    client: httpx.AsyncClient, task_id: str, *, deadline_s: float, max_delay_s: float = 5.0
) -> TaskResult:
    """Poll tasks/get until the task ends or needs the caller; client carries auth."""
    stop_at = time.monotonic() + deadline_s
    delay = 0.25
    payload = {"jsonrpc": "2.0", "id": task_id, "method": "tasks/get", "params": {"id": task_id}}
    while (remaining := stop_at - time.monotonic()) > 0:
        try:
            response = await client.post("/a2a/", json=payload, timeout=remaining)
        except httpx.TimeoutException as exc:
            raise TaskDeadlineError(task_id, deadline_s) from exc
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RemoteAgentError(task_id, body["error"])
        task = body["result"]
        state = task["status"]["state"]
        if state in TERMINAL or state in NEEDS_CALLER:
            return TaskResult(task_id, state, tuple(task.get("artifacts", ())))
        await asyncio.sleep(min(delay, max(stop_at - time.monotonic(), 0)))
        delay = min(delay * 2, max_delay_s)
    raise TaskDeadlineError(task_id, deadline_s)
```

The caller branches on the returned state: `completed` reads the artifacts, `failed`, `canceled` and `rejected` raise a domain error, and `input-required` or `auth-required` goes back to the user or to the credential flow.

## Notes

- Timeouts and retries in general are python-retries-and-timeouts (python-coding, where the repo declares requests, httpx or aiohttp); one shared client per process is httpx-shared-client (web-application, where the repo declares FastAPI and httpx).
- A browser UI that polls a task needs the same deadline.
- Example: examples/simple-agent-api/tests/test_api.py, whose A2A test polls under a deadline.
