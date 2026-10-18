"""The D8 import policy for content core distills (specs/prS-skills-context.md 9.9, 9.15).

Core rewrites the python-best-practices collection's ideas in its own words and
leaves out what D8 drops: the tool and dependency recommendations the engine does
not adopt, and the upstream conventions an existing core rule overrides. These
gates keep a dropped recommendation from creeping back into a rule or prompt,
keep each moved topic in one owner rule, and keep the credit in step with the
distilled rules. The collection's own names are the marker regex's job
(``tests/integration/test_resources_self_contained.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import CORE_ROOT, core_markdown_sources, core_rules

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: Recommendations D8 drops: a build backend, three new test dependencies, letting
#: mypy install packages, and piping a download into a shell. A literal substring
#: scan, so a prohibition must avoid the token too.
DROPPED_RECOMMENDATIONS: Final = (
    "hatchling",
    "factory_boy",
    "pytest-randomly",
    "pytest-check",
    "--install-types",
    "| sh",
)
#: The new rules distilled from python-best-practices; later content PRs extend it.
PBP_DISTILLED_RULES: Final = frozenset(
    {"python-performance-idioms", "python-async", "python-classes-and-protocols"}
)
#: A topic that changed owner (spec 9.4.7) -> the one core rule whose body holds it.
MOVED_GUIDANCE_OWNERS: Final = (
    ("composition over inheritance", "python-classes-and-protocols"),
    ("slots=True", "python-data-shapes"),
)
_PBP_SECTION_HEADING: Final = "## Python best-practices guidance"


#: Every rule and prompt source in core: the bodies an agent reads as guidance.
_SCANNED_SOURCES: Final = core_markdown_sources("rules") + core_markdown_sources("prompts")


def _pbp_attributions_section() -> str:
    """The python-best-practices entry of core ATTRIBUTIONS.md, up to the next entry."""
    text = (CORE_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    _, found, section = text.partition(_PBP_SECTION_HEADING)
    assert found, f"core ATTRIBUTIONS.md has no {_PBP_SECTION_HEADING!r} entry"
    return section.split("\n## ", 1)[0]


@pytest.mark.parametrize("token", DROPPED_RECOMMENDATIONS)
@pytest.mark.parametrize(
    "path", _SCANNED_SOURCES, ids=lambda p: p.relative_to(CORE_ROOT).as_posix()
)
def test_core_artifacts_omit_dropped_recommendations(path: Path, token: str) -> None:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(CORE_ROOT).as_posix()
    assert token not in text, f"{rel}: recommends {token!r}, which the D8 import policy drops"


def test_policy_scan_covers_every_core_rule_and_prompt() -> None:
    """Guard against a walker that silently scans fewer files than core ships."""
    kinds = {path.relative_to(CORE_ROOT).parts[0] for path in _SCANNED_SOURCES}
    assert kinds == {"rules", "prompts"}, kinds
    unscanned = {rule.source_path for rule in core_rules().values()} - set(_SCANNED_SOURCES)
    assert not unscanned, f"core rules missing from the policy scan: {sorted(map(str, unscanned))}"


def test_core_markdown_sources_refuses_a_kind_core_does_not_ship() -> None:
    """A misspelled kind fails loudly instead of yielding a scan over nothing."""
    with pytest.raises(FileNotFoundError, match="'promts'"):
        core_markdown_sources("promts")


@pytest.mark.parametrize("rule_id", sorted(PBP_DISTILLED_RULES))
def test_core_attributions_name_every_distilled_rule(rule_id: str) -> None:
    """R5-6: a distilled rule cannot ship without its credit."""
    assert rule_id in core_rules(), (
        f"{rule_id!r} is listed as distilled but core ships no such rule"
    )
    assert rule_id in _pbp_attributions_section(), (
        f"core ATTRIBUTIONS.md's python-best-practices entry does not name {rule_id!r}"
    )


@pytest.mark.parametrize(("needle", "owner"), MOVED_GUIDANCE_OWNERS)
def test_moved_guidance_has_one_owner(needle: str, owner: str) -> None:
    """Case-insensitive, so a capitalized copy left behind in the old owner still fails."""
    holders = sorted(
        rule_id
        for rule_id, rule in core_rules().items()
        if needle.casefold() in rule.body.casefold()
    )
    assert holders == [owner], f"{needle!r} must live only in {owner}; found in {holders}"


def test_docstrings_rule_keeps_the_example_contract(tmp_path: Path) -> None:
    """D8: the usage example stays required; Google-style sections stay optional."""
    body = render_core_rule("python-docstrings", reference_probe_facts(tmp_path))
    assert "usage example" in body, "python-docstrings no longer requires a usage example"
    google = [line for line in body.splitlines() if "Google" in line]
    assert google, "python-docstrings never mentions Google-style sections"
    assert all("optional" in line for line in google), (
        f"python-docstrings must call Google-style sections optional: {google}"
    )
