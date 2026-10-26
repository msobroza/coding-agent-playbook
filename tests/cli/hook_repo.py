"""A synthetic consumer repo with hooks on, for the ``playbook sync`` hook tests (prK §C.1.3).

Plain builders, not fixtures: ``make_hook_repo`` takes the conftest's
``make_synthetic_repo`` builder and adds a ``[hooks]`` table plus two hooks:

- ``guard-x``: the sample builtin ``guard_x`` on ``pre_tool_use`` (Claude Code);
- ``guard-ext``: an external command (``sh scripts/check.sh --fast``) from the
  repo itself, allowed by ``allow_code_from``, whose script must be copied.

``hook_deps`` builds the injected machine-local seams: a :class:`FakePinWriter`,
a trust store outside the repo, no TTY and an ``ask`` that must never run.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.security.trust import TrustStore
from coding_agent_playbook.sync._machine_local import SyncHookDeps
from tests.engine_version import ENGINE_VERSION
from tests.fakes import FakePinWriter
from tests.hook_samples import write_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

CONFIG = f"""\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "{ENGINE_VERSION}"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""
HOOKS_ON = '[hooks]\nenabled = true\nallow_code_from = ["<repo-local>"]\n'
SETTINGS = ".claude/settings.json"
LAUNCHER = ".claude/hooks/playbook/launch.sh"
GUARD_CONFIG = ".coding-agent-playbook/hooks/guard_config.json"
SCRIPT = ".coding-agent-playbook/hooks/scripts/guard-ext/check.sh"
SCRIPT_BYTES = b"#!/bin/sh\nexit 0\n"


def make_hook_repo(
    root: Path,
    make_synthetic_repo: Callable[..., Path],
    *,
    hooks_table: str | None = HOOKS_ON,
    external: bool = True,
) -> Path:
    """A synthetic repo under ``root`` with ``hooks_table`` appended and the sample hooks.

    Example: ``repo = make_hook_repo(tmp_path, make_synthetic_repo, hooks_table=None)``.
    """
    config = CONFIG if hooks_table is None else f"{CONFIG}\n{hooks_table}"
    root.mkdir(parents=True, exist_ok=True)
    repo = make_synthetic_repo(root, config_text=config)
    hooks_dir = repo / "playbook" / "hooks"
    write_hook(hooks_dir, "guard-x")
    if external:
        handler = {"command": "sh", "script": "scripts/check.sh", "args": ["--fast"]}
        path = write_hook(hooks_dir, "guard-ext", scripts=True, handler=handler)
        script = path.parent / "scripts" / "check.sh"
        script.write_bytes(SCRIPT_BYTES)
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return repo


def set_hooks_table(repo: Path, table: str | None) -> None:
    """Rewrite the committed config with ``table`` (``None``: no ``[hooks]`` table)."""
    config = CONFIG if table is None else f"{CONFIG}\n{table}"
    (repo / ".coding-agent-playbook.toml").write_text(config, encoding="utf-8")


def never_ask(prompt: str) -> str:
    raise AssertionError(f"asked {prompt!r} where no prompt may run")


def hook_deps(state: Path, **overrides: Any) -> SyncHookDeps:
    """Hermetic :class:`SyncHookDeps`: fake pins, a trust store under ``state``, no TTY."""
    values: dict[str, Any] = {
        "pins": FakePinWriter(),
        "trust_store": lambda repo_root: TrustStore(state / "trust.json", repo_root=repo_root),
        "is_tty": lambda: False,
        "ask": never_ask,
        "which": lambda name: None,
    }
    values.update(overrides)
    return SyncHookDeps(**values)


def tree(
    root: Path, *, skip: tuple[str, ...] = (".coding-agent-playbook.lock",)
) -> dict[str, bytes]:
    """Every file under ``root`` (repo-relative posix path -> bytes), minus ``skip``."""
    files = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
    return {rel: path.read_bytes() for rel, path in sorted(files.items()) if rel not in skip}
