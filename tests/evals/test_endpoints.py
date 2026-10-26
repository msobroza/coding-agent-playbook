"""Endpoint tokens and URL fingerprints (``evals.endpoints``, spec #281 ticket 06)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.endpoints import (
    Endpoint,
    EndpointError,
    endpoint_fingerprint,
    resolve_endpoint_headers,
    resolve_endpoint_token,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_URL = "https://llm.internal.example/v1"


class FakeTokenCommand:
    """Stands in for a ``token_command``: records the argv, prints a fixed token."""

    def __init__(self, output: str) -> None:
        self.output = output
        self.argvs: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> str:
        self.argvs.append(list(argv))
        return self.output


def _endpoint(**overrides: object) -> Endpoint:
    fields: dict[str, object] = {"name": "internal", "api": "anthropic", "base_url": _URL}
    fields.update(overrides)
    return Endpoint(**fields)  # type: ignore[arg-type]


def test_token_comes_from_the_named_variable() -> None:
    endpoint = _endpoint(token_env="INTERNAL_LLM_TOKEN")
    assert (
        resolve_endpoint_token(endpoint, {"INTERNAL_LLM_TOKEN": " fake-token \n"}) == "fake-token"
    )


@pytest.mark.parametrize("env", [{}, {"INTERNAL_LLM_TOKEN": ""}, {"INTERNAL_LLM_TOKEN": "  "}])
def test_missing_or_empty_token_variable_names_the_variable(env: dict[str, str]) -> None:
    with pytest.raises(EndpointError, match=r"'internal'.*INTERNAL_LLM_TOKEN is unset or empty"):
        resolve_endpoint_token(_endpoint(token_env="INTERNAL_LLM_TOKEN"), env)


def test_endpoint_without_a_token_source_says_how_to_add_one() -> None:
    with pytest.raises(EndpointError, match=r"has no token: set token_env"):
        resolve_endpoint_token(_endpoint(), {})


def test_token_command_output_is_the_token() -> None:
    command = FakeTokenCommand("fake-token\n")
    endpoint = _endpoint(token_command=("llm-token", "--print"))
    assert resolve_endpoint_token(endpoint, {}, command) == "fake-token"
    assert command.argvs == [["llm-token", "--print"]]


def test_token_command_printing_nothing_is_an_error() -> None:
    endpoint = _endpoint(token_command=("llm-token",))
    with pytest.raises(EndpointError, match=r"token_command printed empty"):
        resolve_endpoint_token(endpoint, {}, FakeTokenCommand(""))


def test_headers_come_from_their_variable_when_named() -> None:
    endpoint = _endpoint(headers_env="LLM_HEADERS")
    assert resolve_endpoint_headers(endpoint, {"LLM_HEADERS": "X-Team: evals"}) == "X-Team: evals"
    with pytest.raises(EndpointError, match=r"LLM_HEADERS is unset or empty"):
        resolve_endpoint_headers(endpoint, {})


def test_fingerprint_is_short_stable_and_hides_the_url() -> None:
    fingerprint = endpoint_fingerprint(_URL)
    assert len(fingerprint) == 12
    assert "internal" not in fingerprint
    assert fingerprint == endpoint_fingerprint(_URL + "/")
    assert fingerprint != endpoint_fingerprint("https://other.example/v1")
