"""Unit tests for the pre-render environment checks (``commands/_sync_preflight.py``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook import bundled_content
from coding_agent_playbook.bundled_content import DEPRECATED_PACK_NAMESPACE, PLUGIN_NAMESPACE
from coding_agent_playbook.commands import _sync_preflight
from coding_agent_playbook.commands._sync_preflight import (
    UnusableOverlay,
    bundled_plugins,
    missing_adapters,
    report_unusable_overlays,
    unusable_overlays,
    warn_missing_adapters,
)
from tests.plugins.superpowers_expectations import PLUGIN_NAME

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


def _names(problems: Sequence[UnusableOverlay]) -> list[str]:
    return [problem.name for problem in problems]


def test_unusable_overlays_lists_unimportable_names_in_order() -> None:
    names = ["coding_agent_playbook", "no_such_overlay_b", PLUGIN_NAME, "no_such_overlay_a"]
    problems = unusable_overlays(names)
    assert _names(problems) == ["no_such_overlay_b", "no_such_overlay_a"]
    assert [problem.reason for problem in problems] == ["not importable", "not importable"]


def test_unusable_overlays_treats_invalid_names_as_not_importable() -> None:
    """A hyphenated distribution name or a dotted path under a missing parent
    is not importable — it must not crash ``find_spec``."""
    names = ["playbook-rules-bnp", "no_such_parent.child", ""]
    assert _names(unusable_overlays(names)) == names


@pytest.mark.parametrize("name", ["json", "os"])
def test_no_resources_reason_for_third_party(name: str) -> None:
    """It would contribute nothing, exactly like an unimportable one; no plugin hint."""
    (problem,) = unusable_overlays([name])
    assert problem.name == name
    assert problem.reason == _sync_preflight._NO_RESOURCES


@pytest.mark.parametrize("name", [PLUGIN_NAMESPACE, DEPRECATED_PACK_NAMESPACE])
def test_plugin_namespace_reason(name: str) -> None:
    (problem,) = unusable_overlays([name])
    # Built from the discovered list, so adding a plugin under content/ needs no
    # edit here (acceptance 5).
    assert problem.reason == (
        "the bundled plugin namespace, not a plugin (bundled plugins: "
        f"{', '.join(bundled_plugins())})"
    )


@pytest.mark.parametrize("name", [PLUGIN_NAMESPACE, DEPRECATED_PACK_NAMESPACE])
def test_plugin_namespace_never_imported(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A leftover ``packs/`` dir holding only ``__pycache__`` cannot change the result."""
    attempted_imports: list[str] = []

    def _refuse_import(module: str, package: str | None = None) -> object:
        # Recorded before raising: ``_unusable_reason`` swallows any exception
        # from ``import_module``, so the raise alone would go unnoticed.
        attempted_imports.append(module)
        raise AssertionError(f"imported {module!r}")

    # The string target: mypy rejects the attribute path (``importlib`` is not re-exported).
    monkeypatch.setattr(f"{_sync_preflight.__name__}.importlib.import_module", _refuse_import)
    (problem,) = unusable_overlays([name])
    assert attempted_imports == []
    assert problem.reason.startswith("the bundled plugin namespace, not a plugin (")


def test_bundled_plugins_are_discovered_not_hardcoded() -> None:
    plugins = bundled_plugins()
    assert PLUGIN_NAME in plugins
    assert plugins == sorted(plugins)
    assert all(name.startswith(f"{PLUGIN_NAMESPACE}.") for name in plugins)


@pytest.mark.parametrize(
    "typo",
    [
        "coding_agent_playbook.plugins.superpower",
        "coding_agent_playbook.plugin.superpowers",
        "coding-agent-playbook.plugins.superpowers",
        # Only the engine-prefix branch matches this one, and only once "-" reads as "_".
        "coding-agent-playbook.plugins.foo",
        "superpowers",
        # Deprecated alias: a typo under the old namespace gets the same hint.
        "coding_agent_playbook.packs.superpower",
    ],
)
def test_a_plugin_like_name_lists_the_bundled_plugins(typo: str) -> None:
    (problem,) = unusable_overlays([typo])
    assert problem.reason.endswith(f"(bundled plugins: {', '.join(bundled_plugins())})")


