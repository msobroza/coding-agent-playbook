"""Load ``guard_config.json``, the runtime's only configuration (specs/prK-lifecycle-hooks.md §D.8).

Sync renders the file at the fixed repo-relative path
``.coding-agent-playbook/hooks/guard_config.json`` (A-C4); the runtime finds
it from the repository root it discovered, never from argv. Hooks never read
their policy from agent-editable repo files at run time (catalog principle 12),
so the file is trusted only when its sha256 equals the lockfile's entry for it
(§D.8.1). It is JSON because the hot path cannot afford ``tomllib``.

:func:`load_guard_config` never raises: a missing file, a digest mismatch, a
newer ``schema_version`` or a malformed value is a :class:`ConfigFault`, which
the failure policy turns into one ask per session (§D.4).

``allow_code_from`` and ``state_ttl_days`` are runtime keys beyond §D.8.2's
table: the runtime needs both (§B.4's entry-point gate, §D.6.1's sweep) and
cannot read ``[hooks]`` itself. K3's renderer writes them from ``[hooks]``.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.hook_runtime._config_reader import (
    Malformed,
    TableReader,
    read_small_file,
)
from coding_agent_playbook.hook_runtime._hook_records import HookRecord, parse_hook_record
from coding_agent_playbook.hook_runtime._lock_digest import expected_digest, load_toml
from coding_agent_playbook.hook_runtime._shell_wrappers import DEFAULT_RUNNER_WRAPPERS, ShellConfig
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.globs import GlobSet, compile_globs
from coding_agent_playbook.hook_runtime.policy import ENGINE_DEADLINE_CAP_MS
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime._lock_digest import TomlLoader
    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "CONFIG_FAULT_REASON",
    "GUARD_CONFIG_REL",
    "LOCKFILE_REL",
    "SUPPORTED_SCHEMA_VERSIONS",
    "ConfigFault",
    "GuardConfig",
    "HookRecord",
    "LoggingConfig",
    "load_guard_config",
]

GUARD_CONFIG_REL: Final = ".coding-agent-playbook/hooks/guard_config.json"
LOCKFILE_REL: Final = ".coding-agent-playbook.lock"
#: The ``schema_version`` range this runtime reads; additive keys need no bump.
SUPPORTED_SCHEMA_VERSIONS: Final = (1, 1)
#: Validate caps the file at 256 KiB; anything past this is not read at all.
MAX_CONFIG_BYTES: Final = 1024 * 1024
DEFAULT_STATE_TTL_DAYS: Final = 7
#: The ask the failure policy shows once per session for any fault (§D.4).
CONFIG_FAULT_REASON: Final = (
    "Playbook guard configuration is missing or changed since sync; "
    "ask the user to run playbook sync."
)

type FaultKind = Literal[
    "missing", "unreadable", "no_lock_entry", "digest_mismatch", "schema_newer", "malformed"
]


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfigFault:
    """Why the config cannot be trusted; ``detail`` never quotes file content beyond a value.

    Example: ``ConfigFault(kind="schema_newer", detail="engine older than guard_config schema 2")``.
    """

    kind: FaultKind
    detail: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LoggingConfig:
    """``guard_config.logging``: which local logs are on (§D.6.2)."""

    decisions: bool = False
    audit: bool = False
    audit_mode: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class GuardConfig:
    """The trusted, parsed ``guard_config.json``.

    ``hooks`` are the enabled hooks; ``deadlines_ms`` has every event (the
    engine cap where the file is silent); globs are compiled and folded for
    the platform; ``tables`` holds every other top-level key (the §E.0.5 pack
    tables) read-only.

    Example::

        >>> cfg = load_guard_config(repo, store)  # doctest: +SKIP
        >>> cfg.secret_paths.matches("deploy/.env")
        True
    """

    schema_version: int
    engine_version: str
    sha256: str
    hooks: Mapping[str, HookRecord]
    deadlines_ms: Mapping[EventName, int]
    unattended_ask: Literal["deny", "warn"]
    logging: LoggingConfig
    shell: ShellConfig
    path_classes: Mapping[str, GlobSet]
    secret_paths: GlobSet
    allow_code_from: frozenset[str]
    state_ttl_days: int
    tables: Mapping[str, Any]


_RUNTIME_KEYS: Final = frozenset(
    {
        "schema_version",
        "engine_version",
        "hooks",
        "deadlines_ms",
        "unattended_ask",
        "logging",
        "shell",
        "path_classes",
        "secret_path_globs",
        "allow_code_from",
        "state_ttl_days",
    }
)


def load_guard_config(
    repo: RepoInfo,
    state: StateStore | None,
    *,
    platform: str = sys.platform,
    home: str | None = None,
    load_toml: TomlLoader = load_toml,
    refresh_digest: bool = False,
) -> GuardConfig | ConfigFault:
    """The verified config of ``repo``'s worktree, or why it cannot be used.

    ``state`` caches the lockfile digest (``None``: parse the lockfile every
    time); ``refresh_digest`` (``session_start``) re-parses it regardless.

    Example::

        >>> load_guard_config(repo, StateStore.for_repo(repo))  # doctest: +SKIP
        GuardConfig(schema_version=1, ...)
    """
    root = Path(repo.worktree_root)
    try:
        data, _ = read_small_file(root / GUARD_CONFIG_REL, MAX_CONFIG_BYTES)
    except FileNotFoundError:
        return ConfigFault(
            kind="missing", detail=f"{GUARD_CONFIG_REL} not found; run playbook sync"
        )
    except (OSError, ValueError) as exc:
        return ConfigFault(kind="unreadable", detail=f"{GUARD_CONFIG_REL}: {exc}")
    digest = hashlib.sha256(data).hexdigest()
    expected = expected_digest(
        root / LOCKFILE_REL, GUARD_CONFIG_REL, state, load_toml=load_toml, refresh=refresh_digest
    )
    if expected is None:
        return ConfigFault(kind="no_lock_entry", detail=f"{LOCKFILE_REL} has no entry for it")
    if expected != digest:
        return ConfigFault(kind="digest_mismatch", detail="sha256 differs from the lock entry")
    return _parse(data, digest, platform=platform, home=home)


def _parse(
    data: bytes, digest: str, *, platform: str, home: str | None
) -> GuardConfig | ConfigFault:
    try:
        reader = TableReader(json.loads(data), "")
        version = reader.integer("schema_version", minimum=SUPPORTED_SCHEMA_VERSIONS[0])
        if version > SUPPORTED_SCHEMA_VERSIONS[1]:
            detail = f"engine older than guard_config schema {version}"
            return ConfigFault(kind="schema_newer", detail=detail)
        return _config(reader, version, digest, platform, home)
    except ValueError as exc:  # Malformed, and JSONDecodeError / UnicodeDecodeError
        detail = str(exc) if isinstance(exc, Malformed) else f"not JSON: {exc}"
        return ConfigFault(kind="malformed", detail=detail)
    except re.error as exc:  # a glob class like [z-a] compiles to an invalid regex
        return ConfigFault(kind="malformed", detail=f"invalid glob: {exc}")
    except RecursionError:  # pathologically nested JSON
        return ConfigFault(kind="malformed", detail="JSON nested too deeply")


def _config(
    reader: TableReader, version: int, digest: str, platform: str, home: str | None
) -> GuardConfig:
    hooks = reader.child("hooks", required=True)
    return GuardConfig(
        schema_version=version,
        engine_version=reader.text("engine_version", ""),
        sha256=digest,
        hooks=MappingProxyType(
            {
                hook_id: parse_hook_record(hook_id, raw, platform=platform, home=home)
                for hook_id, raw in hooks.table.items()
            }
        ),
        deadlines_ms=_deadlines(reader.child("deadlines_ms")),
        unattended_ask=_unattended_ask(reader),
        logging=_logging(reader.child("logging")),
        shell=_shell(reader.child("shell")),
        path_classes=_path_classes(reader.child("path_classes"), platform, home),
        secret_paths=compile_globs(
            reader.strings("secret_path_globs", SECRET_PATH_GLOBS), platform=platform, home=home
        ),
        allow_code_from=frozenset(reader.strings("allow_code_from", ())),
        state_ttl_days=reader.integer("state_ttl_days", DEFAULT_STATE_TTL_DAYS, minimum=1),
        tables=MappingProxyType({k: v for k, v in reader.table.items() if k not in _RUNTIME_KEYS}),
    )


def _unattended_ask(reader: TableReader) -> Literal["deny", "warn"]:
    return "warn" if reader.choice("unattended_ask", ("deny", "warn"), "deny") == "warn" else "deny"


def _deadlines(reader: TableReader) -> Mapping[EventName, int]:
    deadlines = dict(ENGINE_DEADLINE_CAP_MS)
    for name in reader.table:
        try:
            event = EventName(name)
        except ValueError:
            raise Malformed(reader.where, "expected canonical event names as keys", name) from None
        deadlines[event] = reader.integer(name, minimum=1)
    return MappingProxyType(deadlines)


def _logging(reader: TableReader) -> LoggingConfig:
    return LoggingConfig(
        decisions=reader.boolean("decisions", False),
        audit=reader.boolean("audit", False),
        audit_mode=reader.text("audit_mode", ""),
    )


def _shell(reader: TableReader) -> ShellConfig:
    return ShellConfig(
        wrapper_prefixes=reader.strings("wrapper_prefixes", ()),
        runner_wrappers=reader.strings("runner_wrappers", DEFAULT_RUNNER_WRAPPERS),
    )


def _path_classes(reader: TableReader, platform: str, home: str | None) -> Mapping[str, GlobSet]:
    return MappingProxyType(
        {
            name: compile_globs(reader.strings(name), platform=platform, home=home)
            for name in reader.table
        }
    )
