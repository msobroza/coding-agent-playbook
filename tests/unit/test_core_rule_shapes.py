"""Every scoped rule in core fits one reference read (specs/prS-skills-context.md 9.4.5, 9.15).

A scoped rule reaches the agent as one reference of its skill, opened in a single
read. 100 lines is the Agent Skills threshold above which a reference needs a
table of contents, and 750 words keeps one reference to one topic, so CI bounds
every core scoped rule, rendered as sync renders it with the reference-probe facts
(``tests/_budget_probe.py``). Those facts reach the ``pytest-asyncio`` branch of
``pytest``, the torch, NumPy, pandas and scikit-learn sections of
``ml-serialization-security``, and the NumPy and pandas sections and the torch and
scikit-learn seeding lines of the four array and data-frame members (spec 9.15,
12.3); the sanity test below pins each one. The probe declares no
``transformers`` and no ``polars``, and pins one Python, so the bound is also
applied over the fact matrix (prU D40, ``tests/_budget_probe.py``
:func:`~tests._budget_probe.fact_matrix`): Python 3.10 to 3.13 crossed with every
on/off combination of the libraries a rule's template tests, each distinct
rendering measured once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from tests._budget_probe import distinct_renderings, reference_probe_facts, render_core_rule
from tests._catalog import core_rules

if TYPE_CHECKING:
    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

REFERENCE_MAX_LINES: Final = 100
REFERENCE_MAX_WORDS: Final = 750
SCOPED_CORE_RULE_IDS: Final = sorted(
    rule_id for rule_id, rule in core_rules().items() if rule.frontmatter.scope == "scoped"
)
#: The four ml-data members for array and data-frame code (spec 9.6.1), sorted by id;
#: each renders one section per library (``tests/unit/test_ml_data_rules.py``).
ML_ARRAY_RULE_IDS: Final = (
    "ml-data-transforms",
    "ml-dtypes-and-typing",
    "ml-reproducibility-and-testing",
    "ml-vectorization",
)
#: Rule id -> text that only the probe's branch of its ``{% if %}`` renders.
LONG_BRANCH_MARKERS: Final = (
    ("pytest", "This project has `pytest-asyncio` installed"),
    ("ml-serialization-security", "## PyTorch checkpoints"),
    ("ml-serialization-security", "## NumPy / array data"),
    ("ml-serialization-security", "## pandas frames"),
    ("ml-serialization-security", "## scikit-learn estimators"),
    *((rule_id, heading) for rule_id in ML_ARRAY_RULE_IDS for heading in ("## NumPy", "## pandas")),
    ("ml-reproducibility-and-testing", "torch.manual_seed"),
    ("ml-reproducibility-and-testing", "random_state=int("),
    ("ml-reproducibility-and-testing", "rng = np.random.default_rng(seed)"),
)


@pytest.fixture(scope="module")
def probe_facts(tmp_path_factory: pytest.TempPathFactory) -> Facts:
    """The reference-probe facts, detected once for the module."""
    return reference_probe_facts(tmp_path_factory.mktemp("reference-probe-facts"))


def assert_fits_one_reference_read(rule_id: str, body: str, rendered_with: str) -> None:
    """Fail, naming the rule and its size, when ``body`` exceeds 100 lines or 750 words.

    ``rendered_with`` names the facts ``body`` was rendered with, for the message.

    Example: ``assert_fits_one_reference_read("pytest", body, "the reference-probe facts")``.
    """
    lines, words = len(body.splitlines()), len(body.split())
    assert lines <= REFERENCE_MAX_LINES and words <= REFERENCE_MAX_WORDS, (
        f"{rule_id}: renders {lines} lines / {words} words with {rendered_with}; "
        f"expected at most {REFERENCE_MAX_LINES} lines and {REFERENCE_MAX_WORDS} words "
        "(split it or move detail to another member)"
    )


@pytest.mark.parametrize("rule_id", SCOPED_CORE_RULE_IDS)
def test_core_scoped_rule_fits_one_reference_read(rule_id: str, probe_facts: Facts) -> None:
    body = render_core_rule(rule_id, probe_facts)
    assert_fits_one_reference_read(rule_id, body, "the reference-probe facts")


@pytest.mark.parametrize("rule_id", SCOPED_CORE_RULE_IDS)
def test_every_distinct_rendering_of_a_core_scoped_rule_fits_one_reference_read(
    rule_id: str,
) -> None:
    for body, facts in distinct_renderings(core_rules()[rule_id]).items():
        assert_fits_one_reference_read(rule_id, body, f"the fact-matrix facts {facts}")


@pytest.mark.parametrize(("rule_id", "marker"), LONG_BRANCH_MARKERS)
def test_reference_probe_facts_render_every_jinja_branch_once(
    rule_id: str, marker: str, probe_facts: Facts
) -> None:
    """The size bound measures these sections: the probe renders each listed branch once."""
    count = render_core_rule(rule_id, probe_facts).count(marker)
    assert count == 1, f"{rule_id}: {marker!r} renders {count} times with the probe facts"