def test_bundled_plugins_is_sorted_dotted_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-exported from ``bundled_content``: identifier dirs only, sorted, never cached."""
    root = tmp_path / "content"
    (root / "core").mkdir(parents=True)
    for leaf in ("superpowers", "python_design", ".hidden", "_private", "__pycache__", "bad-name"):
        (root / "plugins" / leaf / "skills").mkdir(parents=True)
    (root / "plugins" / "README.md").write_text("stray file\n", encoding="utf-8")

    assert _sync_preflight.bundled_plugins is bundled_content.bundled_plugins
    assert bundled_plugins(root) == [
        f"{PLUGIN_NAMESPACE}.python_design",
        f"{PLUGIN_NAMESPACE}.superpowers",
    ]
    # Acceptance 5: a new plugin dir is listed and usable with no code change.
    (root / "plugins" / "new_one" / "skills").mkdir(parents=True)
    assert f"{PLUGIN_NAMESPACE}.new_one" in bundled_plugins(root)
    monkeypatch.setattr(bundled_content, "_PACKAGE_DIR", tmp_path / "src" / "coding_agent_playbook")
    assert unusable_overlays([f"{PLUGIN_NAMESPACE}.new_one"]) == []


def test_an_unrelated_name_gets_no_plugin_hint() -> None:
    (problem,) = unusable_overlays(["playbook_rules_bnpp"])
    assert problem.reason == "not importable"


# --------------------------------------------------------------------------- #
# Import-time failures: reported as a reason, never raised
# --------------------------------------------------------------------------- #


def test_a_package_that_raises_on_import_is_unusable_even_with_resources(
    make_package: Callable[..., str],
) -> None:
    """``find_spec`` alone passed it; rendering then crashed with a traceback."""
    name = make_package("cap_boom_overlay", init="raise RuntimeError('boom')\n", resources=True)
    (problem,) = unusable_overlays([name])
    assert problem.reason == "not importable (RuntimeError: boom)"


def test_a_dotted_name_whose_parent_raises_is_unusable(make_package: Callable[..., str]) -> None:
    make_package("cap_boom_parent", init="raise RuntimeError('boom parent')\n")
    name = make_package("cap_boom_parent.sub", resources=True)
    (problem,) = unusable_overlays([name])
    assert problem.reason == "not importable (RuntimeError: boom parent)"


def test_a_missing_dependency_is_named_not_mistaken_for_the_overlay(
    make_package: Callable[..., str],
) -> None:
    name = make_package("cap_dep_overlay", init="import cap_no_such_dependency\n", resources=True)
    (problem,) = unusable_overlays([name])
    assert problem.reason == (
        "not importable (ModuleNotFoundError: No module named 'cap_no_such_dependency')"
    )


def test_an_importable_package_with_resources_is_usable(make_package: Callable[..., str]) -> None:
    assert unusable_overlays([make_package("cap_ok_overlay", resources=True)]) == []


def test_an_empty_name_is_unusable_not_a_crash() -> None:
    (problem,) = unusable_overlays([""])
    assert problem.reason == "not importable (ValueError: Empty module name)"


def test_a_problem_renders_as_name_and_reason() -> None:
    assert str(UnusableOverlay("org_overlay", "not importable")) == "org_overlay: not importable"


def test_missing_adapters_is_sorted_set_difference() -> None:
    assert missing_adapters(["z", "continue", "a", "a"], ["continue", "agents_md"]) == ["a", "z"]
    assert missing_adapters([], ["continue"]) == []


def test_report_unusable_overlays_names_package_reason_and_fix(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_unusable_overlays(
        [UnusableOverlay("org_overlay", "not importable"), UnusableOverlay("json", "no res")]
    )
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "\n  org_overlay: not importable\n  json: no res\n" in err
    assert "nothing\nwas written" in err
    assert "additional_dependencies" in err
    assert "language: system" in err


def test_warn_missing_adapters_names_adapter(capsys: pytest.CaptureFixture[str]) -> None:
    warn_missing_adapters(["codex"])
    err = capsys.readouterr().err
    assert err.startswith("warning: ")
    assert "codex" in err
