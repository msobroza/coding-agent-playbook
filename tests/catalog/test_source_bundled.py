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
from coding_agent_playbook.evals.edition_pins import with_edition_line, without_edition_line
from coding_agent_playbook.evals.prompting import _infer_prompts_dir, _resolve_prompt
from coding_agent_playbook.evals.task_registry import load_layer_samples
from coding_agent_playbook.validation.preflight import unusable_overlays
from tests._catalog import CORE_ROOT, core_rule_paths, core_skill_root, plugin_root
from tests.core_skill_pins import ALL_PINS, PLAIN_CORE_SKILL_IDS
from tests.engine_version import ENGINE_VERSION

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SUPERPOWERS_PACK_NAME = "coding_agent_playbook.packs.superpowers"
_SUPERPOWERS_PLUGIN_NAME = "coding_agent_playbook.plugins.superpowers"
_DEMO_PLUGIN_NAME = "coding_agent_playbook.plugins.demo"
#: The shipped sample copied into the synthetic plugin, and the prompt it names.
_SHIPPED_SAMPLE_ID = "explain/pure-function"
_SHIPPED_PROMPT_FILE = "explain.md"
#: The id the shipped prompt declares, and the plugin sample's id (distinctive, for output scans).
_SHIPPED_PROMPT_ID = "explain"
_DEMO_SAMPLE_ID = "explain/demo-plugin-eval-sample"
_SUPERPOWERS_SKILL_COUNT = 15


def test_engine_rules_come_from_catalog_core(tmp_path: Path) -> None:
    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()
    engine_rules = [rule for rule in rules if rule.source_package == ENGINE_PACKAGE]
    # Derived from the files on disk (prU L0-03), so a content lane adding a rule edits no pin.
    assert len(engine_rules) == len(core_rule_paths())
    # prU L0-07 (D21): always rules in rules/always/, scoped rules in their skill's rules/.
    always_root = (CORE_ROOT / "rules" / "always").resolve()
    skills_root = (CORE_ROOT / "skills").resolve()
    for rule in engine_rules:
        assert rule.source_path is not None
        path = rule.source_path.resolve()
        if rule.frontmatter.scope == "always":
            assert path.is_relative_to(always_root), path
        else:
            assert path.parent.name == "rules", path
            assert path.parent.parent.parent == skills_root, path


def test_engine_skills_come_from_catalog_core(tmp_path: Path) -> None:
    skills = FileSystemArtifactSource(repo_root=tmp_path).list_skills()
    engine_skills = [skill for skill in skills if skill.source_package == ENGINE_PACKAGE]
    # Derived (prU L0-03): every core skill dir with a SKILL.md, i.e. one per pins module
    # plus the plain skills, so a content lane adding a skill edits no shared pin.
    skill_dirs = [p.parent for p in sorted((CORE_ROOT / "skills").glob("*/SKILL.md"))]
    assert len(skill_dirs) == len(ALL_PINS) + len(PLAIN_CORE_SKILL_IDS)
    assert len(engine_skills) == len(skill_dirs)
    skills_root = (CORE_ROOT / "skills").resolve()
    for skill in engine_skills:
        skill_dir = skills_root / str(skill.frontmatter["id"])
        assert (skill_dir / "SKILL.md").is_file(), (
            f"engine skill {skill_dir.name!r} has no SKILL.md"
        )
        # prU D2, D19, D25, D48: a core skill may ship references/, scripts/ and examples/.
        for name, side_dir in skill.side_dirs():
            expected = skill_dir / name if (skill_dir / name).is_dir() else None
            assert (side_dir and side_dir.resolve()) == expected, (skill_dir.name, name)


def test_core_skill_root_is_the_core_twin_of_plugin_root() -> None:
    """Script tests under tests/core_skills/<skill_snake>/ find their skill through it."""
    assert core_skill_root("python-coding") == CORE_ROOT / "skills" / "python-coding"


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
    """Write a catalog root whose ``demo`` plugin ships one eval sample and its prompt.

    Returns the plugin's directory. The sample is a shipped one, renamed
    :data:`_DEMO_SAMPLE_ID`. ``core/prompts/`` holds a second copy of the prompt
    (same id, no sample of its own), so a lookup that leaves the sample's layer finds
    the wrong file.
    """
    (catalog_dir / "core" / "rules").mkdir(parents=True)
    (catalog_dir / "core" / "prompts").mkdir()
    plugin = catalog_dir / "plugins" / "demo"
    sample_dir = plugin / "eval_samples" / _DEMO_SAMPLE_ID
    sample_dir.mkdir(parents=True)
    (plugin / "prompts").mkdir()
    shipped = (CORE_ROOT / "eval_samples" / _SHIPPED_SAMPLE_ID / "sample.toml").read_text("utf-8")
    (sample_dir / "sample.toml").write_text(_plugin_copy_of(shipped), encoding="utf-8")
    prompt = (CORE_ROOT / "prompts" / _SHIPPED_PROMPT_FILE).read_text("utf-8")
    for layer in (plugin, catalog_dir / "core"):
        (layer / "prompts" / _SHIPPED_PROMPT_FILE).write_text(prompt, encoding="utf-8")
    return plugin


