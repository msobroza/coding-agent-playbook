"""The ``[evals.endpoints.<name>]`` blocks of both config files (spec #281 ticket 06).

::

    [evals.endpoints.internal]
    api = "anthropic"                  # anthropic | openai-chat | openai-responses
    base_url = "https://llm.internal.example"
    token_env = "INTERNAL_LLM_TOKEN"   # the variable's NAME; the token is never in a file
    auth_header = "bearer"             # or "x-api-key"; anthropic endpoints only
    headers_env = "INTERNAL_LLM_HEADERS"  # optional: extra "Name: Value" lines
    context_tokens = 200000            # optional
    max_output_tokens = 8192           # optional

An endpoint may be declared in either file. The local file may also add the token
part (``token_env``, or ``token_command``, which only the local file accepts) to an
endpoint the committed file declares, and nothing else: the team's routing stays
the team's. Inline secret keys (``token``, ``api_key``, ``password`` …) are refused
in both files.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.evals.config_shapes import (
    optional_count,
    optional_text,
    refuse_unknown_keys,
    table,
    text,
)
from coding_agent_playbook.evals.endpoints import (
    API_ANTHROPIC,
    AUTH_BEARER,
    AUTH_HEADERS,
    ENDPOINT_APIS,
    Endpoint,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The token part: the only keys the local file may add to a committed endpoint.
_TOKEN_KEYS: Final = frozenset({"token_env", "token_command"})
#: The keys of a committed ``[evals.endpoints.<name>]``: no ``token_command``.
_COMMITTED_KEYS: Final = frozenset(
    {
        "api",
        "base_url",
        "token_env",
        "auth_header",
        "headers_env",
        "context_tokens",
        "max_output_tokens",
    }
)
#: The keys of a local ``[evals.endpoints.<name>]``.
_LOCAL_KEYS: Final = _COMMITTED_KEYS | {"token_command"}
#: An environment variable name, as ``token_env`` and ``headers_env`` give it.
_ENV_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_URL_SCHEMES: Final = ("http://", "https://")


def parse_endpoints(
    committed: Mapping[str, object], local: Mapping[str, object]
) -> tuple[dict[str, Endpoint], dict[str, Endpoint]]:
    """The committed endpoints, and every endpoint the local file can see, merged.

    The first map is what committed targets and the committed judge may name;
    the second adds the local file's own endpoints and its token parts.

    Example::

        >>> spec = {"api": "anthropic", "base_url": "https://x", "token_env": "T"}
        >>> parse_endpoints({"endpoints": {"e": spec}}, {})[1]["e"].token_env
        'T'
    """
    committed_specs = table(committed.get("endpoints", {}), CONFIG_FILENAME, "[evals.endpoints]")
    local_specs = table(local.get("endpoints", {}), CONFIG_LOCAL_FILENAME, "[evals.endpoints]")
    committed_endpoints = {
        name: _endpoint(name, spec, CONFIG_FILENAME, _COMMITTED_KEYS)
        for name, spec in committed_specs.items()
    }
    merged = dict(committed_endpoints)
    for name, spec in local_specs.items():
        if name in committed_endpoints:
            merged[name] = _add_token_part(committed_endpoints[name], spec)
        else:
            merged[name] = _endpoint(name, spec, CONFIG_LOCAL_FILENAME, _LOCAL_KEYS)
    return committed_endpoints, merged


def _endpoint(name: str, value: object, source: str, allowed: frozenset[str]) -> Endpoint:
    label = f"[evals.endpoints.{name}]"
    spec = table(value, source, label)
    if "token_command" in spec and "token_command" not in allowed:
        raise ConfigError(
            f"{source}: {label} token_command is accepted only in {CONFIG_LOCAL_FILENAME} "
            "(a committed command would run on every machine); use token_env here"
        )
    refuse_unknown_keys(spec, source, label, allowed)
    for key in ("api", "base_url"):
        if key not in spec:
            raise ConfigError(f"{source}: {label} needs {key}")
    api = _choice(spec, "api", ENDPOINT_APIS, source, label)
    auth_header = AUTH_BEARER
    if "auth_header" in spec:
        if api != API_ANTHROPIC:
            raise ConfigError(
                f"{source}: {label} auth_header applies to api = {API_ANTHROPIC!r} only, "
                f"got api = {api!r}"
            )
        auth_header = _choice(spec, "auth_header", AUTH_HEADERS, source, label)
    token_env, token_command = _token_part(spec, source, label)
    return Endpoint(
        name=name,
        api=api,
        base_url=_base_url(spec, source, label),
        token_env=token_env,
        token_command=token_command,
        auth_header=auth_header,
        headers_env=_env_name(spec, "headers_env", source, label),
        context_tokens=optional_count(spec, "context_tokens", source, label),
        max_output_tokens=optional_count(spec, "max_output_tokens", source, label),
        source=source,
    )


def _add_token_part(committed: Endpoint, value: object) -> Endpoint:
    """``committed`` with the local file's token part, which replaces the committed one."""
    label = f"[evals.endpoints.{committed.name}]"
    spec = table(value, CONFIG_LOCAL_FILENAME, label)
    refuse_unknown_keys(spec, CONFIG_LOCAL_FILENAME, label, _LOCAL_KEYS)
    routing = sorted(set(spec) - _TOKEN_KEYS)
    if routing:
        raise ConfigError(
            f"{CONFIG_LOCAL_FILENAME}: {label} may add only {sorted(_TOKEN_KEYS)} to the "
            f"endpoint {CONFIG_FILENAME} declares, got {routing}; change those in {CONFIG_FILENAME}"
        )
    token_env, token_command = _token_part(spec, CONFIG_LOCAL_FILENAME, label)
    return replace(committed, token_env=token_env, token_command=token_command)


def _token_part(
    spec: Mapping[str, object], source: str, label: str
) -> tuple[str | None, tuple[str, ...] | None]:
    """``(token_env, token_command)``: at most one of them, each checked."""
    if "token_env" in spec and "token_command" in spec:
        raise ConfigError(f"{source}: {label} sets token_env and token_command; keep one")
    token_env = _env_name(spec, "token_env", source, label)
    if "token_command" not in spec:
        return token_env, None
    argv = tuple(shlex.split(text(spec, "token_command", source, label)))
    return None, argv


def _choice(
    spec: Mapping[str, object], key: str, choices: tuple[str, ...], source: str, label: str
) -> str:
    value = text(spec, key, source, label)
    if value not in choices:
        raise ConfigError(f"{source}: {label} {key} must be one of {list(choices)}, got {value!r}")
    return value


def _base_url(spec: Mapping[str, object], source: str, label: str) -> str:
    value = text(spec, "base_url", source, label)
    if not value.startswith(_URL_SCHEMES):
        raise ConfigError(
            f"{source}: {label} base_url must start with http:// or https://, got {value!r}"
        )
    return value


def _env_name(spec: Mapping[str, object], key: str, source: str, label: str) -> str | None:
    value = optional_text(spec, key, source, label)
    if value is not None and not _ENV_NAME.fullmatch(value):
        raise ConfigError(
            f"{source}: {label} {key} must name an environment variable "
            f"(letters, digits, '_'), got {value!r}"
        )
    return value
