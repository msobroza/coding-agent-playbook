"""Endpoints: a custom model server an Eval target or the judge reaches (spec #281).

An endpoint is declared once, under ``[evals.endpoints.<name>]``, and targets and
the judge refer to it by name. It names the API shape the server speaks, its base
URL and the **name** of the environment variable that holds its token; the token
itself is never in a file (``evals.endpoint_config`` rejects inline secret keys).
The local config file may instead give a ``token_command`` whose output is the token.

Results never record the URL or the token: only the endpoint's name and
:func:`endpoint_fingerprint`, a short digest of its URL, so an internal hostname
never leaks into a report or a shipped release metrics file.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

#: The API shapes an endpoint can speak. Claude Code speaks only the first.
API_ANTHROPIC: Final = "anthropic"
API_OPENAI_CHAT: Final = "openai-chat"
API_OPENAI_RESPONSES: Final = "openai-responses"
ENDPOINT_APIS: Final = (API_ANTHROPIC, API_OPENAI_CHAT, API_OPENAI_RESPONSES)

#: How an ``anthropic`` endpoint takes its token: ``Authorization: Bearer`` or ``x-api-key``.
AUTH_BEARER: Final = "bearer"
AUTH_X_API_KEY: Final = "x-api-key"
AUTH_HEADERS: Final = (AUTH_BEARER, AUTH_X_API_KEY)

#: Hex digits of the URL digest a result records.
_FINGERPRINT_CHARS: Final = 12

#: Bound on a ``token_command`` run (seconds): a password-manager prompt must not hang a run.
_TOKEN_COMMAND_TIMEOUT: Final = 30.0

#: Runs a ``token_command`` argv and returns its stdout (injected in tests).
type TokenCommandRunner = Callable[[Sequence[str]], str]


class EndpointError(ExitTwoError):
    """An endpoint that cannot be used as configured (no token, say); ``playbook`` exits 2.

    The message names the endpoint and the variable, never the token's value.

    Example::

        >>> str(EndpointError("endpoint 'internal': INTERNAL_LLM_TOKEN is not set"))
        "endpoint 'internal': INTERNAL_LLM_TOKEN is not set"
    """


@dataclass(frozen=True)
class Endpoint:
    """One ``[evals.endpoints.<name>]`` block, checked; it holds no secret.

    ``token_env`` is the name of the variable holding the token and
    ``token_command`` an argv whose output is the token (local file only); at
    most one is set. ``auth_header`` applies to ``anthropic`` endpoints only.
    ``headers_env`` names a variable holding extra ``Name: Value`` header lines.
    ``source`` is the file that declared the block.

    Example::

        >>> len(Endpoint("internal", "anthropic", "https://llm.example/v1", token_env="T").fingerprint)
        12
    """

    name: str
    api: str
    base_url: str
    token_env: str | None = None
    token_command: tuple[str, ...] | None = None
    auth_header: str = AUTH_BEARER
    headers_env: str | None = None
    context_tokens: int | None = None
    max_output_tokens: int | None = None
    source: str = ""

    @property
    def fingerprint(self) -> str:
        """:func:`endpoint_fingerprint` of :attr:`base_url`."""
        return endpoint_fingerprint(self.base_url)


def endpoint_fingerprint(base_url: str) -> str:
    """A short, stable digest of ``base_url``: results record it instead of the URL.

    A trailing ``/`` does not change it, so ``…/v1`` and ``…/v1/`` match.

    Example::

        >>> endpoint_fingerprint("https://llm.example/v1") == endpoint_fingerprint("https://llm.example/v1/")
        True
    """
    digest = hashlib.sha256(base_url.rstrip("/").encode("utf-8")).hexdigest()
    return digest[:_FINGERPRINT_CHARS]


def resolve_endpoint_token(
    endpoint: Endpoint,
    env: Mapping[str, str],
    run_command: TokenCommandRunner | None = None,
) -> str:
    """The token of ``endpoint``: ``env[token_env]``, or ``token_command``'s output.

    A missing or empty variable, an endpoint with no token source, or a command
    that fails or prints nothing raises :class:`EndpointError` naming the
    variable or the endpoint, never the value.

    Example::

        >>> resolve_endpoint_token(Endpoint("e", "anthropic", "https://x", token_env="T"), {"T": "t0"})
        't0'
    """
    if endpoint.token_command is not None:
        runner = run_command if run_command is not None else run_token_command
        return _non_empty(runner(endpoint.token_command), endpoint, "its token_command printed")
    if endpoint.token_env is None:
        raise EndpointError(
            f'endpoint {endpoint.name!r} has no token: set token_env = "<VARIABLE>" '
            "in either config file (or token_command in the local file)"
        )
    value = env.get(endpoint.token_env, "")
    return _non_empty(value, endpoint, f"its token variable {endpoint.token_env} is unset or")


def resolve_endpoint_headers(endpoint: Endpoint, env: Mapping[str, str]) -> str | None:
    """The extra header lines in ``env[headers_env]``, ``None`` when ``headers_env`` is unset.

    Example::

        >>> resolve_endpoint_headers(Endpoint("e", "anthropic", "https://x"), {}) is None
        True
    """
    if endpoint.headers_env is None:
        return None
    value = env.get(endpoint.headers_env, "")
    return _non_empty(value, endpoint, f"its headers variable {endpoint.headers_env} is unset or")


def _non_empty(value: str, endpoint: Endpoint, what: str) -> str:
    """``value`` stripped, else :class:`EndpointError` saying ``what`` was empty."""
    stripped = value.strip()
    if not stripped:
        raise EndpointError(f"endpoint {endpoint.name!r}: {what} empty")
    return stripped


def run_token_command(argv: Sequence[str]) -> str:
    """Run a ``token_command`` (no shell, bounded) and return its stdout.

    Its output is never quoted in an error: it may be part of a secret.

    Example::

        >>> run_token_command(["printf", "t0"])  # doctest: +SKIP
        't0'
    """
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=_TOKEN_COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EndpointError(
            f"token_command {argv[0]!r} could not run: {type(exc).__name__}"
        ) from None
    if completed.returncode != 0:
        raise EndpointError(f"token_command {argv[0]!r} exited {completed.returncode}")
    return completed.stdout
