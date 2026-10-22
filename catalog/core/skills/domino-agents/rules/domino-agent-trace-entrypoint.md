---
id: domino-agent-trace-entrypoint
name: Traced request function
description: "Put add_tracing directly on the one function that handles a request, with a typed parameter and return contract shared with evaluators."
version: 1
scope: scoped
globs:
  - "**/*agent*.py"
  - "**/tracing.py"
  - "**/chat_app.py"
  - "**/main.py"
applies_if:
  domino_project: true
section: tracing
priority: 47
tags: [python, domino, agents, tracing]
---

# Trace one request function with a stable contract

## Description

Exactly one function handles a user request end to end, and `add_tracing` sits directly on it, with no other decorator in between. It opens the span (a new trace when none is open) and records the function's inputs and outputs, which is what production monitoring, the Traces tab and every evaluator read back. Take the span name from one shared constant and pass `autolog_frameworks` naming the agent framework. The parameters are the request's data (the question) and the return value is a small typed mapping (answer, tools): those names and keys are a contract with evaluators and dashboards. The App and the development evaluation call the same function under the same name, so their traces compare. Collaborators (the agent, its deps and the config that holds the run limits) arrive through a closure built in the composition root, never as parameters.

## Bad Example

```python
@add_tracing(name="ask")
async def ask_agent(question, agent=AGENT):
    return await agent.run(question)  # the framework's whole result object


def dev_evaluator(span) -> dict[str, float]:
    question = span.inputs["data_point"]  # another function's parameter name
    return {"answered": float(bool(span.outputs["answer"]))}
```

The function is untyped, returns the framework's result object, and the evaluator reads keys this function never records, so it breaks silently.

## Good Example

```python
from collections.abc import Awaitable, Callable
from typing import Final, TypedDict

REQUEST_SPAN_NAME: Final = "ask_agent"


class AgentAnswer(TypedDict):
    answer: str
    tools: list[str]


AskAgent = Callable[[str], Awaitable[AgentAnswer]]


def make_ask(agent: Agent[AgentDeps, str], deps: AgentDeps, config: AgentConfig) -> AskAgent:
    limits = UsageLimits(request_limit=config.request_limit)

    async def ask_agent(question: str) -> AgentAnswer:
        result = await agent.run(question, deps=deps, usage_limits=limits)
        return {"answer": result.output, "tools": tool_names(result)}

    return ask_agent


# in create_app, once:
ask = tracer.trace(REQUEST_SPAN_NAME)(make_ask(agent, deps, config))
```

The tracer seam applies `add_tracing(name=REQUEST_SPAN_NAME, autolog_frameworks=["pydantic_ai"])` inside Domino and returns the function unchanged elsewhere.

## Notes

- Renaming the parameter or a returned key breaks the evaluators and the production Job; change them together.
- The 6.2 user guide says `add_tracing` alone captures production traces; the SDK reference also offers `init_tracing`, which needs `DOMINO_AGENT_IS_PROD` and `DOMINO_APP_ID`. Follow the user guide and check the deployment before relying on `init_tracing`.
- Secrets never become a parameter or a returned key (`domino-agent-redact-traces`); the tracer seam is `domino-agent-sdk-names`.
- See examples/simple-agent-api/app/agent.py and examples/simple-agent-api/app/tracing.py.
