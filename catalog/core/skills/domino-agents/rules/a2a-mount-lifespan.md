---
id: a2a-mount-lifespan
name: A2A mount and lifespan
description: "Mount the A2A app from create_app and enter its lifespan from the parent's, so its task worker runs; one worker, one pod."
scope: scoped
section: a2a
priority: 60
globs:
  - "**/a2a.py"
  - "**/*agent*.py"
  - "**/main.py"
  - "**/chat_app.py"
applies_if:
  domino_project: true
  has_framework: ["fastapi"]
  any_dependency: ["fasta2a", "a2a-sdk", "pydantic-ai", "pydantic-ai-slim"]
tags: [python, domino, a2a, fastapi]
---

# A2A mount and lifespan

A FastAPI or Starlette parent app does not run the lifespan of an app mounted under it. The A2A app built by `agent.to_a2a()` starts its task manager, broker and worker inside its own lifespan, so a plain mount accepts `message/send` requests, stores the tasks and never processes them: callers poll `tasks/get` until they give up. Build the A2A app in `create_app` from the agent the app already holds, mount it at `/a2a`, and enter the sub-app's lifespan from the parent's.

## Bad Example

```python
from fastapi import FastAPI

from app.agent import agent  # built at import

app = FastAPI()
app.mount("/a2a", agent.to_a2a())  # its lifespan never runs: tasks stay "submitted"
```

## Good Example

```python
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
from fastapi import FastAPI
from starlette.applications import Starlette


def make_lifespan(
    a2a_app: Starlette, clients: Sequence[httpx.AsyncClient]
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            async with a2a_app.router.lifespan_context(a2a_app):
                yield
        finally:
            for client in clients:
                await client.aclose()

    return lifespan


def create_app(
    settings: AgentSettings,
    *,
    model: Model | None = None,
    token_provider: TokenProvider | None = None,
    tracer: Tracer | None = None,
) -> FastAPI:
    clients = build_clients(settings, token_provider)
    agent = build_agent(model or build_model(settings, clients.model), settings.agent_config)
    tracer = tracer or select_tracer(settings)
    a2a_app = build_a2a_app(agent, settings)
    app = FastAPI(lifespan=make_lifespan(a2a_app, (clients.model, clients.token)))
    app.state.ask_agent = tracer.trace(REQUEST_SPAN_NAME)(make_ask(agent, settings))
    app.mount("/a2a", a2a_app)
    return app
```

The `finally` closes the clients even when the A2A app's shutdown raises.

## Notes

- The default broker and task storage live in the memory of one process. Start the server with one worker and keep the App at one pod. Session affinity routes a viewer's browser session to one pod and needs an admin flag; its effect on machine callers is not documented, so the engine infers that a second replica without shared task storage can receive a `tasks/get` for a task it never saw.
- Prove the worker runs with a test that sends `message/send` and polls `tasks/get` to completion under a deadline (domino-agent-fake-llm-tests). Route tests use the test client as a context manager, so both lifespans run.
- The gate also lists pydantic-ai because its a2a extra brings fasta2a in without the repo naming it.
- The rest of the app factory is domino-agent-app-factory; the card the sub-app serves is a2a-agent-card.
- Example: examples/simple-agent-api/app/main.py and examples/simple-agent-api/app/a2a.py.
