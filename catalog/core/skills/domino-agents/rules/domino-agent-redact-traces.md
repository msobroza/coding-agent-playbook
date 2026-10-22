---
id: domino-agent-redact-traces
name: Domino agent secrets out of traces
description: "Pass credentials to the traced request function only through a closure or an injected collaborator, and return only the answer and tool names."
version: 1
scope: scoped
globs:
  - "**/settings.py"
  - "**/config.py"
  - "**/*token*.py"
  - "**/*auth*.py"
  - "**/llm.py"
  - "**/*agent*.py"
  - "**/tracing.py"
  - "**/chat_app.py"
  - "**/main.py"
applies_if:
  domino_project: true
section: secrets
priority: 23
tags: [python, domino, agents, security, tracing]
---

# Domino agent secrets out of traces

`add_tracing` opens a span for the decorated call and records its inputs and outputs. The Traces tab shows them to everyone who can read the experiment or the agent's dashboard, and evaluators read them back. So whatever a traced function takes as a parameter or returns is published:

- credentials reach the request function only through a closure or an injected collaborator, never as a parameter;
- return values carry the answer and the tool names, never headers, clients, raw provider responses or settings objects;
- settings print with secrets masked (`SecretStr`), so a settings object that slips into a span shows no key.

## Bad Example

```python
@add_tracing(name="ask_agent")
async def ask_agent(question: str, token: str) -> dict[str, object]:
    # The token is recorded as a span input; the headers as a span output.
    response = await call_model(question, token)
    return {"answer": response.text, "headers": dict(response.headers)}
```

## Good Example

```python
class AgentAnswer(TypedDict):
    answer: str
    tools: list[str]


def make_ask(agent: Agent[AgentDeps, str], deps: AgentDeps) -> AskAgent:
    async def ask_agent(question: str) -> AgentAnswer:
        result = await agent.run(question, deps=deps)
        return {"answer": result.output, "tools": tool_names(result)}

    return ask_agent
```

The agent's model client holds the token auth flow (domino-agent-endpoint-auth), so the traced function sees only the question.

## Notes

- User prompts and answers are recorded by design; an agent that handles personal data says so in its README.
- What goes into logs is domino-agent-logging.
- A viewer's own token inside an App is domino-app-viewer-token (domino-apps).
- See examples/simple-agent-api/app/agent.py.
