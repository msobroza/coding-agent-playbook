"""How an OpenCode run reaches a custom endpoint (spec #281 ticket 06b).

An :class:`OpenCodeRoute` is the per-run wiring for one endpoint of any API shape,
isolated from the user's own OpenCode setup:

- an inline config in ``OPENCODE_CONFIG_CONTENT`` declares one provider,
  :data:`PROVIDER_ID`, as the only enabled provider: the SDK package for the
  endpoint's API shape, the base URL, the token as an ``{env:VAR}`` reference
  (never the value), the target's model (and small model) as served model ids
  with the declared context and output limits and a zero built-in cost. A unique
  id keeps a same-named provider in the user's ``auth.json`` from shadowing it,
  and the built-in ``openai`` id would always call the Responses API;
- the child environment points ``XDG_CONFIG_HOME``, ``XDG_DATA_HOME`` and
  ``XDG_STATE_HOME`` at empty scratch directories (no global config, stored keys
  or session history), keeps Claude Code instructions out
  (``OPENCODE_DISABLE_CLAUDE_CODE``), and drops inherited OpenCode config
  variables, provider keys and base URLs, and ``OTEL_*`` export variables.

OpenCode splices an ``{env:VAR}`` value into the JSON text unescaped (and an unset
one silently becomes ``""``), so the token is checked non-empty and free of
quotes, backslashes and control characters first. This needs OpenCode 1.1.64 or
later (``{env:}`` substitution in inline config).

An :class:`OpenCodeKeyRoute` isolates a run the same way without an endpoint: the
built-in ``anthropic`` provider, reached with an API key in ``ANTHROPIC_API_KEY``
(``--record``, #329 ticket 02).
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
    API_OPENAI_CHAT,
    API_OPENAI_RESPONSES,
    AUTH_X_API_KEY,
    EndpointError,
    resolve_endpoint_headers,
    resolve_endpoint_token,
)
from coding_agent_playbook.evals.run.secret_redaction import redact_secrets, with_escaped_forms

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from coding_agent_playbook.evals.endpoints import Endpoint, TokenCommandRunner

#: The one provider an endpoint run enables; no built-in OpenCode provider uses it.
PROVIDER_ID: Final = "playbook-target"
#: The child variable that carries the token; the inline config only names it.
TOKEN_VARIABLE: Final = "PLAYBOOK_ENDPOINT_TOKEN"

#: The bundled AI SDK package that speaks each endpoint API shape.
_SDK_PACKAGES: Final = {
    API_OPENAI_CHAT: "@ai-sdk/openai-compatible",
    API_OPENAI_RESPONSES: "@ai-sdk/openai",
    API_ANTHROPIC: "@ai-sdk/anthropic",
}
#: The API version path ``@ai-sdk/anthropic`` expects at the end of its base URL.
_ANTHROPIC_VERSION_SUFFIX: Final = "/v1"
#: A zero price: results take cost from a declared target price, never from OpenCode.
_ZERO_COST: Final = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
#: Inherited variables whose name starts with one of these are dropped.
_SCRUBBED_PREFIXES: Final = ("OPENCODE_", "OTEL_", "ANTHROPIC_", "OPENAI_")
#: Inherited variables whose name ends with this are dropped (provider keys).
_SCRUBBED_SUFFIX: Final = "_API_KEY"
#: Inherited credential variables dropped by name.
_SCRUBBED_NAMES: Final = frozenset({"AWS_BEARER_TOKEN_BEDROCK"})
#: Switches every isolated run gets: no self-update, no Claude Code instructions; OpenCode reads "1".
_ISOLATED_ENV: Final = {
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",
}
#: An endpoint run also skips the models catalog fetch: its inline config declares its models.
#: A key route keeps the fetch, since its built-in provider's models come from that catalog.
_QUIET_ENV: Final = {**_ISOLATED_ENV, "OPENCODE_DISABLE_MODELS_FETCH": "1"}
#: The scratch subdirectory each XDG base variable points at.
_XDG_DIRS: Final = {"XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state"}
#: Characters an unescaped ``{env:}`` value may not hold inside a JSON string.
_JSON_BREAKERS: Final = frozenset('"\\')
#: JSON strings may not hold a raw control character (below U+0020) either.
_FIRST_PRINTABLE: Final = 0x20


@dataclass(frozen=True)
class OpenCodeRoute:
    """The wiring of one OpenCode run to ``endpoint``; build it with :func:`opencode_route`.

    ``model`` is the served model id (also its key in the inline config) and
    ``small_model`` (default ``model``) the one OpenCode uses for titles and
    summaries. ``token`` and ``headers`` are kept out of ``repr``.

    Example::

        >>> from coding_agent_playbook.evals.endpoints import Endpoint
        >>> OpenCodeRoute(Endpoint("e", "openai-chat", "https://x/v1"), "m", token="t0").model_ref
        'playbook-target/m'
    """

    endpoint: Endpoint
    model: str
    small_model: str | None = None
    token: str = field(default="", repr=False)
    headers: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def model_ref(self) -> str:
        """``<provider>/<model>``: what ``opencode run --model`` takes."""
        return f"{PROVIDER_ID}/{self.model}"

    def config(self) -> dict[str, object]:
        """The inline OpenCode config: one enabled provider, its models, no secret.

        Example::

            >>> from coding_agent_playbook.evals.endpoints import Endpoint
            >>> OpenCodeRoute(Endpoint("e", "openai-chat", "https://x/v1"), "m").config()["model"]
            'playbook-target/m'
        """
        small = self.small_model or self.model
        provider = {
            "npm": _SDK_PACKAGES[self.endpoint.api],
            "name": "playbook eval target",
            "options": self._options(),
            "models": {
                name: self._model_entry(name) for name in dict.fromkeys((self.model, small))
            },
        }
        return {
            "enabled_providers": [PROVIDER_ID],
            "model": self.model_ref,
            "small_model": f"{PROVIDER_ID}/{small}",
            "autoupdate": False,
            "provider": {PROVIDER_ID: provider},
        }

    def child_env(self, base: Mapping[str, str], scratch: Path) -> dict[str, str]:
        """``base`` scrubbed of the user's OpenCode setup, then the endpoint's wiring.

        ``scratch`` holds the per-run XDG directories (``config``, ``data``,
        ``state``). The endpoint's own token and headers variables are dropped:
        the agent gets the token once, under :data:`TOKEN_VARIABLE`.

        Example::

            >>> from coding_agent_playbook.evals.endpoints import Endpoint
            >>> route = OpenCodeRoute(Endpoint("e", "openai-chat", "https://x/v1"), "m", token="t0")
            >>> route.child_env({"OPENAI_API_KEY": "k"}, Path("/s"))[TOKEN_VARIABLE]
            't0'
        """
        dropped = {self.endpoint.token_env, self.endpoint.headers_env}
        env = {
            name: value
            for name, value in base.items()
            if not _scrubbed(name) and name not in dropped
        }
        env.update({name: str(scratch / sub) for name, sub in _XDG_DIRS.items()})
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(self.config(), sort_keys=True)
        env[TOKEN_VARIABLE] = self.token
        env.update(_QUIET_ENV)
        return env

    def redact(self, text: str) -> str:
        """``text`` with the token and the header values replaced, for transcripts and errors.

        Their JSON-escaped forms are replaced too, longest first (``secret_redaction``).

        Example::

            >>> from coding_agent_playbook.evals.endpoints import Endpoint
            >>> OpenCodeRoute(Endpoint("e", "openai-chat", "https://x"), "m", token="t0").redact("a t0")
            'a [redacted]'
        """
        return redact_secrets(text, with_escaped_forms((self.token, *self.headers.values())))

    def _options(self) -> dict[str, object]:
        """The provider options: base URL, the token reference and any extra headers."""
        options: dict[str, object] = {"baseURL": self._base_url()}
        options[self._token_option()] = "{env:" + TOKEN_VARIABLE + "}"
        if self.headers:
            options["headers"] = dict(self.headers)
        return options

    def _base_url(self) -> str:
        """The SDK base URL; an ``anthropic`` endpoint's gets the ``/v1`` it omits.

        Why: an ``anthropic`` ``base_url`` is the API root without ``/v1`` (Claude
        Code and the judge get it as ``ANTHROPIC_BASE_URL`` and add ``/v1/messages``),
        but ``@ai-sdk/anthropic`` requests ``${baseURL}/messages`` as given.
        """
        url = self.endpoint.base_url
        if self.endpoint.api != API_ANTHROPIC:
            return url
        trimmed = url.rstrip("/")
        return trimmed if trimmed.endswith(_ANTHROPIC_VERSION_SUFFIX) else trimmed + "/v1"

    def _token_option(self) -> str:
        """``authToken`` (bearer) for a bearer ``anthropic`` endpoint, else ``apiKey``."""
        if self.endpoint.api == API_ANTHROPIC and self.endpoint.auth_header != AUTH_X_API_KEY:
            return "authToken"
        return "apiKey"

    def _model_entry(self, model: str) -> dict[str, object]:
        """One declared model: its served id, zero cost and the declared limits."""
        entry: dict[str, object] = {"id": model, "name": model, "cost": dict(_ZERO_COST)}
        context, output = self.endpoint.context_tokens, self.endpoint.max_output_tokens
        if context is not None or output is not None:
            # 0 is OpenCode's own "undeclared" value for either limit.
            entry["limit"] = {"context": context or 0, "output": output or 0}
        return entry


@dataclass(frozen=True)
class OpenCodeKeyRoute:
    """An isolated OpenCode run on its built-in providers, given only an Anthropic API key.

    What a ``--record`` run without an endpoint gets (#329 ticket 02): the same
    scrubbed env and empty XDG directories as :class:`OpenCodeRoute`, so no
    personal config, stored keys, plugins or Claude Code instructions reach the
    run, and the key as ``ANTHROPIC_API_KEY``. ``model`` is sent as written
    (``anthropic/<model id>``). ``token`` is kept out of ``repr``.

    Example::

        >>> OpenCodeKeyRoute("anthropic/m", "k0").model_ref
        'anthropic/m'
    """

    model: str
    token: str = field(repr=False)

    @property
    def model_ref(self) -> str:
        """The target's model, exactly as written: what ``opencode run --model`` takes."""
        return self.model

    def child_env(self, base: Mapping[str, str], scratch: Path) -> dict[str, str]:
        """``base`` scrubbed of the user's OpenCode setup, then the scratch XDG dirs and the key.

        Example::

            >>> OpenCodeKeyRoute("anthropic/m", "k0").child_env({"OPENAI_API_KEY": "o"}, Path("/s"))
            {'XDG_CONFIG_HOME': '/s/config', 'XDG_DATA_HOME': '/s/data', 'XDG_STATE_HOME': '/s/state', 'ANTHROPIC_API_KEY': 'k0', 'OPENCODE_DISABLE_AUTOUPDATE': '1', 'OPENCODE_DISABLE_CLAUDE_CODE': '1'}
        """
        env = {name: value for name, value in base.items() if not _scrubbed(name)}
        env.update({name: str(scratch / sub) for name, sub in _XDG_DIRS.items()})
        env["ANTHROPIC_API_KEY"] = self.token
        env.update(_ISOLATED_ENV)
        return env

    def redact(self, text: str) -> str:
        """``text`` with the key and its JSON-escaped forms replaced.

        Example::

            >>> OpenCodeKeyRoute("anthropic/m", "k0").redact("a k0")
            'a [redacted]'
        """
        return redact_secrets(text, with_escaped_forms((self.token,)))


#: How an OpenCode run is isolated: through an endpoint, or on an API key.
type OpenCodeIsolation = OpenCodeRoute | OpenCodeKeyRoute


def _scrubbed(name: str) -> bool:
    return (
        name.startswith(_SCRUBBED_PREFIXES)
        or name.endswith(_SCRUBBED_SUFFIX)
        or name in _SCRUBBED_NAMES
    )


def opencode_route(
    endpoint: Endpoint,
    model: str,
    *,
    small_model: str | None = None,
    env: Mapping[str, str] | None = None,
    run_command: TokenCommandRunner | None = None,
) -> OpenCodeRoute:
    """The route to ``endpoint``, its token and headers read from ``env`` (default ``os.environ``).

    Raises :class:`~coding_agent_playbook.evals.endpoints.EndpointError` for a
    missing or empty token, a token that would corrupt the inline config, or a
    malformed header line; each names the variable, never the value.

    Example::

        >>> from coding_agent_playbook.evals.endpoints import Endpoint
        >>> opencode_route(Endpoint("e", "openai-chat", "https://x", token_env="T"), "m", env={"T": "t0"}).model
        'm'
    """
    source = os.environ if env is None else env
    token = resolve_endpoint_token(endpoint, source, run_command)
    _check_splice_safe(token, endpoint)
    raw_headers = resolve_endpoint_headers(endpoint, source)
    return OpenCodeRoute(
        endpoint=endpoint,
        model=model,
        small_model=small_model,
        token=token,
        headers=_parse_headers(raw_headers, endpoint) if raw_headers is not None else {},
    )


def _check_splice_safe(token: str, endpoint: Endpoint) -> None:
    """Refuse a token OpenCode would splice into its JSON config as broken or extra JSON."""
    if not any(char in _JSON_BREAKERS or ord(char) < _FIRST_PRINTABLE for char in token):
        return
    origin = (
        f"its token variable {endpoint.token_env}"
        if endpoint.token_command is None
        else "its token_command output"
    )
    raise EndpointError(
        f"endpoint {endpoint.name!r}: {origin} holds a double quote, backslash or control "
        "character, which OpenCode would splice unescaped into its inline JSON config"
    )


def _parse_headers(raw: str, endpoint: Endpoint) -> dict[str, str]:
    """``Name: Value`` lines into a mapping; a line without a name and a colon is refused."""
    headers: dict[str, str] = {}
    for line in filter(None, (line.strip() for line in raw.splitlines())):
        name, colon, value = line.partition(":")
        if not colon or not name.strip():
            raise EndpointError(
                f"endpoint {endpoint.name!r}: its headers variable {endpoint.headers_env} "
                'has a line that is not "Name: Value"'
            )
        headers[name.strip()] = value.strip()
    return headers


@contextmanager
def routed_opencode_env(
    route: OpenCodeIsolation | None, base: Mapping[str, str] | None
) -> Iterator[dict[str, str] | None]:
    """The child env for one OpenCode process: ``base`` unrouted, else isolated.

    With a route, fresh empty XDG directories live for the block and are removed
    after it; ``base`` ``None`` then means ``os.environ``. Without one, ``base``
    is yielded unchanged (``None``: the child inherits the parent's env).

    Example::

        >>> with routed_opencode_env(None, {"PATH": "/bin"}) as env:
        ...     env
        {'PATH': '/bin'}
    """
    if route is None:
        yield None if base is None else dict(base)
        return
    with tempfile.TemporaryDirectory(prefix="playbook-opencode-") as scratch:
        root = Path(scratch)
        for sub in _XDG_DIRS.values():
            (root / sub).mkdir()
        yield route.child_env(os.environ if base is None else base, root)
