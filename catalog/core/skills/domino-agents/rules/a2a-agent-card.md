---
id: a2a-agent-card
name: A2A agent card
description: "Declare the agent card once: skills that match the real tools, the version from the agent config, and the published App URL plus /a2a from settings."
version: 1
scope: scoped
section: a2a
priority: 61
globs:
  - "**/a2a.py"
  - "**/*agent*.py"
  - "**/main.py"
  - "**/chat_app.py"
applies_if:
  domino_project: true
  any_dependency: ["fasta2a", "a2a-sdk", "pydantic-ai", "pydantic-ai-slim"]
tags: [python, domino, a2a]
---

# A2A agent card

Orchestrators and registries pick an agent from its card, served at `/a2a/.well-known/agent-card.json`, so the card is a contract. Declare it once, in one module: its skills describe the tools or capabilities the agent really has, its version follows the agent config, and its URL is the published App URL plus `/a2a`, read from settings, because the library's default points at localhost. Registering the agent with a registry reuses the same card object instead of a second hand-written copy, and the card carries no credential.

## Bad Example

```python
a2a_app = agent.to_a2a(
    name="Assistant",
    version="1.0",  # never follows the config
    skills=[Skill(id="search", name="Web search", description="Searches the web.", tags=[])],
)  # no url: callers are told to reach localhost; the agent has no search tool

REGISTRY_ENTRY = {  # a second copy that drifts from the first
    "name": "Assistant",
    "url": "https://agents.example.com/assistant/a2a",
    "skills": [{"id": "search"}],
}
```

## Good Example

```python
from fasta2a.schema import AgentProvider, Skill
from pydantic_ai import Agent
from starlette.applications import Starlette

CARD_SKILLS: tuple[Skill, ...] = (
    Skill(
        id="science_line",
        name="Science line",
        description="Answers with one short line about a science topic.",
        tags=["science"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    ),
)


def build_a2a_app(agent: Agent[AgentDeps, str], settings: AgentSettings) -> Starlette:
    return agent.to_a2a(
        name=settings.agent_name,
        description="Answers questions with one short line.",
        version=settings.agent_config.version,
        url=f"{str(settings.public_url).rstrip('/')}/a2a",
        provider=AgentProvider(
            organization=settings.provider_organization,
            url=str(settings.provider_url),
        ),
        skills=list(CARD_SKILLS),
    )
```

```python
# settings defaults use reserved hosts only
public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8888")
provider_url: AnyHttpUrl = AnyHttpUrl("https://example.com")
```

## Notes

- The App URL is known only after the App is published, so it lives in a project environment variable read by settings (domino-env-var-names, domino-jobs).
- When a tool is added, renamed or removed, change the card's skills in the same commit; a test reads the served card and checks its URL ends in `/a2a`.
- How the card's app is mounted and started is a2a-mount-lifespan; calling another agent is a2a-client-deadlines.
- Example: examples/simple-agent-api/app/a2a.py.
