"""Shared fixtures: settings built in code, a fresh app on a fake model, and a live client.

Real model requests are switched off for the whole run, so a test that forgets the
fake model fails instead of calling a provider. Async tests run on asyncio through
anyio's pytest plugin.
"""

import random
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import models

from app.main import create_app
from app.settings import AgentSettings
from tests.fakes import FakeTokenProvider, RecordingTracer, make_settings, scripted_model

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> AgentSettings:
    return make_settings()


@pytest.fixture
def tracer() -> RecordingTracer:
    return RecordingTracer()


@pytest.fixture
def app(settings: AgentSettings, tracer: RecordingTracer) -> FastAPI:
    return create_app(
        settings,
        model=scripted_model(),
        token_provider=FakeTokenProvider(),
        tracer=tracer,
        rng=random.Random(7),
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client inside the app's lifespan, so the A2A task worker runs too."""
    with TestClient(app) as test_client:
        yield test_client
