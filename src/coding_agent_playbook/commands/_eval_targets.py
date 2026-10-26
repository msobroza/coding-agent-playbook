"""``playbook eval --targets``: list the Eval targets, where each comes from and whether it can run.

Read-only and offline: it reads the ``[evals]`` table of both config files and
looks each harness up in the ``coding_agent_playbook.runners`` group and on
``PATH`` (the runner's ``available()`` guard); it never runs a harness.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._eval_options import runner_available
from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.target_config import load_eval_settings
from coding_agent_playbook.evals.targets import BUILTIN_TARGET, target_selection

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.targets import EvalSettings, EvalTarget

_NO_TARGETS: Final = f"no eval targets configured ([evals.targets] in {CONFIG_FILENAME})"


def print_targets(repo_root: Path) -> int:
    """Print every configured target and the default a run would use; exit ``0``.

    Example::

        >>> print_targets(repo)  # doctest: +SKIP
        default: claude-opus (from .coding-agent-playbook.toml [evals] default)
        * claude-opus  harness=claude_code  model=claude-opus-5-5  from .coding-agent-playbook.toml  CLI installed  release
        0
    """
    settings = load_eval_settings(repo_root)
    selected = target_selection(settings, cli_value=None, env=os.environ)
    print(_default_line(selected))
    if not settings.targets:
        print(_NO_TARGETS)
        print(_target_line(BUILTIN_TARGET, settings, is_default=True))
        return 0
    default_name = selected[0] if selected is not None else None
    for name in sorted(settings.targets):
        target = settings.targets[name]
        print(_target_line(target, settings, is_default=name == default_name))
    return 0


def _default_line(selected: tuple[str, str] | None) -> str:
    """The run's default target: the selected spec and its source, else the built-in one."""
    if selected is None:
        return f"default: {BUILTIN_TARGET.name} ({BUILTIN_TARGET.source}: Claude Code, its default model)"
    spec, source = selected
    return f"default: {spec} (from {source})"


def _target_line(target: EvalTarget, settings: EvalSettings, *, is_default: bool) -> str:
    """One row: marker, name, harness, model, origin, CLI status, then runs/label/release."""
    parts = [
        f"{'*' if is_default else ' '} {target.name}",
        f"harness={target.harness}",
        f"model={target.display_model}",
        f"from {target.source}",
        f"CLI {_harness_status(target.harness)}",
    ]
    if target.runs is not None:
        parts.append(f"runs={target.runs}")
    if target.label is not None:
        parts.append(f"label={target.label!r}")
    if target.name in settings.release:
        parts.append("release")
    return "  ".join(parts)


def _harness_status(harness: str) -> str:
    """``installed``, ``not installed`` or ``unknown harness`` (no such runner registered)."""
    runner_cls = registry.load_runner_class(harness)
    if runner_cls is None:
        return "unknown harness"
    return "installed" if runner_available(runner_cls) else "not installed"
