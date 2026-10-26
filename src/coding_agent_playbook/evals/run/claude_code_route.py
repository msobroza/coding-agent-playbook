"""How a Claude Code run (an agent run or the LLM judge) reaches a custom endpoint (spec #281).

A :class:`ClaudeCodeRoute` is the per-run wiring for one ``anthropic`` endpoint,
isolated from the user's own Claude Code settings and login:

- the child environment drops every inherited ``ANTHROPIC_*``, ``CLAUDE_CODE_USE_*``
  and OAuth variable (a leftover ``ANTHROPIC_API_KEY`` would be sent as a second
  auth header; a ``CLAUDE_CODE_USE_*`` switch changes the wire format), points
  ``CLAUDE_CONFIG_DIR`` at an empty scratch directory, and carries the token as
  ``ANTHROPIC_AUTH_TOKEN`` (bearer) or ``ANTHROPIC_API_KEY`` (x-api-key) only;
- non-secret routing (the base URL, and the background model in the alias slots)
  goes in ``--settings`` JSON, which outranks the scratch repo's own settings
  files. argv is visible in the process list, so the token is never put there;
- the context window and output limit, when declared, and telemetry and
  non-essential traffic switched off.

The request model is the runner's ``--model``. Without a route a run keeps the
user's personal Claude Code settings (today's behaviour).
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.endpoints import (
    API_ANTHROPIC,
    AUTH_X_API_KEY,
    EndpointError,
    resolve_endpoint_headers,
    resolve_endpoint_token,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from coding_agent_playbook.evals.endpoints import Endpoint, TokenCommandRunner

#: Inherited variables whose name starts with one of these are dropped.
_SCRUBBED_PREFIXES: Final = ("ANTHROPIC_", "CLAUDE_CODE_USE_")
#: Inherited variables dropped by name (OAuth login, Vertex region, config dir).
_SCRUBBED_NAMES: Final = frozenset({"CLAUDE_CODE_OAUTH_TOKEN", "CLOUD_ML_REGION"})
#: Switches that keep a run's traffic on the endpoint path; Claude Code reads 0 as on too.
_QUIET_ENV: Final = {
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}
#: What a redacted token reads as in a transcript or an error excerpt.
_REDACTED: Final = "[redacted]"


@dataclass(frozen=True)
class ClaudeCodeRoute:
    """The wiring of one Claude Code run to ``endpoint``; build it with :func:`claude_code_route`.

    ``model`` fills the alias slots Claude Code may fall back to, so no Anthropic
    model id reaches the endpoint; ``small_model`` (default ``model``) is the
    background model. ``token`` and ``headers`` are kept out of ``repr``.

    Example::

        >>> from coding_agent_playbook.evals.endpoints import Endpoint
        >>> route = ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token="t0")
        >>> route.settings_argv()[0]
        '--settings'
    """

    endpoint: Endpoint
    model: str
    small_model: str | None = None
    token: str = field(default="", repr=False)
    headers: str | None = field(default=None, repr=False)

    def settings_argv(self) -> list[str]:
        """``--settings <json>``: the base URL and the model slots, never the token.

        Example::

            >>> from coding_agent_playbook.evals.endpoints import Endpoint
            >>> ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m").settings_argv()[1]
            '{"env": {"ANTHROPIC_BASE_URL": "https://x", "ANTHROPIC_DEFAULT_HAIKU_MODEL": "m", "ANTHROPIC_DEFAULT_OPUS_MODEL": "m", "ANTHROPIC_DEFAULT_SONNET_MODEL": "m"}}'
        """
        routing = {
            "ANTHROPIC_BASE_URL": self.endpoint.base_url,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": self.small_model or self.model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": self.model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": self.model,
        }
        return ["--settings", json.dumps({"env": routing}, sort_keys=True)]

    def child_env(self, base: Mapping[str, str], config_dir: Path) -> dict[str, str]:
        """``base`` scrubbed of the user's Claude Code credentials, then the endpoint's wiring.

        The endpoint's own token and headers variables are dropped too: the agent
        gets the token once, under the name Claude Code reads.

        Example::

            >>> from coding_agent_playbook.evals.endpoints import Endpoint
            >>> route = ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token="t0")
            >>> route.child_env({"ANTHROPIC_API_KEY": "k"}, Path("/c"))["ANTHROPIC_AUTH_TOKEN"]
            't0'
        """
        dropped = {self.endpoint.token_env, self.endpoint.headers_env}
        env = {
            name: value
            for name, value in base.items()
            if not _scrubbed(name) and name not in dropped
        }
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
        env[self._token_variable()] = self.token
        env.update(self._optional_env())
        env.update(_QUIET_ENV)
        return env

    def redact(self, text: str) -> str:
        """``text`` with the token (and the header lines) replaced, for transcripts and errors.

        Example::

            >>> from coding_agent_playbook.evals.endpoints import Endpoint
            >>> ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token="t0").redact("a t0")
            'a [redacted]'
        """
        for secret in (self.token, self.headers):
            if secret:
                text = text.replace(secret, _REDACTED)
        return text

    def _token_variable(self) -> str:
        """``ANTHROPIC_API_KEY`` for an x-api-key endpoint, else ``ANTHROPIC_AUTH_TOKEN`` (bearer)."""
        if self.endpoint.auth_header == AUTH_X_API_KEY:
            return "ANTHROPIC_API_KEY"
        return "ANTHROPIC_AUTH_TOKEN"

    def _optional_env(self) -> dict[str, str]:
        """The extra headers and the declared limits, each only when set."""
        env: dict[str, str] = {}
        if self.headers is not None:
            env["ANTHROPIC_CUSTOM_HEADERS"] = self.headers
        if self.endpoint.context_tokens is not None:
            env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(self.endpoint.context_tokens)
        if self.endpoint.max_output_tokens is not None:
            env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(self.endpoint.max_output_tokens)
        return env


def _scrubbed(name: str) -> bool:
    return name.startswith(_SCRUBBED_PREFIXES) or name in _SCRUBBED_NAMES


def claude_code_route(
    endpoint: Endpoint,
    model: str,
    *,
    small_model: str | None = None,
    env: Mapping[str, str] | None = None,
    run_command: TokenCommandRunner | None = None,
) -> ClaudeCodeRoute:
    """The route to ``endpoint``, its token and headers read from ``env`` (default ``os.environ``).

    Raises :class:`~coding_agent_playbook.evals.endpoints.EndpointError` for a
    non-``anthropic`` endpoint or a missing or empty token variable.

    Example::

        >>> from coding_agent_playbook.evals.endpoints import Endpoint
        >>> claude_code_route(Endpoint("e", "anthropic", "https://x", token_env="T"), "m", env={"T": "t0"}).model
        'm'
    """
    if endpoint.api != API_ANTHROPIC:
        raise EndpointError(
            f"endpoint {endpoint.name!r} has api = {endpoint.api!r}; Claude Code speaks only "
            f"{API_ANTHROPIC!r}: use an OpenCode target for this endpoint"
        )
    source = os.environ if env is None else env
    return ClaudeCodeRoute(
        endpoint=endpoint,
        model=model,
        small_model=small_model,
        token=resolve_endpoint_token(endpoint, source, run_command),
        headers=resolve_endpoint_headers(endpoint, source),
    )


def routed_argv(argv: list[str], route: ClaudeCodeRoute | None) -> list[str]:
    """``argv``, followed by the route's ``--settings`` when there is a route.

    Example::

        >>> routed_argv(["claude", "-p", "hi"], None)
        ['claude', '-p', 'hi']
    """
    return argv if route is None else [*argv, *route.settings_argv()]


@contextmanager
def routed_env(
    route: ClaudeCodeRoute | None, base: Mapping[str, str] | None
) -> Iterator[dict[str, str] | None]:
    """The child env for one Claude Code process: ``base`` unrouted, else isolated.

    With a route, a fresh empty ``CLAUDE_CONFIG_DIR`` lives for the block and is
    removed after it; ``base`` ``None`` then means ``os.environ``. Without one,
    ``base`` is yielded unchanged (``None``: the child inherits the parent's env).

    Example::

        >>> with routed_env(None, {"PATH": "/bin"}) as env:
        ...     env
        {'PATH': '/bin'}
    """
    if route is None:
        yield None if base is None else dict(base)
        return
    with tempfile.TemporaryDirectory(prefix="playbook-claude-config-") as config_dir:
        yield route.child_env(os.environ if base is None else base, Path(config_dir))