def _plugin_copy_of(shipped: str) -> str:
    """The shipped core ``sample.toml`` text as the demo plugin's sample: renamed, never pinned.

    Only core samples may carry ``edition`` (``evals.sample``), and the shipped
    one carries it once an edition is frozen, so the copy drops the line.
    """
    renamed = shipped.replace(f'id = "{_SHIPPED_SAMPLE_ID}"', f'id = "{_DEMO_SAMPLE_ID}"', 1)
    assert renamed != shipped, f"no id line to rename in the shipped {_SHIPPED_SAMPLE_ID} sample"
    return without_edition_line(renamed)


def test_a_pinned_shipped_sample_copies_into_a_plugin_unpinned(tmp_path: Path) -> None:
    """Regression (#319 review): a pinned core sample copied into a plugin still loads there."""
    shipped = (CORE_ROOT / "eval_samples" / _SHIPPED_SAMPLE_ID / "sample.toml").read_text("utf-8")
    pinned = with_edition_line(without_edition_line(shipped), "v9.9.9")
    sample_dir = tmp_path / "eval_samples" / _DEMO_SAMPLE_ID
    sample_dir.mkdir(parents=True)

    (sample_dir / "sample.toml").write_text(_plugin_copy_of(pinned), encoding="utf-8")

    (sample,) = load_layer_samples(tmp_path / "eval_samples", _DEMO_PLUGIN_NAME)
    assert (sample.id, sample.edition) == (_DEMO_SAMPLE_ID, None)
    assert _plugin_copy_of(pinned) == _plugin_copy_of(shipped)


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


def test_plugin_with_eval_samples_and_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bundled plugin may ship eval samples; each finds its plugin's own ``prompts/``."""
    plugin = _use_demo_catalog(tmp_path, monkeypatch)

    source = FileSystemArtifactSource(
        repo_root=tmp_path / "repo", overlay_packages=[_DEMO_PLUGIN_NAME]
    )
    samples = {sample.id: sample for sample in source.list_eval_samples()}

    assert set(samples) == {_DEMO_SAMPLE_ID}
    sample = samples[_DEMO_SAMPLE_ID]
    assert sample.source_package == _DEMO_PLUGIN_NAME
    assert sample.source_path is not None
    assert _infer_prompts_dir(sample.source_path) == plugin / "prompts"
    prompt = _resolve_prompt(sample)
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
        f'[engine]\nversion = "{ENGINE_VERSION}"\n\n'
        '[storage]\nartifact_source = "filesystem"\nstate_source = "filesystem"\n'
    )


@pytest.mark.parametrize(
    ("overlays", "enabled"), [([_DEMO_PLUGIN_NAME], True), ([], False)], ids=["enabled", "off"]
)
def test_eval_list_shows_a_plugin_sample_only_when_the_plugin_is_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_synthetic_repo: Callable[..., Path],
    overlays: list[str],
    enabled: bool,
) -> None:
    """``playbook eval --list`` walks a bundled plugin's ``eval_samples/`` only for an enabled plugin.

    Enabled, the sample sits under the plugin's own copy of its prompt (the plugin
    layer wins the id); off, the core copy is listed with no sample at all.
    """
    _use_demo_catalog(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    make_synthetic_repo(repo, config_text=_config_text(overlays))

    assert main(["eval", "--list", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out

    assert (_DEMO_SAMPLE_ID in out) is enabled
    if enabled:
        assert f"{_SHIPPED_PROMPT_ID} (overlay {_DEMO_PLUGIN_NAME})" in out
        assert ", 1 eval sample," in out
    else:
        assert f"{_SHIPPED_PROMPT_ID} (engine)" in out
        assert _DEMO_PLUGIN_NAME not in out
        assert ", 0 eval samples," in out


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
