"""Every scoped rule and every rule template in core fits one reference read (spec 9.4.5, 9.15).

A scoped rule reaches the agent as one reference of its skill, opened in a single
read. 100 lines is the Agent Skills threshold above which a reference needs a
table of contents, and 750 words keeps one reference to one topic (prU D20), so CI
bounds every core scoped rule, rendered as sync renders it with the reference-probe
facts (``tests/_budget_probe.py``), and counts after ``ruff format`` has laid out
its code blocks. Those facts reach the ``pytest-asyncio`` branch of
``pytest``, the torch, NumPy, pandas and scikit-learn sections of
``ml-serialization-security``, the NumPy and pandas lines of the array and
data-frame members and the torch and scikit-learn seeding lines (spec 9.15,
12.3); the sanity test below pins each one. The probe declares no
``transformers`` and no ``polars``, pins one Python and one project description,
so the bound is also applied to every distinct rendering of every scoped rule and
every ``.md.j2`` rule over its matrix (prU D40, ``tests/_template_matrix.py``):
Python 3.10 to 3.13 crossed with every on/off combination of the libraries its
template tests and with each project metadata variant it reads. This is the one
size check over the matrix; ``tests/unit/test_core_rule_template_matrix.py`` checks
that the matrix reaches every branch.

A second bound renders every rule with :func:`tests._budget_probe.every_gate_facts`
(every gate the detector can open at once), so the rules the probe never
activates (SQLAlchemy, uv, pydantic-settings) are measured with all their gates
on too (prU D20, L0-13).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from tests._budget_probe import every_gate_facts, reference_probe_facts, render_core_rule
from tests._catalog import core_rules
from tests._template_matrix import distinct_renderings, ruff_formatted

if TYPE_CHECKING:
    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

REFERENCE_MAX_LINES: Final = 100
REFERENCE_MAX_WORDS: Final = 750
SCOPED_CORE_RULE_IDS: Final = sorted(
    rule_id for rule_id, rule in core_rules().items() if rule.frontmatter.scope == "scoped"
)
#: Every rule the matrix measures: the scoped rules and the always rules with a template.
MATRIX_MEASURED_RULE_IDS: Final = sorted(
    {
        *SCOPED_CORE_RULE_IDS,
        *(rule_id for rule_id, rule in core_rules().items() if rule.is_templated),
    }
)
#: The ml-data members gated on all three of NumPy, pandas and polars, sorted by id; each
#: renders per-library lines only for the libraries declared (``tests/unit/test_ml_data_rules.py``).
ML_ARRAY_RULE_IDS: Final = (
    "ml-build-once",
    "ml-check-after-load",
    "ml-data-transforms",
    "ml-dtypes-at-load",
    "ml-numeric-assertions",
    "ml-seeded-randomness",
    "ml-vectorization",
)
#: Rule id -> text that only the probe's branch of its ``{% if %}`` renders.
LONG_BRANCH_MARKERS: Final = (
    ("pytest", "This project has `pytest-asyncio` installed"),
    ("ml-serialization-security", "torch.load(path, weights_only=True)"),
    ("ml-serialization-security", "np.load(path, allow_pickle=False)"),
    ("ml-serialization-security", "pd.read_parquet(path)"),
    ("ml-serialization-security", "same scikit-learn version"),
    ("ml-vectorization", "parcels.iterrows()"),
    ("ml-vectorization", "np.where(readings > ceiling"),
    ("ml-build-once", "np.concatenate([load_chunk(path)"),
    ("ml-build-once", "pd.concat(frames"),
    ("ml-data-transforms", "np.minimum(readings, ceiling)"),
    ("ml-data-transforms", 'users.dropna(subset=["email"], inplace=True)'),
    ("ml-dtypes-at-load", "usecols=0, dtype=str"),
    ("ml-dtypes-at-load", "pd.read_csv(path, parse_dates="),
    ("ml-check-after-load", "frame.dtypes"),
    ("ml-check-after-load", "array.shape[1] != dim"),
    ("ml-categorical-labels", "REGION = pd.CategoricalDtype("),
    ("ml-seeded-randomness", "torch.manual_seed"),
    ("ml-seeded-randomness", "random_state=int("),
    ("ml-seeded-randomness", "rng = np.random.default_rng(seed)"),
    # D27(4): the probe has pytest-asyncio; the AnyIO branches are measured over the matrix.
    ("fastapi-dependency-overrides", "This project has `pytest-asyncio`"),
    ("sqlalchemy-test-rollback", '@pytest_asyncio.fixture(scope="session", loop_scope="session")'),
)


@pytest.fixture(scope="module")
def probe_facts(tmp_path_factory: pytest.TempPathFactory) -> Facts:
    """The reference-probe facts, detected once for the module."""
    return reference_probe_facts(tmp_path_factory.mktemp("reference-probe-facts"))


def assert_fits_one_reference_read(rule_id: str, body: str, rendered_with: str) -> None:
    """Fail, naming the rule and its size, when ``body`` exceeds 100 lines or 750 words.

    Counted on :func:`~tests._template_matrix.ruff_formatted` ``body`` (D20: after
    ruff format). ``rendered_with`` names the facts ``body`` was rendered with, for
    the message.

    Example: ``assert_fits_one_reference_read("pytest", body, "the reference-probe facts")``.
    """
    formatted = ruff_formatted(body)
    lines, words = len(formatted.splitlines()), len(formatted.split())
    assert lines <= REFERENCE_MAX_LINES and words <= REFERENCE_MAX_WORDS, (
        f"{rule_id}: renders {lines} lines / {words} words (after ruff format) with "
        f"{rendered_with}; "
        f"expected at most {REFERENCE_MAX_LINES} lines and {REFERENCE_MAX_WORDS} words "
        "(split it or move detail to another member)"
    )


@pytest.mark.parametrize("rule_id", SCOPED_CORE_RULE_IDS)
def test_core_scoped_rule_fits_one_reference_read(rule_id: str, probe_facts: Facts) -> None:
    body = render_core_rule(rule_id, probe_facts)
    assert_fits_one_reference_read(rule_id, body, "the reference-probe facts")


@pytest.mark.parametrize("rule_id", MATRIX_MEASURED_RULE_IDS)
def test_every_distinct_rendering_of_a_core_rule_fits_one_reference_read(rule_id: str) -> None:
    for body, point in distinct_renderings(core_rules()[rule_id]).items():
        assert_fits_one_reference_read(rule_id, body, f"the matrix {point}")


def test_the_cap_counts_code_blocks_as_ruff_format_lays_them_out() -> None:
    call = "result = compute(" + ", ".join(f"argument_{index}" for index in range(12)) + ")"
    body = "Prose.\n\n```python\n" + call + "\n```\n" + "line\n" * 94
    assert len(body.splitlines()) == 99
    with pytest.raises(AssertionError, match="after ruff format"):
        assert_fits_one_reference_read("probe", body, "a synthetic body")


@pytest.mark.parametrize("rule_id", SCOPED_CORE_RULE_IDS)
def test_core_scoped_rule_fits_one_reference_read_with_every_gate_on(rule_id: str) -> None:
    body = render_core_rule(rule_id, every_gate_facts())
    assert_fits_one_reference_read(rule_id, body, "every gate on (every_gate_facts)")


@pytest.mark.parametrize(("rule_id", "marker"), LONG_BRANCH_MARKERS)
def test_reference_probe_facts_render_every_jinja_branch_once(
    rule_id: str, marker: str, probe_facts: Facts
) -> None:
    """The size bound measures these sections: the probe renders each listed branch once."""
    count = render_core_rule(rule_id, probe_facts).count(marker)
    assert count == 1, f"{rule_id}: {marker!r} renders {count} times with the probe facts"
