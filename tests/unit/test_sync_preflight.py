"""Unit tests for the pre-render environment checks (``commands/_sync_preflight.py``)."""

from __future__ import annotations

import types
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands._sync_preflight import (
    UnusableOverlay,
    bundled_packs,
    missing_adapters,
    report_unusable_overlays,
    unusable_overlays,
    warn_missing_adapters,
)
from coding_agent_playbook.packs.superpowers import PACK_NAME

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


def _names(problems: Sequence[UnusableOverlay]) -> list[str]:
    return [problem.name for problem in problems]


def test_unusable_overlays_lists_unimportable_names_in_order() -> None:
    names = ["coding_agent_playbook", "no_such_overlay_b", PACK_NAME, "no_such_overlay_a"]
    problems = unusable_overlays(names)
    assert _names(problems) == ["no_such_overlay_b", "no_such_overlay_a"]
    assert [problem.reason for problem in problems] == ["not importable", "not importable"]


def test_unusable_overlays_treats_invalid_names_as_not_importable() -> None:
    """A hyphenated distribution name or a dotted path under a missing parent
    is not importable — it must not crash ``find_spec``."""
    names = ["playbook-rules-bnp", "no_such_parent.child", ""]
    assert _names(unusable_overlays(names)) == names


@pytest.mark.parametrize("name", ["json", "os", "coding_agent_playbook.packs"])
def test_an_importable_package_without_resources_is_unusable(name: str) -> None:
    """It would contribute nothing, exactly like an unimportable one."""
    (problem,) = unusable_overlays([name])
    assert problem.name == name
    assert problem.reason.startswith("importable, but ships no resources/ directory")


def test_bundled_packs_are_discovered_not_hardcoded() -> None:
    packs = bundled_packs()
    assert PACK_NAME in packs
    assert packs == sorted(packs)
    assert all(name.startswith("coding_agent_playbook.packs.") for name in packs)


@pytest.mark.parametrize(
    "typo",
    [
        "coding_agent_playbook.packs.superpower",
        "coding_agent_playbook.pack.superpowers",
        "coding-agent-playbook.packs.superpowers",
        # Only the engine-prefix branch matches this one, and only once "-" reads as "_".
        "coding-agent-playbook.packs.foo",
        "superpowers",
        "coding_agent_playbook.packs",
    ],
)
def test_a_pack_like_name_lists_the_bundled_packs(typo: str) -> None:
    (problem,) = unusable_overlays([typo])
    assert problem.reason.endswith(f"(bundled packs: {', '.join(bundled_packs())})")


def test_bundled_packs_lists_only_subpackages(tmp_path: Path) -> None:
    """A helper module next to the packs (``packs/_common.py``) is not a pack."""
    (tmp_path / "real_pack").mkdir()
    (tmp_path / "real_pack" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "_common.py").write_text("", encoding="utf-8")
    parent = types.ModuleType("fake_packs")
    parent.__path__ = [str(tmp_path)]

    assert bundled_packs(parent) == ["fake_packs.real_pack"]


def test_an_unrelated_name_gets_no_pack_hint() -> None:
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
