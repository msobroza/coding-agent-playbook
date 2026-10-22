---
id: domino-agent-app-factory
name: Domino agent app factory
description: "Build the agent, its model, clients, token provider and traced request function once in create_app, with nothing agent-related at import."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/main.py"
  - "**/asgi.py"
  - "**/chat_app.py"
  - "**/*agent*.py"
  - "**/chat.py"
applies_if:
  domino_project: true
  has_framework: ["fastapi"]
section: service
priority: 40
tags: [python, domino, agents, fastapi]
---

# Domino agent app factory

On Domino an agent is an App: it runs on the App hosting infrastructure and gets its own dashboard. Deploy Agent, started from a run in Experiment Manager (or from the Apps view), asks for the same launch script as an App's entrypoint.

The agent, its model, the HTTP clients, the token provider, the traced request function and the A2A sub-app are built once per process inside `create_app(settings)` and stored on `app.state`; their constructors do no I/O. The lifespan enters the A2A sub-app's lifespan and closes the clients after `yield`. Nothing agent-related happens at import: no YAML read, no SDK import, no logging setup. The request function never builds an agent.

## Bad Example

```python
logging.basicConfig(level=logging.INFO)
CONFIG = yaml.safe_load(Path("agent_config.yaml").read_text(encoding="utf-8"))
agent = Agent(CONFIG["model"]["name"])  # built at import, shared by every test
app = FastAPI()


@add_tracing(name="ask_agent")
async def ask_agent(question: str) -> str:
    fresh = Agent(CONFIG["model"]["name"])  # and again on every request
    return (await fresh.run(question)).output
```

## Good Example

```python
def create_app(
    settings: AgentSettings, *, model: Model | None = None, tracer: Tracer | None = None
) -> FastAPI:
    config = load_agent_config(settings.config_path)
    token_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    tokens = build_token_provider(settings, token_client)
    model_client = build_model_client(settings, tokens)
    agent = build_agent(model or build_model(config, settings, model_client), config)
    tracer = tracer or select_tracer(settings)
    a2a_app = build_a2a_app(agent, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with a2a_app.router.lifespan_context(a2a_app):
            yield
        await model_client.aclose()
        await token_client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.state.ask = tracer.trace(REQUEST_SPAN_NAME)(make_ask(agent, AgentDeps(), config))
    app.mount("/a2a", a2a_app)
    app.include_router(chat_router)
    return app
```

`asgi.py` is the only module that reads the environment: `app = create_app(AgentSettings())`.

## Notes

- The `create_app(settings)` plus `asgi.py` split is fastapi-app-wiring and the composition root is arch-composition-root; the launch script, bind address and port are domino-app-launch-script and domino-app-bind-host-port (domino-apps).
- The launch script execs uvicorn on the ASGI module with one worker while A2A tasks live in process memory (a2a-mount-lifespan).
- A custom `/docs` route keeps a relative openapi URL, so the docs work under the App's path prefix (domino-app-relative-urls); a browser UI derives its base path from the page URL for the same reason.
- CORS comes only from an explicit allow-list in settings, empty by default for same-origin callers behind the proxy (web-cors-origins).
- The 6.2 deploy page's sample builds the agent inside the traced function on every call; build it once instead. On 6.2.0, Deploy Agent sits in the run's menu of the runs table.
- See examples/simple-agent-api/app/main.py, examples/simple-agent-api/app/asgi.py and examples/simple-agent-api/app.sh.
