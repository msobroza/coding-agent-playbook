"""Shape checks shared by the ``[evals]`` config readers (``target_config``, ``endpoint_config``).

Each check raises :class:`~coding_agent_playbook.config.schema.ConfigError` naming
the file, the table, the key, the value and the expected shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.schema import ConfigError

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Keys that would hold a secret inline. Tokens come only from ``token_env``
#: (or ``token_command`` in the local file), never from a config value.
INLINE_SECRET_KEYS: Final = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "key",
        "password",
        "passwd",
        "secret",
        "auth_token",
        "access_token",
        "bearer",
        "credential",
        "credentials",
    }
)


def table(value: object, source: str, label: str) -> Mapping[str, object]:
    """``value`` if it is a table, else ``ConfigError``.

    Example::

        >>> table({}, "f.toml", "[evals]")
        {}
    """
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: {label} must be a table, got {value!r}")
    return value


def refuse_unknown_keys(
    spec: Mapping[str, object], source: str, label: str, allowed: frozenset[str]
) -> None:
    """``ConfigError`` for an inline secret key, then for any key outside ``allowed``.

    Example::

        >>> refuse_unknown_keys({"model": "m"}, "f.toml", "[evals.judge]", frozenset({"model"}))
    """
    secrets = sorted(set(spec) & INLINE_SECRET_KEYS)
    if secrets:
        raise ConfigError(
            f"{source}: {label} {secrets[0]} would put a secret in a config file; "
            'keep the token in an environment variable and name it with token_env = "<VARIABLE>"'
        )
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ConfigError(
            f"{source}: {label} has unknown key(s) {unknown}; expected only {sorted(allowed)}"
        )


def text(spec: Mapping[str, object], key: str, source: str, label: str) -> str:
    """``spec[key]`` as a non-empty string, else ``ConfigError``.

    Example::

        >>> text({"model": "m"}, "model", "f.toml", "[evals.judge]")
        'm'
    """
    value = spec[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{source}: {label} {key} must be a non-empty string, got {value!r}")
    return value


def optional_text(spec: Mapping[str, object], key: str, source: str, label: str) -> str | None:
    """:func:`text` when ``key`` is present, else ``None``.

    Example::

        >>> optional_text({}, "label", "f.toml", "[evals.targets.t]") is None
        True
    """
    return text(spec, key, source, label) if key in spec else None


def optional_count(spec: Mapping[str, object], key: str, source: str, label: str) -> int | None:
    """``spec[key]`` as an integer ``>= 1`` when present, else ``None``.

    Example::

        >>> optional_count({"runs": 3}, "runs", "f.toml", "[evals.targets.t]")
        3
    """
    if key not in spec:
        return None
    value = spec[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{source}: {label} {key} must be an integer >= 1, got {value!r}")
    return value
