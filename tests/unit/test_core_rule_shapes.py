"""Every scoped rule in core fits one reference read (specs/prS-skills-context.md 9.4.5, 9.15).

A scoped rule reaches the agent as one reference of its skill, opened in a single
read. 100 lines is the Agent Skills threshold above which a reference needs a
table of contents, and 750 words keeps one reference to one topic, so CI bounds
every core scoped rule, rendered as sync renders it with the reference-probe facts
(``tests/_budget_probe.py``). Those facts take the long branch of every Jinja
rule; the sanity test below pins that, so the bound measures the longest form.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import core_rules

if TYPE_CHECKING:
    from coding_agent_playbook.detector import Facts

pytestmark = pytest.mark.catalog

REFERENCE_MAX_LINES: Final = 100
REFERENCE_MAX_WORDS: Final = 750
SCOPED_CORE_RULE_IDS: Final = sorted(
    rule_id for rule_id, rule in core_rules().items() if rule.frontmatter.scope == "scoped"
)
#: Rule id -> text that only the probe's branch of its ``{% if %}`` renders.
LONG_BRANCH_MARKERS: Final = (
    ("pytest", "This project has `pytest-asyncio` installed"),
    ("ml-serialization-security", "## PyTorch checkpoints"),
    ("ml-serialization-security", "## NumPy / array data"),
    ("ml-serialization-security", "## pandas frames"),
    ("ml-serialization-security", "## scikit-learn estimators"),
)


@pytest.fixture(scope="module")
def probe_facts(tmp_path_factory: pytest.TempPathFactory) -> Facts:
    """The reference-probe facts, detected once for the module."""
    return reference_probe_facts(tmp_path_factory.mktemp("reference-probe-facts"))


@pytest.mark.parametrize("rule_id", SCOPED_CORE_RULE_IDS)
def test_core_scoped_rule_fits_one_reference_read(rule_id: str, probe_facts: Facts) -> None:
    body = render_core_rule(rule_id, probe_facts)
    lines, words = len(body.splitlines()), len(body.split())
    assert lines <= REFERENCE_MAX_LINES and words <= REFERENCE_MAX_WORDS, (
        f"{rule_id}: renders {lines} lines / {words} words with the reference-probe facts; "
        f"expected at most {REFERENCE_MAX_LINES} lines and {REFERENCE_MAX_WORDS} words "
        "(split it or move detail to another member)"
    )


@pytest.mark.parametrize(("rule_id", "marker"), LONG_BRANCH_MARKERS)
def test_reference_probe_facts_render_every_jinja_branch_once(
    rule_id: str, marker: str, probe_facts: Facts
) -> None:
    """The size bound measures the long form: the probe reaches each library branch once."""
    count = render_core_rule(rule_id, probe_facts).count(marker)
    assert count == 1, f"{rule_id}: {marker!r} renders {count} times with the probe facts"
