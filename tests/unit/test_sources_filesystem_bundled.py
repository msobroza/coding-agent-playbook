"""Bundled layers (the engine and the bundled plugins) resolve through ``catalog``.

``sources.filesystem._resource_subdir`` reads the engine's ``catalog/core/`` and
each ``catalog/plugins/<leaf>/`` straight from the catalog root, never through
``importlib.resources``. Third-party overlays keep the ``<pkg>/resources/<kind>``
contract, including a namespace overlay whose ``resources/`` spans two portions.
The preflight (``_sync_preflight.unusable_overlays``) accepts a bundled plugin
under either namespace by checking the catalog tree, without importing it.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook import catalog
from coding_agent_playbook.catalog import ENGINE_PACKAGE, CatalogMissingError
from coding_agent_playbook.commands._sync_preflight import unusable_overlays
from coding_agent_playbook.evals.prompting import _infer_prompts_dir
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource, _resource_subdir
from tests._catalog import CORE_ROOT, plugin_root

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SUPERPOWERS_PACK_NAME = "coding_agent_playbook.packs.superpowers"
_SUPERPOWERS_PLUGIN_NAME = "coding_agent_playbook.plugins.superpowers"
_DEMO_PLUGIN_NAME = "coding_agent_playbook.plugins.demo"
#: The shipped task copied into the synthetic plugin, and the prompt it names.
_SHIPPED_TASK_ID = "explain-pure-function"
_SHIPPED_PROMPT_FILE = "explain.md"
_ENGINE_RULE_COUNT = 13
_SUPERPOWERS_SKILL_COUNT = 15


def test_engine_rules_come_from_catalog_core(tmp_path: Path) -> None:
    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()
    engine_rules = [rule for rule in rules if rule.source_package == ENGINE_PACKAGE]
    assert len(engine_rules) == _ENGINE_RULE_COUNT
    rules_root = (CORE_ROOT / "rules").resolve()
    for rule in engine_rules:
        assert rule.source_path is not None
        assert rule.source_path.resolve().is_relative_to(rules_root), rule.source_path


def test_pack_names_resolve_to_catalog_plugins(tmp_path: Path) -> None:
    source = FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=[_SUPERPOWERS_PACK_NAME])
    skills = [s for s in source.list_skills() if s.source_package == _SUPERPOWERS_PACK_NAME]
    assert len(skills) == _SUPERPOWERS_SKILL_COUNT
    skills_root = (plugin_root("superpowers") / "skills").resolve()
    scripts_dirs = [skill.scripts_dir for skill in skills if skill.scripts_dir is not None]
    assert scripts_dirs, "no superpowers skill ships a scripts/ dir"
    for scripts_dir in scripts_dirs:
        assert scripts_dir.resolve().is_relative_to(skills_root), scripts_dir


@pytest.fixture
def forget_nsov() -> Iterator[None]:
    """Drop the ``nsov`` namespace package from ``sys.modules`` after the test."""
    yield
    sys.modules.pop("nsov", None)


def test_two_portion_namespace_overlay_still_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, forget_nsov: None
) -> None:
    """``resources/`` spans two portions; each kind dir lives wholly in one of them.

    Splitting the ``joinpath("resources", subdir)`` call in two would stringify a
    ``MultiplexedPath`` and silently drop the overlay.
    """
    rules_dir = tmp_path / "a" / "nsov" / "resources" / "rules"
    skill_dir = tmp_path / "b" / "nsov" / "resources" / "skills" / "s1"
    rules_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    (rules_dir / "r.md").write_text("---\nid: r\n---\nbody\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("---\nname: s1\n---\nbody\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "a"))
    monkeypatch.syspath_prepend(str(tmp_path / "b"))

    assert _resource_subdir("nsov", "rules") == rules_dir
    assert _resource_subdir("nsov", "skills") == skill_dir.parent


def _write_demo_catalog(catalog_dir: Path) -> Path:
    """Write a catalog root whose ``demo`` plugin ships one eval task and its prompt.

    Returns the plugin's directory. The task is a shipped one, renamed ``t1``.
    """
    (catalog_dir / "core" / "rules").mkdir(parents=True)
    plugin = catalog_dir / "plugins" / "demo"
    task_dir = plugin / "eval_tasks" / "t1"
    task_dir.mkdir(parents=True)
    (plugin / "prompts").mkdir()
    shipped = (CORE_ROOT / "eval_tasks" / _SHIPPED_TASK_ID / "task.toml").read_text("utf-8")
    renamed = shipped.replace(f'id = "{_SHIPPED_TASK_ID}"', 'id = "t1"', 1)
    assert renamed != shipped, f"no id line to rename in the shipped {_SHIPPED_TASK_ID} task"
    (task_dir / "task.toml").write_text(renamed, encoding="utf-8")
    prompt = (CORE_ROOT / "prompts" / _SHIPPED_PROMPT_FILE).read_text("utf-8")
    (plugin / "prompts" / _SHIPPED_PROMPT_FILE).write_text(prompt, encoding="utf-8")
    return plugin


def test_plugin_with_eval_tasks_and_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bundled plugin may ship eval tasks; each finds its plugin's own ``prompts/``."""
    plugin = _write_demo_catalog(tmp_path / "catalog")
    package_dir = tmp_path / "src" / "coding_agent_playbook"
    package_dir.mkdir(parents=True)
    monkeypatch.setattr(catalog, "_PACKAGE_DIR", package_dir)

    source = FileSystemArtifactSource(
        repo_root=tmp_path / "repo", overlay_packages=[_DEMO_PLUGIN_NAME]
    )
    tasks = {task.id: task for task in source.list_eval_tasks()}

    assert set(tasks) == {"t1"}
    assert tasks["t1"].source_package == _DEMO_PLUGIN_NAME
    source_path = tasks["t1"].source_path
    assert source_path is not None
    assert _infer_prompts_dir(source_path) == plugin / "prompts"


def test_bundled_lookup_raises_when_the_catalog_root_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bundled branch sits outside the never-raise guard: a broken install is loud."""
    monkeypatch.setattr(catalog, "_PACKAGE_DIR", tmp_path / "src" / "coding_agent_playbook")
    with pytest.raises(CatalogMissingError):
        _resource_subdir(ENGINE_PACKAGE, "rules")


def test_unusable_overlays_accepts_pack_names() -> None:
    assert unusable_overlays([_SUPERPOWERS_PACK_NAME, _SUPERPOWERS_PLUGIN_NAME]) == []
    (problem,) = unusable_overlays(["coding_agent_playbook.plugins.nope"])
    assert problem.reason.startswith("no such bundled plugin")
