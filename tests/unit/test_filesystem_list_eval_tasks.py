"""Tests for ``FileSystemArtifactSource.list_eval_tasks`` (PR 11).

PR 5 shipped this method as a stub returning ``[]``; PR 11 makes it walk the
engine's ``catalog/core/eval_tasks/`` tree, each overlay's (a bundled plugin's
``catalog/plugins/<name>/eval_tasks/``, a third-party overlay package's
``resources/eval_tasks/``), and the consumer repo's ``playbook/eval_tasks/``.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.task import EvalTask
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


TASK_TOML_TEMPLATE = """\
id = "{task_id}"
prompt_id = "{prompt_id}"
description = "{description}"
"""


def _make_overlay_with_eval_task(
    tmp_path: Path,
    package_name: str,
    task_id: str,
    *,
    prompt_id: str = "demo",
    description: str = "An overlay task",
) -> None:
    """Create a tiny third-party overlay package with one eval task under resources/eval_tasks/."""
    pkg_dir = tmp_path / package_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    task_dir = pkg_dir / "resources" / "eval_tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(
        TASK_TOML_TEMPLATE.format(task_id=task_id, prompt_id=prompt_id, description=description),
        encoding="utf-8",
    )
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
    if package_name in sys.modules:
        importlib.reload(sys.modules[package_name])


@pytest.fixture
def overlay_cleanup(tmp_path: Path) -> Iterator[None]:
    yield
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))
    for mod_name in list(sys.modules):
        if mod_name.startswith("temp_eval_overlay"):
            del sys.modules[mod_name]


def test_list_eval_tasks_walks_engine_resources(tmp_path: Path) -> None:
    """The engine ships eval tasks under ``catalog/core/eval_tasks/``
    (resolved through ``catalog``). Confirm
    the walker picks them up and tags them with
    ``source_package="coding_agent_playbook"``."""
    source = FileSystemArtifactSource(repo_root=tmp_path)
    tasks = source.list_eval_tasks()
    engine_tasks = [t for t in tasks if t.source_package == "coding_agent_playbook"]
    assert engine_tasks, "expected at least one engine-shipped eval task"
    assert all(t.source_package == "coding_agent_playbook" for t in engine_tasks)


def test_list_eval_tasks_walks_overlay_packages(tmp_path: Path, overlay_cleanup: None) -> None:
    _make_overlay_with_eval_task(tmp_path, "temp_eval_overlay", "overlay-task-foo")
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_eval_overlay"],
    )
    tasks = source.list_eval_tasks()
    overlay_tasks = [t for t in tasks if t.source_package == "temp_eval_overlay"]
    assert len(overlay_tasks) == 1
    task = overlay_tasks[0]
    assert isinstance(task, EvalTask)
    assert task.id == "overlay-task-foo"


def test_list_eval_tasks_walks_repo_local(tmp_path: Path) -> None:
    task_dir = tmp_path / "playbook" / "eval_tasks" / "local-task"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        TASK_TOML_TEMPLATE.format(
            task_id="local-task", prompt_id="local-prompt", description="repo-local"
        ),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=tmp_path)
    tasks = source.list_eval_tasks()
    repo_local_tasks = [t for t in tasks if t.source_package == "<repo-local>"]
    assert len(repo_local_tasks) == 1
    assert repo_local_tasks[0].id == "local-task"


def test_list_eval_tasks_aggregates_overlay_and_repo_local(
    tmp_path: Path, overlay_cleanup: None
) -> None:
    _make_overlay_with_eval_task(tmp_path, "temp_eval_overlay2", "overlay-task-bar")
    repo_local = tmp_path / "playbook" / "eval_tasks" / "repo-task"
    repo_local.mkdir(parents=True)
    (repo_local / "task.toml").write_text(
        TASK_TOML_TEMPLATE.format(task_id="repo-task", prompt_id="p", description="repo task"),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_eval_overlay2"],
    )
    tasks = source.list_eval_tasks()
    non_engine = [t for t in tasks if t.source_package != "coding_agent_playbook"]
    ids = {t.id for t in non_engine}
    assert ids == {"overlay-task-bar", "repo-task"}
    by_id = {t.id: t for t in non_engine}
    assert by_id["overlay-task-bar"].source_package == "temp_eval_overlay2"
    assert by_id["repo-task"].source_package == "<repo-local>"
