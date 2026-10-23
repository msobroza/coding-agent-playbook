---
id: domino-agent-run-limits
name: Domino agent run limits
description: "Bound every agent run with a wall-clock deadline below the App proxy's read timeout and a cap on model requests, both from the agent config."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/main.py"
  - "**/asgi.py"
  - "**/chat_app.py"
  - "**/*agent*.py"
  - "**/chat.py"
  - "**/evals/**/*.py"
applies_if:
  domino_project: true
section: service
priority: 42
tags: [python, domino, agents]
---

# Domino agent run limits

One agent run can loop over tool and model calls for as long as the model keeps asking. Each run therefore gets two bounds, both read from the agent config:

- a wall-clock deadline below the App proxy's read timeout (300 seconds by default, and admins can change it), so the caller gets the agent's own error instead of a proxy timeout;
- a cap on model requests (pydantic-ai `UsageLimits(request_limit=...)`, or the framework's own iteration cap), so a tool loop stops early.

The route's error table turns an exceeded deadline into 504 and an exceeded limit into 502 (domino-agent-chat-endpoint). The model client keeps its own per-call timeout as well.

## Bad Example

```python
async def ask_agent(question: str) -> AgentAnswer:
    # No deadline, no request cap: a tool loop runs until the proxy gives up.
    result = await agent.run(question)
    return {"answer": result.output, "tools": tool_names(result)}
```

## Good Example

```python
def make_ask(agent: Agent[AgentDeps, str], deps: AgentDeps, config: AgentConfig) -> AskAgent:
    limits = UsageLimits(request_limit=config.request_limit)

    async def ask_agent(question: str) -> AgentAnswer:
        result = await asyncio.wait_for(
            agent.run(question, deps=deps, usage_limits=limits),
            timeout=config.timeout_seconds,
        )
        return {"answer": result.output, "tools": tool_names(result)}

    return ask_agent
```

```yaml
# agent_config.yaml
request_limit: 8
timeout_seconds: 120
```

## Notes

- On Python 3.11 and later, `async with asyncio.timeout(...)` is the idiomatic form of the same deadline.
- Token limits (`UsageLimits(total_tokens_limit=...)`) cap cost as well.
- Work that needs minutes, such as bulk scoring or ingestion, runs as a Job, never inside a request (domino-app-proxy-limits, domino-apps; domino-launch-jobs-from-code, domino-jobs).
- See examples/simple-agent-api/app/agent.py.
