---
id: domino-agents
name: domino-agents
description: "Guides LLM agent services deployed on Domino 6.2."
playbook:
  use_when: "building, tracing, evaluating or testing an LLM agent API that runs on Domino"
  files: "Agent service, its launch script and agent config, evaluation Jobs and tests"
  sections:
    - id: secrets
      title: "Secrets and tokens"
      impact: CRITICAL
      summary: "Where provider keys and rotating Domino tokens live, how they are fetched and attached, and where they never appear."
      open_when: "Agent code handles an LLM provider key, the Domino access token for a hosted model, or an outbound Authorization header."
    - id: service
      title: "Agent service"
      impact: HIGH
      summary: "The agent as one App process: built once, a bounded chat route, run limits, conversation state and logging."
      open_when: "Agent code builds the agent, its model or HTTP clients, or edits the chat route, its time or request limits, history or logging."
    - id: configuration
      title: "Configuration"
      impact: HIGH
      summary: "One typed settings object and one agent config file whose every key takes effect."
      open_when: "The agent's settings gain a field or an in-Domino switch, or the agent config YAML, its keys or its loader change."
    - id: tracing
      title: "Tracing"
      impact: HIGH
      summary: "add_tracing on the one request function, spans autologging misses, and the 6.2 SDK names behind a seam."
      open_when: "Agent code adds, moves or renames a function under add_tracing or mlflow.trace, changes autologging, or pins the agent SDK."
    - id: evaluation
      title: "Evaluation"
      impact: HIGH
      summary: "Development evaluations as Jobs inside DominoRun, deterministic evaluators, production scoring in a scheduled Job."
      open_when: "Code writes an agent evaluator, a DominoRun evaluation script, or a Job that reads agent traces or calls log_evaluation."
    - id: a2a
      title: "A2A protocol"
      impact: MEDIUM
      summary: "Mounting the A2A app with its lifespan, publishing one agent card, and calling other agents under a deadline."
      open_when: "Code mounts agent.to_a2a, edits the agent card, or calls another agent's message/send or tasks/get."
    - id: testing
      title: "Testing"
      impact: MEDIUM
      summary: "Fakes for the model, the token endpoint and the Domino SDK, so the suite runs without Domino or a live LLM."
      open_when: "A test exercises the agent, its routes, the token provider, the tracer or an evaluation Job without Domino or a real model."
---

# Domino agents

On Domino 6.2 an LLM agent is an App with its own dashboard: one request function is traced, and evaluation Jobs measure its quality before and after it is deployed. App hosting basics belong to the domino-apps skill, shared project basics (environment variables, Jobs, datasets) to domino-jobs, and generic web practice to web-application. Domino repos also get a runnable example agent service that applies every rule below.

## Quick Reference

- Provider keys and the hosts of Domino-hosted models come from environment variables through one typed settings object; the agent config file holds only non-secret choices.
- The rotating Domino access token is fetched asynchronously, with a timeout and a cache, and attached by the model's HTTP client; the agent is never rebuilt to rotate it.
- `create_app(settings)` builds the agent, its clients and the traced request function once per process; nothing agent-related happens at import.
- `add_tracing` sits directly on the one function that handles a request; its parameter and returned keys are a contract with evaluators and dashboards.
- Development evaluations run as Jobs inside `DominoRun`; production traces are scored out of band by a scheduled Job that logs results back.

```python
from collections.abc import Awaitable, Callable

from fastapi import FastAPI


def create_app(settings: AgentSettings) -> FastAPI:
    config = load_agent_config(settings.config_path)
    agent = build_agent(build_model(config, settings), config)
    tracer = select_tracer(settings)
    ask: Callable[[str], Awaitable[AgentAnswer]] = tracer.trace(REQUEST_SPAN_NAME)(
        make_ask(agent, config)
    )
    app = FastAPI()
    app.state.ask = ask
    return app
```

## See Also

- domino-apps
- domino-jobs
- web-application
- python-coding
- python-testing
