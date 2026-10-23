"""A skill's side dirs and the files sync withholds from them (prU D48, D58).

``scripts/``, ``references/`` and ``examples/`` are the byte-copied subtrees of
a skill. ``Skill.is_withheld`` decides whether one file is written: the most
specific ``playbook.references`` entry covering it wins, and of two entries of
one depth the withheld one wins. Kept apart from ``test_skill_fields.py`` for the
file-size budget.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.artifacts.skill import (
    SIDE_DIR_NAMES,
    ListedReference,
    Skill,
    side_dirs_at,
)


def _skill(**fields: Any) -> Skill:
    return dataclasses.replace(Skill({"id": "x"}, "", None, None, "pkg"), **fields)


def _gated(listed: tuple[str, ...] = (), withheld: tuple[str, ...] = ()) -> Skill:
    references = tuple(ListedReference(path, "When needed.") for path in listed)
    return _skill(listed_references=references, withheld_paths=withheld)


@pytest.mark.parametrize(
    ("listed", "withheld", "relative", "expected"),
    [
        pytest.param((), (), "examples/app/main.py", False, id="uncovered-file-is-written"),
        pytest.param((), ("examples/app",), "examples/app/main.py", True, id="withheld-dir"),
        pytest.param(("references/x.md",), (), "references/x.md", False, id="listed-file"),
        pytest.param(
            ("examples/app",),
            ("examples/app/slow",),
            "examples/app/slow/t.py",
            True,
            id="listed-parent-withheld-child",
        ),
        pytest.param(
            ("examples/app/core",),
            ("examples/app",),
            "examples/app/core/m.py",
            False,
            id="withheld-parent-listed-child",
        ),
        pytest.param(
            ("examples/app",),
            ("examples/app",),
            "examples/app/main.py",
            True,
            id="tie-at-one-depth-withholds",
        ),
        pytest.param((), ("examples/app",), "examples/application/main.py", False, id="prefix"),
    ],
)
def test_is_withheld_lets_the_most_specific_entry_decide(
    listed: tuple[str, ...], withheld: tuple[str, ...], relative: str, expected: bool
) -> None:
    assert _gated(listed, withheld).is_withheld(relative) is expected


def test_side_dirs_name_each_subtree_in_write_order() -> None:
    skill = _skill(scripts_dir=Path("s/scripts"), examples_dir=Path("s/examples"))

    assert skill.side_dirs() == (
        ("scripts", Path("s/scripts")),
        ("references", None),
        ("examples", Path("s/examples")),
    )
    assert tuple(name for name, _ in skill.side_dirs()) == SIDE_DIR_NAMES
    assert skill.side_dir("examples") == Path("s/examples")


def test_side_dir_rejects_an_unknown_name_naming_it_and_the_allowed_names() -> None:
    with pytest.raises(ValueError, match=r"'rules'.*scripts, references, examples"):
        _skill().side_dir("rules")  # type: ignore[arg-type]


def test_side_dir_home_is_the_parent_of_the_first_side_dir_present() -> None:
    assert _skill(references_dir=Path("s/x/references")).side_dir_home() == Path("s/x")
    assert _skill().side_dir_home() is None


def test_side_dirs_at_records_only_the_dirs_present(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "examples").write_text("not a dir", encoding="utf-8")

    assert side_dirs_at(tmp_path) == {
        "scripts_dir": tmp_path / "scripts",
        "references_dir": None,
        "examples_dir": None,
    }


def test_examples_dir_and_withheld_paths_round_trip_through_dict() -> None:
    skill = _skill(examples_dir=Path("skills/x/examples"), withheld_paths=("examples/app",))

    data = skill.to_dict()

    assert (data["examples_dir"], data["withheld_paths"]) == ("skills/x/examples", ["examples/app"])
    assert Skill.from_dict(data) == skill


def test_a_dict_without_the_new_fields_defaults_them() -> None:
    data = _skill().to_dict()
    del data["examples_dir"], data["withheld_paths"]

    restored = Skill.from_dict(data)

    assert (restored.examples_dir, restored.withheld_paths) == (None, ())
