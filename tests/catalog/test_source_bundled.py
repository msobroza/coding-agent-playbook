"""Bundled layers (the engine and the bundled plugins) resolve through ``catalog``.

``catalog.source._resource_subdir`` reads the engine's ``catalog/core/`` and
each ``catalog/plugins/<leaf>/`` straight from the catalog root, never through
``importlib.resources``. Third-party overlays keep the ``<pkg>/resources/<kind>``
contract, including a namespace overlay whose ``resources/`` spans two portions.
The preflight (``validation.preflight.unusable_overlays``) accepts a bundled plugin
under either namespace by checking the catalog tree, without importing it.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog import roots as catalog
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE, CatalogMissingError
from coding_agent_playbook.catalog.source import FileSystemArtifactSource, _resource_subdir
from coding_agent_playbook.cli import main
from coding_agent_playbook.evals.prompting import _infer_prompts_dir, _resolve_prompt
from coding_agent_playbook.validation.preflight import unusable_overlays
from tests._catalog import CORE_ROOT, plugin_root

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SUPERPOWERS_PACK_NAME = "coding_agent_playbook.packs.superpowers"
_SUPERPOWERS_PLUGIN_NAME = "coding_agent_playbook.plugins.superpowers"
_DEMO_PLUGIN_NAME = "coding_agent_playbook.plugins.demo"
#: The shipped task copied into the synthetic plugin, and the prompt it names.
_SHIPPED_TASK_ID = "explain-pure-function"
_SHIPPED_PROMPT_FILE = "explain.md"
#: The id the shipped prompt declares, and the plugin task's id (distinctive, for output scans).
_SHIPPED_PROMPT_ID = "explain"
_DEMO_TASK_ID = "demo-plugin-eval-task"
#: Two always rules and 26 scoped rules, each scoped one a member of a core skill.
_ENGINE_RULE_COUNT = 28
#: python-coding, python-testing, python-tooling, ml-data and playbook-guardrails (spec D4).
_ENGINE_SKILL_COUNT = 5
_SUPERPOWERS_SKILL_COUNT = 15


def test_engine_rules_come_from_catalog_core(tmp_path: Path) -> None:
    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()
    engine_rules = [rule for rule in rules if rule.source_package == ENGINE_PACKAGE]
    assert len(engine_rules) == _ENGINE_RULE_COUNT
    rules_root = (CORE_ROOT / "rules").resolve()
    for rule in engine_rules:
        assert rule.source_path is not None
        assert rule.source_path.resolve().is_relative_to(rules_root), rule.source_path


def test_engine_skills_come_from_catalog_core(tmp_path: Path) -> None:
    skills = FileSystemArtifactSource(repo_root=tmp_path).list_skills()
    engine_skills = [skill for skill in skills if skill.source_package == ENGINE_PACKAGE]
    assert len(engine_skills) == _ENGINE_SKILL_COUNT
    skills_root = (CORE_ROOT / "skills").resolve()
    for skill in engine_skills:
        assert skill.references_dir is None and skill.scripts_dir is None, skill.frontmatter
        skill_md = skills_root / str(skill.frontmatter["id"]) / "SKILL.md"
        assert skill_md.is_file(), f"engine skill {skill.frontmatter['id']!r} is not {skill_md}"


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

    Returns the plugin's directory. The task is a shipped one, renamed
    :data:`_DEMO_TASK_ID`. ``core/prompts/`` holds a second copy of the prompt
    (same id, no task of its own), so a lookup that leaves the task's layer finds
    the wrong file.
    """
    (catalog_dir / "core" / "rules").mkdir(parents=True)
    (catalog_dir / "core" / "prompts").mkdir()
    plugin = catalog_dir / "plugins" / "demo"
    task_dir = plugin / "eval_tasks" / _DEMO_TASK_ID
    task_dir.mkdir(parents=True)
    (plugin / "prompts").mkdir()
    shipped = (CORE_ROOT / "eval_tasks" / _SHIPPED_TASK_ID / "task.toml").read_text("utf-8")
    renamed = shipped.replace(f'id = "{_SHIPPED_TASK_ID}"', f'id = "{_DEMO_TASK_ID}"', 1)
    assert renamed != shipped, f"no id line to rename in the shipped {_SHIPPED_TASK_ID} task"
    (task_dir / "task.toml").write_text(renamed, encoding="utf-8")
    prompt = (CORE_ROOT / "prompts" / _SHIPPED_PROMPT_FILE).read_text("utf-8")
    for layer in (plugin, catalog_dir / "core"):
        (layer / "prompts" / _SHIPPED_PROMPT_FILE).write_text(prompt, encoding="utf-8")
    return plugin


