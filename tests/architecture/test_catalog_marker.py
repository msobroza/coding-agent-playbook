"""The catalog-marker guard (ADR 0009): a test that depends on skill content runs in the skill lane.

The skill lane runs only ``pytest -m catalog``, so a test module that imports
skill helpers but lacks the module-level marker would never run on the pull
request that breaks it. The first two tests check the real tree; the rest pin
the helpers in ``tests.architecture.catalog_marker`` on synthetic trees.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import pytest

from tests._catalog import REPO_ROOT
from tests.architecture.catalog_marker import (
    SKILL_HELPER_NAMES,
    SkillReach,
    UnmarkedModule,
    has_catalog_marker,
    marker_report,
    stale_exemptions,
    unlisted_skill_names,
    unmarked_skill_lane_test_modules,
    unmarked_skill_dependent_modules,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

# The guard is itself a catalog check: a skill-lane pull request must not be
# able to drop a marker without this test running (ADR 0009).
pytestmark = pytest.mark.catalog

_TESTS_ROOT = REPO_ROOT / "tests"
_MARKED = "import pytest\n\npytestmark = pytest.mark.catalog\n"


def _tree(tmp_path: Path, files: Mapping[str, str]) -> Path:
    """Write ``files`` (repo-relative path -> source) under ``tmp_path``; return its ``tests/``."""
    for relative, source in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return tmp_path / "tests"


def _offender_paths(tests_root: Path) -> list[str]:
    return [offender.path for offender in unmarked_skill_dependent_modules(tests_root)]


def test_every_skill_dependent_test_module_is_a_catalog_check() -> None:
    offenders = unmarked_skill_dependent_modules(_TESTS_ROOT)

    assert not offenders, marker_report(offenders)


def test_every_test_module_in_a_skill_lane_test_directory_is_a_catalog_check() -> None:
    offenders = unmarked_skill_lane_test_modules(_TESTS_ROOT)

    assert not offenders, marker_report(offenders)


def test_every_marker_exemption_still_applies() -> None:
    assert stale_exemptions(_TESTS_ROOT) == []


def test_an_exempted_module_is_not_reported_and_a_stale_exemption_is(tmp_path: Path) -> None:
    pins = "from tests.core_skill_pins import PINS\n"
    tests_root = _tree(
        tmp_path,
        {
            "tests/cli/test_exempt.py": pins,
            "tests/cli/test_marked.py": f"{_MARKED}{pins}",
            "tests/cli/test_plain.py": "import json\n",
        },
    )
    exemptions = {
        "tests/cli/test_exempt.py": "only adapts to core",
        "tests/cli/test_marked.py": "x",
        "tests/cli/test_plain.py": "x",
        "tests/cli/test_gone.py": "x",
    }

    assert unmarked_skill_dependent_modules(tests_root, exemptions) == []
    assert stale_exemptions(tests_root, exemptions) == [
        "tests/cli/test_gone.py: no such test module",
        "tests/cli/test_marked.py: it carries the catalog marker",
        "tests/cli/test_plain.py: it reaches no skill helper",
    ]


def test_every_catalog_helper_that_uses_skill_content_is_a_listed_skill_name() -> None:
    listed = SKILL_HELPER_NAMES["tests._catalog"]
    tree = ast.parse((_TESTS_ROOT / "_catalog.py").read_text(encoding="utf-8"))

    # A helper built on a listed name reads skill content too, so the guard
    # must count its importers: list it in SKILL_HELPER_NAMES.
    assert unlisted_skill_names(tree, listed) == []


def test_a_definition_that_uses_a_listed_name_is_unlisted_until_listed() -> None:
    tree = ast.parse(
        "ROOT = 1\n"
        "WALK: int = ROOT + 1\n"
        "def ids() -> int:\n    return ROOT\n"
        "def other() -> int:\n    return 2\n"
        "class Kit:\n    root = WALK\n"
    )

    assert unlisted_skill_names(tree, frozenset({"ROOT"})) == ["WALK", "ids"]
    assert unlisted_skill_names(tree, frozenset({"ROOT", "WALK", "ids"})) == ["Kit"]


@pytest.mark.parametrize(
    ("statement", "helper"),
    [
        ("import tests.core_skill_pins.python_tooling", "tests.core_skill_pins.python_tooling"),
        ("import tests.core_skills._references as refs", "tests.core_skills._references"),
        (
            "from tests.core_skill_pins.web_application import PINS",
            "tests.core_skill_pins.web_application",
        ),
        ("from tests import core_skill_pins", "tests.core_skill_pins"),
        ("import tests._core_skill_layout", "tests._core_skill_layout"),
        ("from tests._catalog import CORE_SKILLS_ROOT", "tests._catalog.CORE_SKILLS_ROOT"),
        ("from tests._catalog import REPO_ROOT, core_skill_root", "tests._catalog.core_skill_root"),
        ("from tests._catalog import KEPT_RULE_IDS as KEPT", "tests._catalog.KEPT_RULE_IDS"),
        ("from tests._catalog import _parsed_core_rules", "tests._catalog._parsed_core_rules"),
        ("from tests._catalog import core_skill_ids", "tests._catalog.core_skill_ids"),
        ("from tests._catalog import core_rule_skill_ids", "tests._catalog.core_rule_skill_ids"),
        ("from tests._catalog import core_rules", "tests._catalog.core_rules"),
        ("from tests._catalog import core_rule_paths", "tests._catalog.core_rule_paths"),
        ("from tests._catalog import core_skills", "tests._catalog.core_skills"),
        ("from tests._catalog import *", "tests._catalog"),
        ("import tests._catalog as catalog", "tests._catalog"),
        ("from tests import _catalog", "tests._catalog"),
        (
            "def test_x() -> None:\n    from tests.core_skills import _references",
            "tests.core_skills",
        ),
    ],
)
def test_each_import_form_of_a_skill_helper_is_found(
    tmp_path: Path, statement: str, helper: str
) -> None:
    tests_root = _tree(tmp_path, {"tests/unit/test_x.py": f"{statement}\n"})

    assert unmarked_skill_dependent_modules(tests_root) == [
        UnmarkedModule("tests/unit/test_x.py", SkillReach(helper, ()))
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "import json",
        "from tests._catalog import CORE_ROOT, core_markdown_sources",
        "import tests.core_skills_extra",
        "from tests.cli import skill_kit",
        "from coding_agent_playbook.catalog import core_skills",
    ],
)
def test_an_import_that_reaches_no_skill_helper_is_not_reported(
    tmp_path: Path, statement: str
) -> None:
    tests_root = _tree(
        tmp_path,
        {"tests/cli/skill_kit.py": "import json\n", "tests/unit/test_x.py": f"{statement}\n"},
    )

    assert _offender_paths(tests_root) == []


def test_a_skill_helper_is_followed_through_helper_modules(tmp_path: Path) -> None:
    tests_root = _tree(
        tmp_path,
        {
            "tests/_inner.py": "from tests._catalog import KEPT_RULE_IDS\n",
            "tests/cli/_outer.py": "from .._inner import KEPT_RULE_IDS\n",
            "tests/cli/test_x.py": "from tests.cli._outer import KEPT_RULE_IDS\n",
        },
    )

    assert unmarked_skill_dependent_modules(tests_root) == [
        UnmarkedModule(
            "tests/cli/test_x.py",
            SkillReach("tests._catalog.KEPT_RULE_IDS", ("tests.cli._outer", "tests._inner")),
        )
    ]


def test_a_helper_package_init_is_followed(tmp_path: Path) -> None:
    tests_root = _tree(
        tmp_path,
        {
            "tests/kit/__init__.py": "from tests.core_skill_pins import PINS\n",
            "tests/unit/test_x.py": "from tests import kit\n",
        },
    )

    [offender] = unmarked_skill_dependent_modules(tests_root)

    assert offender.reach == SkillReach("tests.core_skill_pins", ("tests.kit",))


def test_an_import_cycle_between_helpers_ends(tmp_path: Path) -> None:
    tests_root = _tree(
        tmp_path,
        {
            "tests/_a.py": "import tests._b\n",
            "tests/_b.py": "import tests._a\nimport tests.core_skill_pins\n",
            "tests/unit/test_x.py": "import tests._a\n",
        },
    )

    [offender] = unmarked_skill_dependent_modules(tests_root)

    assert offender.reach == SkillReach("tests.core_skill_pins", ("tests._a", "tests._b"))


def test_a_helper_imported_from_a_marked_test_module_is_followed(tmp_path: Path) -> None:
    # test_a's marker covers test_a only; test_b runs test_a's imports unmarked.
    tests_root = _tree(
        tmp_path,
        {
            "tests/cli/test_a.py": f"{_MARKED}from tests._catalog import CORE_SKILLS_ROOT\n",
            "tests/cli/test_b.py": "from tests.cli.test_a import CORE_SKILLS_ROOT\n",
        },
    )

    assert unmarked_skill_dependent_modules(tests_root) == [
        UnmarkedModule(
            "tests/cli/test_b.py",
            SkillReach("tests._catalog.CORE_SKILLS_ROOT", ("tests.cli.test_a",)),
        )
    ]


def test_the_parent_package_of_an_imported_helper_is_followed(tmp_path: Path) -> None:
    tests_root = _tree(
        tmp_path,
        {
            "tests/kit/__init__.py": "import tests.core_skill_pins\n",
            "tests/kit/sub.py": "import json\n",
            "tests/unit/test_x.py": "from tests.kit.sub import f\n",
        },
    )

    [offender] = unmarked_skill_dependent_modules(tests_root)

    assert offender.reach == SkillReach("tests.core_skill_pins", ("tests.kit",))


def test_a_suffix_style_test_module_is_checked_by_both_rules(tmp_path: Path) -> None:
    # pytest's default python_files also collects *_test.py.
    tests_root = _tree(
        tmp_path,
        {
            "tests/unit/pins_test.py": "import tests.core_skill_pins\n",
            "tests/core_skills/ml_data/scripts_test.py": "def test_x() -> None: ...\n",
        },
    )

    assert _offender_paths(tests_root) == ["tests/unit/pins_test.py"]
    assert [o.path for o in unmarked_skill_lane_test_modules(tests_root)] == [
        "tests/core_skills/ml_data/scripts_test.py"
    ]


def test_a_marked_skill_dependent_module_is_not_reported(tmp_path: Path) -> None:
    source = f"{_MARKED}from tests.core_skill_pins.ml_data import PINS\n"
    tests_root = _tree(tmp_path, {"tests/unit/test_x.py": source})

    assert _offender_paths(tests_root) == []


def test_a_module_under_tests_fixtures_is_ignored(tmp_path: Path) -> None:
    source = "from tests.core_skill_pins.ml_data import PINS\n"
    tests_root = _tree(tmp_path, {"tests/fixtures/sample/tests/test_x.py": source})

    assert _offender_paths(tests_root) == []


@pytest.mark.parametrize(
    ("source", "marked"),
    [
        ("pytestmark = pytest.mark.catalog", True),
        ('pytestmark = [pytest.mark.usefixtures("env"), pytest.mark.catalog]', True),
        ("pytestmark = (pytest.mark.catalog,)", True),
        ("pytestmark: list[pytest.MarkDecorator] = [pytest.mark.catalog]", True),
        ("@pytest.mark.catalog\ndef test_x() -> None: ...", False),
        ('pytestmark = pytest.mark.usefixtures("env")', False),
        ("pytestmark = pytest.mark.catalogue", False),
        ("if True:\n    pytestmark = pytest.mark.catalog", False),
        ("marks = pytest.mark.catalog", False),
    ],
)
def test_only_a_module_level_pytestmark_counts_as_the_marker(source: str, marked: bool) -> None:
    assert has_catalog_marker(ast.parse(f"import pytest\n\n{source}\n")) is marked


def test_an_unmarked_test_module_in_a_skill_lane_test_directory_is_reported(
    tmp_path: Path,
) -> None:
    tests_root = _tree(
        tmp_path,
        {
            "tests/core_skills/ml_data/test_unmarked.py": "def test_x() -> None: ...\n",
            "tests/core_skills/ml_data/test_marked.py": _MARKED,
            "tests/core_skills/ml_data/_scripts.py": "import json\n",
            "tests/core_skill_pins/test_pins.py": "def test_x() -> None: ...\n",
            "tests/core_skill_pins/ml_data.py": "PINS = {}\n",
            "tests/unit/test_elsewhere.py": "def test_x() -> None: ...\n",
        },
    )

    assert unmarked_skill_lane_test_modules(tests_root) == [
        UnmarkedModule("tests/core_skill_pins/test_pins.py", None),
        UnmarkedModule("tests/core_skills/ml_data/test_unmarked.py", None),
    ]


def test_the_report_names_the_module_the_helper_the_route_and_the_fix() -> None:
    direct = UnmarkedModule("tests/cli/test_a.py", SkillReach("tests.core_skill_pins", ()))
    through = UnmarkedModule(
        "tests/cli/test_b.py",
        SkillReach("tests._catalog.CORE_SKILLS_ROOT", ("tests._mapping", "tests._attributions")),
    )
    core = UnmarkedModule("tests/core_skills/ml_data/test_c.py", None)

    report = marker_report([direct, through, core])

    assert report.splitlines() == [
        "3 test module(s) lack the catalog marker (ADR 0009: the skill lane runs only -m catalog):",
        "- tests/cli/test_a.py: reaches tests.core_skill_pins directly",
        "- tests/cli/test_b.py: reaches tests._catalog.CORE_SKILLS_ROOT"
        " through tests._mapping -> tests._attributions",
        "- tests/core_skills/ml_data/test_c.py: sits under a skill-lane test directory",
        "Fix: add pytestmark = pytest.mark.catalog at module level"
        " (or append pytest.mark.catalog to an existing pytestmark list).",
    ]
