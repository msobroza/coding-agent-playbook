"""Eval-task loader. Parses ``eval_tasks/<id>/task.toml`` into ``EvalTask``."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.task import EvalTask

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def discover_eval_task_dirs(root: Path) -> Iterator[Path]:
    """Yield each ``<root>/<id>/`` subdir that contains a ``task.toml``.

    Skips dot-prefixed directories (``.git``, ``.cache``, ``__pycache__``, etc.)
    so accidentally nested infrastructure doesn't get loaded as tasks. Results
    are sorted alphabetically by directory name for deterministic ordering in
    ``cap eval --list`` output.

    Returns nothing (no exception) when ``root`` does not exist — overlay
    packages can ship without an ``eval_tasks/`` directory.
    """
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if (entry / "task.toml").is_file():
            yield entry


def load_eval_task_from_dir(
    task_dir: Path,
    *,
    source_package: str,
) -> EvalTask:
    """Load and parse the ``task.toml`` inside ``task_dir`` into an ``EvalTask``.

    Raises :exc:`FileNotFoundError` if ``task.toml`` is missing.

    Wraps any TOML parse error or schema violation from
    :meth:`EvalTask.from_dict` into a :exc:`ValueError` whose message embeds
    the full ``task.toml`` path so users can jump straight to the offending
    file.
    """
    task_toml = task_dir / "task.toml"
    if not task_toml.is_file():
        raise FileNotFoundError(f"no task.toml in {task_dir}")
    try:
        with task_toml.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{task_toml}: malformed TOML: {exc}") from exc
    try:
        return EvalTask.from_dict(data, source_path=task_toml, source_package=source_package)
    except ValueError as exc:
        raise ValueError(f"{task_toml}: {exc}") from exc