def _use_demo_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make ``<tmp_path>/catalog`` the engine's catalog (a source checkout); return the plugin dir.

    Example::

        plugin = _use_demo_catalog(tmp_path, monkeypatch)
    """
    plugin = _write_demo_catalog(tmp_path / "catalog")
    package_dir = tmp_path / "src" / "coding_agent_playbook"
    package_dir.mkdir(parents=True)
    monkeypatch.setattr(catalog, "_PACKAGE_DIR", package_dir)
    return plugin


def test_plugin_with_eval_tasks_and_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bundled plugin may ship eval tasks; each finds its plugin's own ``prompts/``."""
    plugin = _use_demo_catalog(tmp_path, monkeypatch)

    source = FileSystemArtifactSource(
        repo_root=tmp_path / "repo", overlay_packages=[_DEMO_PLUGIN_NAME]
    )
    tasks = {task.id: task for task in source.list_eval_tasks()}

    assert set(tasks) == {_DEMO_TASK_ID}
    task = tasks[_DEMO_TASK_ID]
    assert task.source_package == _DEMO_PLUGIN_NAME
    assert task.source_path is not None
    assert _infer_prompts_dir(task.source_path) == plugin / "prompts"
    prompt = _resolve_prompt(task)
    assert prompt is not None
    assert prompt.source_path == plugin / "prompts" / _SHIPPED_PROMPT_FILE


def _config_text(overlays: list[str]) -> str:
    """A minimal committed config enabling ``overlays``."""
    listed = ", ".join(f'"{name}"' for name in overlays)
    return (
        "schema_version = 1\n"
        'adapters_enabled = ["claude_code"]\n'
        f"overlays_enabled = [{listed}]\n\n"
        '[project]\nname = "synthetic"\nkind = "python-library"\n\n'
        '[engine]\nversion = "0.1.0a0"\n\n'
        '[storage]\nartifact_source = "filesystem"\nstate_source = "filesystem"\n'
    )


@pytest.mark.parametrize(
    ("overlays", "enabled"), [([_DEMO_PLUGIN_NAME], True), ([], False)], ids=["enabled", "off"]
)
def test_eval_list_shows_a_plugin_task_only_when_the_plugin_is_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_synthetic_repo: Callable[..., Path],
    overlays: list[str],
    enabled: bool,
) -> None:
    """``playbook eval --list`` walks a bundled plugin's ``eval_tasks/`` only for an enabled plugin.

    Enabled, the task sits under the plugin's own copy of its prompt (the plugin
    layer wins the id); off, the core copy is listed with no task at all.
    """
    _use_demo_catalog(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    make_synthetic_repo(repo, config_text=_config_text(overlays))

    assert main(["eval", "--list", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out

    assert (_DEMO_TASK_ID in out) is enabled
    if enabled:
        assert f"{_SHIPPED_PROMPT_ID} (overlay {_DEMO_PLUGIN_NAME})" in out
        assert ", 1 eval task," in out
    else:
        assert f"{_SHIPPED_PROMPT_ID} (engine)" in out
        assert _DEMO_PLUGIN_NAME not in out
        assert ", 0 eval tasks," in out


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
