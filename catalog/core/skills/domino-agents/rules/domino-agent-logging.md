---
id: domino-agent-logging
name: Domino agent logging
description: "Log one event per request with named fields, keep prompts and answers in the trace instead of the logs, and never print."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/main.py"
  - "**/asgi.py"
  - "**/chat_app.py"
  - "**/*agent*.py"
  - "**/chat.py"
  - "**/logs.py"
  - "**/logging_config.py"
applies_if:
  domino_project: true
section: service
priority: 44
tags: [python, domino, agents, logging]
---

# Domino agent logging

The trace already holds the model's inputs and outputs and every tool call. Logs carry what the trace does not make easy to search, and nothing more:

- one event per request with the request or trace id, the message size, the tools used, the model request count and the latency, as named fields (`extra=`) in the repo's own log format;
- prompts, answers and tool arguments stay out of logs unless the README says why;
- tools and agent code log through `logging.getLogger(__name__)` and never `print`;
- a deployed agent runs at the level from settings (INFO by default): no `--debug` flag in the launch script and no DEBUG level forced at import.

The App's stdout and stderr are its log stream, and Domino keeps execution logs indefinitely and puts them in support bundles, so whatever reaches them stays readable long after the request.

## Bad Example

```python
logging.basicConfig(level=logging.DEBUG)  # at import, in every process


@agent.tool_plain
def science_line() -> str:
    print("=== science_line called ===")
    return pick_line(SCIENCE)


async def ask_agent(question: str) -> AgentAnswer:
    answer = await run(question)
    logger.info(f"question={question} answer={answer}")  # the whole conversation
    return answer
```

## Good Example

```python
logger = logging.getLogger(__name__)


async def ask_agent(question: str) -> AgentAnswer:
    started = clock()
    result = await agent.run(question, deps=deps, usage_limits=limits)
    tools = tool_names(result)
    logger.info(
        "agent request answered",
        extra={
            "request_id": current_request_id(),
            "message_chars": len(question),
            "tools": tools,
            "model_requests": result.usage().requests,
            "latency_ms": round((clock() - started) * 1000),
        },
    )
    return {"answer": result.output, "tools": tools}
```

```python
# asgi.py: the only module that reads the environment configures logging once
settings = AgentSettings()
configure_logging(settings.log_level)
app = create_app(settings)
```

## Notes

- Logging set up once in each entry point on stdout is domino-app-logging (domino-apps) and domino-job-logging (domino-jobs); keeping secrets out of logs is domino-job-logging; request ids are fastapi-request-id-logging (web-application), where the repo uses FastAPI: its middleware sets the id that `current_request_id()` reads.
- The agent example's logs.py writes JSON lines, one format among others.
- See examples/simple-agent-api/app/logs.py and examples/simple-agent-api/app.sh.
