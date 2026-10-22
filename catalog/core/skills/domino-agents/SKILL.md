---
id: domino-agents
name: domino-agents
description: "Guides LLM agent services deployed on Domino 6.2."
playbook:
  use_when: "building, tracing, evaluating or testing an LLM agent API that runs on Domino"
  files: "Agent service code, launch script, agent config, evaluation Jobs and their tests"
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

On Domino 6.2 an LLM agent is an App with its own dashboard: its one request function is traced, and evaluation Jobs measure its quality, both during development and against production traces. App hosting basics belong to the domino-apps skill, shared project basics such as environment variables and Jobs to the domino-jobs skill, and generic web API practice to the web-application skill. Domino repos also get a runnable example agent that applies these rules end to end.

## Quick reference

- Provider keys and model endpoint hosts come from environment variables through one typed settings object, never from the agent config file, which the evaluation run publishes with the experiment.
- The rotating Domino access token is fetched asynchronously, with a timeout and a short cache, and attached by the model client on every request; the agent is never rebuilt to rotate it.
- The agent, its model, its HTTP clients and the A2A sub-app are built once per process by the app factory, and its lifespan runs the sub-app's lifespan and closes the clients.
- `add_tracing` wraps one request function with a stable parameter and return contract; credentials never pass through it.
- Development evaluations run as Jobs inside `DominoRun`; a scheduled Job scores production traces out of band, never inside the request.

```python
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
    app.include_router(chat_router)
    return app
```

## See also

domino-apps, domino-jobs, web-application, python-coding, python-testing.
