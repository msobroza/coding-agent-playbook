---
id: domino-agent-fake-llm-tests
name: Agent tests on a fake model
description: "Pass a fake model into create_app, switch real model requests off for the run, build settings in code, and test routes through a TestClient context."
scope: scoped
section: testing
priority: 63
globs:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
  - "**/conftest.py"
  - "**/fakes.py"
applies_if:
  domino_project: true
  has_framework: ["pytest"]
tags: [python, domino, pytest]
---

# Agent tests on a fake model

Tests never call a real LLM, the Domino token endpoint or Domino itself. The model is a parameter of `create_app`: pydantic-ai's `TestModel` for shape checks, and `FunctionModel` to script which tool the model calls and what it answers. Real model requests are switched off for the whole run in `conftest.py` (`models.ALLOW_MODEL_REQUESTS = False`), so a test that forgets the fake fails instead of spending tokens. The token provider and the tracer are named fakes. Each test builds a fresh app from settings constructed in code, never from a `.env` file or the environment. Route tests use FastAPI's `TestClient` as a context manager so every lifespan runs, the A2A one included.

Cover the answer path, a 422 on a bad body, a 502 with a generic body on a model error, a 504 when the run deadline passes, the request limit tripping, and one recorded span whose only input is the question.

## Bad Example

```python
from app.main import app  # module-level app: built from the environment at import


@patch("app.agent.agent.model", "openai:chat-model")  # patches a global
def test_chat() -> None:
    response = TestClient(app).post("/chat", json={"message": "Hi"})  # needs OPENAI_API_KEY
    assert response.status_code == 200
```

## Good Example

```python
# tests/conftest.py
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import models

from app.main import create_app
from app.settings import AgentSettings
from tests.fakes import FakeTokenProvider, RecordingTracer, scripted_model

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def settings() -> AgentSettings:
    return AgentSettings(openai_api_key="test-key", run_timeout_seconds=2.0, _env_file=None)


@pytest.fixture
def tracer() -> RecordingTracer:
    return RecordingTracer()


@pytest.fixture
def client(settings: AgentSettings, tracer: RecordingTracer) -> Iterator[TestClient]:
    app = create_app(
        settings, model=scripted_model(), token_provider=FakeTokenProvider(), tracer=tracer
    )
    with TestClient(app) as client:
        yield client
```

```python
# tests/test_api.py
def test_chat_answers_with_the_scripted_tool_line(
    client: TestClient, tracer: RecordingTracer
) -> None:
    response = client.post("/chat", json={"message": "Tell me about planets"})

    assert response.status_code == 200
    assert response.json() == {"response": "science: planets orbit stars"}
    assert tracer.inputs("ask_agent") == [{"question": "Tell me about planets"}]
```

## Notes

- Overriding providers in route tests is fastapi-dependency-overrides (web-application, where the repo uses FastAPI); doubles in general are pytest-test-doubles, and the async test plugin choice is pytest (python-testing).
- Unit tests use fakes; the Domino SDK, the token endpoint and the trace store are faked as in domino-agent-fake-domino-tests.
- Another framework's fake chat model plays the same part: the fake is passed in, never patched over a global.
- Example: examples/simple-agent-api/tests/conftest.py, examples/simple-agent-api/tests/fakes.py and examples/simple-agent-api/tests/test_api.py.
