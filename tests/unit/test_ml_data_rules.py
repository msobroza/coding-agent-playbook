"""The ml-data members for array and data-frame code (specs/prS-skills-context.md 12, prU).

Most gate on ``any_ml_stack: [numpy, pandas, polars]`` (D9) and render each
library's lines only when the repo declares it: a NumPy-only repo gets the NumPy
lines and no data-frame guidance (R5-2). The members that speak of one kind of
library gate on it (``ml-numpy-dtypes`` on NumPy, ``ml-loc-assignment`` on
pandas, ``ml-categorical-labels`` on pandas or polars), and
``ml-frame-validation`` also needs pandera, so it never mandates pandera
(mapping-ml-data.md). torch alone activates none of them, so a torch-only repo
keeps ``ml-serialization-security`` as ml-data's only member, and the resync
golden for adding torch stays byte-identical.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, cast

import pytest

from coding_agent_playbook.detector.predicate import filter_applies_if
from tests._budget_probe import render_core_rule
from tests._catalog import core_rules
from tests.unit.test_core_rule_shapes import ML_ARRAY_RULE_IDS, assert_fits_one_reference_read

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

#: Every library one of the four rules branches on: their longest rendered form.
_EVERY_BRANCH_LIBRARY: Final = ("numpy", "pandas", "polars", "scikit-learn", "torch")
#: The line that says where the run's ``rng`` comes from (ml-reproducibility-and-testing).
_RNG_DEFINITION: Final = "rng = np.random.default_rng(seed)"


def _ml_facts(*libraries: str, dependencies: tuple[str, ...] = ()) -> Facts:
    """Detector facts whose ``ml_stack`` declares exactly ``libraries``, plus ``dependencies``."""
    return cast(
        "Facts",
        {
            "ml_stack": dict.fromkeys(libraries, ">=1"),
            "dependencies": dict.fromkeys((*libraries, *dependencies), ">=1"),
        },
    )


def _active_ml_data_members(facts: Facts, repo_root: Path) -> list[str]:
    """The ids of ml-data's member rules that pass ``applies_if``, as sync filters them."""
    members = [rule for rule in core_rules().values() if rule.frontmatter.skill == "ml-data"]
    return sorted(rule.frontmatter.id for rule in filter_applies_if(members, facts, repo_root))


@pytest.mark.parametrize(
    ("ml_stack", "dependencies", "extra"),
    [
        (("numpy",), (), ("ml-numpy-dtypes",)),
        (("pandas",), (), ("ml-categorical-labels", "ml-loc-assignment")),
        (("polars",), (), ("ml-categorical-labels",)),
        (
            ("pandas",),
            ("pandera",),
            ("ml-categorical-labels", "ml-frame-validation", "ml-loc-assignment"),
        ),
        (("polars",), ("pandera",), ("ml-categorical-labels", "ml-frame-validation")),
        (("numpy",), ("pandera",), ("ml-numpy-dtypes",)),
    ],
)
def test_ml_data_rules_gate_on_the_libraries_they_speak_of(
    ml_stack: tuple[str, ...], dependencies: tuple[str, ...], extra: tuple[str, ...], tmp_path: Path
) -> None:
    members = _active_ml_data_members(_ml_facts(*ml_stack, dependencies=dependencies), tmp_path)

    assert members == sorted({*ML_ARRAY_RULE_IDS, *extra}), (
        f"ml_stack {list(ml_stack)} with {list(dependencies)} activates {members}"
    )


def test_no_array_library_activates_no_array_rule(tmp_path: Path) -> None:
    assert _active_ml_data_members(_ml_facts(dependencies=("pandera",)), tmp_path) == []


def test_torch_only_repo_keeps_serialization_as_the_only_ml_data_member(tmp_path: Path) -> None:
    """Spec 12.2: torch alone adds no member, so the add-torch resync golden is unchanged."""
    members = _active_ml_data_members(_ml_facts("torch"), tmp_path)

    assert members == ["ml-serialization-security"], f"torch alone activates {members}"


#: Rule id -> library -> a line only that library's branch renders (mapping-ml-data.md).
_LIBRARY_MARKERS: Final[dict[str, dict[str, str]]] = {
    "ml-vectorization": {"numpy": "np.where(", "pandas": "iterrows", "polars": "map_elements"},
    "ml-build-once": {"numpy": "np.concatenate(", "pandas": "pd.concat(", "polars": "pl.concat("},
    "ml-data-transforms": {
        "numpy": "np.minimum(",
        "pandas": "inplace=True",
        "polars": "insert_column",
    },
    "ml-dtypes-at-load": {
        "numpy": "np.loadtxt(",
        "pandas": "pd.read_csv(",
        "polars": "schema_overrides=",
    },
    "ml-check-after-load": {
        "numpy": "array.shape",
        "pandas": "frame.dtypes",
        "polars": "frame.schema",
    },
    "ml-frame-validation": {"pandas": "pandera.pandas", "polars": "pandera.polars"},
    "ml-categorical-labels": {"pandas": "pd.CategoricalDtype(", "polars": "pl.Enum("},
}


def _library_rows() -> list[tuple[str, str, str, str]]:
    """(rule id, the one declared library, its marker, another library's marker)."""
    return [
        (rule_id, library, marker, other)
        for rule_id, markers in _LIBRARY_MARKERS.items()
        for library, marker in markers.items()
        for other_library, other in markers.items()
        if other_library != library
    ]


@pytest.mark.parametrize(("rule_id", "library", "present", "absent"), _library_rows())
def test_each_library_renders_only_its_own_lines(
    rule_id: str, library: str, present: str, absent: str
) -> None:
    body = render_core_rule(rule_id, _ml_facts(library))

    assert present in body, f"{rule_id} with only {library} lacks {present!r}"
    assert absent not in body, f"{rule_id} with only {library} renders {absent!r}"


def _section_rows() -> list[tuple[str, tuple[str, ...], str, str]]:
    """(rule id, ml_stack, text that must render, text that must not)."""
    return [
        # Library-specific seeding lines follow their own library, inside the shared section.
        (
            "ml-reproducibility-and-testing",
            ("numpy", "torch"),
            "torch.manual_seed",
            "random_state=",
        ),
        ("ml-reproducibility-and-testing", ("numpy", "scikit-learn"), "random_state=", "torch."),
        # polars installs no NumPy, so a polars-only repo gets no NumPy generator.
        ("ml-reproducibility-and-testing", ("polars",), "seed=sample_seed", "np.random"),
        # A polars-only repo gets no NumPy text from the library-neutral parts either.
        ("ml-vectorization", ("polars",), "pl.when(", "np."),
        ("ml-build-once", ("polars",), "pl.concat(", "np."),
        ("ml-dtypes-at-load", ("numpy",), "dtype=", "read_csv"),
    ]


@pytest.mark.parametrize(("rule_id", "ml_stack", "present", "absent"), _section_rows())
def test_library_sections_follow_the_ml_stack(
    rule_id: str, ml_stack: tuple[str, ...], present: str, absent: str
) -> None:
    body = render_core_rule(rule_id, _ml_facts(*ml_stack))

    assert body.count(present) >= 1, f"{rule_id} with {list(ml_stack)} lacks {present!r}"
    assert absent not in body, f"{rule_id} with {list(ml_stack)} renders {absent!r}"


@pytest.mark.parametrize("rule_id", sorted({*ML_ARRAY_RULE_IDS, *_LIBRARY_MARKERS}))
def test_ml_array_rule_fits_one_reference_read_with_every_library(rule_id: str) -> None:
    """The longest form: the probe declares no polars, so its size test misses that section."""
    body = render_core_rule(rule_id, _ml_facts(*_EVERY_BRANCH_LIBRARY))

    assert_fits_one_reference_read(rule_id, body, f"ml_stack {list(_EVERY_BRANCH_LIBRARY)}")


@pytest.mark.parametrize(
    "ml_stack",
    [
        ("numpy",),
        ("pandas",),
        ("pandas", "scikit-learn"),
        ("polars", "scikit-learn"),
        _EVERY_BRANCH_LIBRARY,
    ],
)
def test_rng_is_defined_before_its_first_use(ml_stack: tuple[str, ...]) -> None:
    """Review fix: the pandas and scikit-learn lines once used ``rng`` that only NumPy defined."""
    body = render_core_rule("ml-reproducibility-and-testing", _ml_facts(*ml_stack))

    first_use = re.search(r"\brng\b", body)
    assert first_use is not None, f"{list(ml_stack)} renders no `rng` at all"
    assert body.find(_RNG_DEFINITION) == first_use.start(), (
        f"with {list(ml_stack)} `rng` is used before {_RNG_DEFINITION!r}: "
        f"{body[first_use.start() - 60 : first_use.end() + 60]!r}"
    )


def test_seed_sequence_children_are_passed_to_default_rng() -> None:
    """Review fix: ``SeedSequence.spawn`` returns seeds, not generators, so the line wraps them."""
    body = render_core_rule("ml-reproducibility-and-testing", _ml_facts("numpy"))

    spawn_lines = [line for line in body.splitlines() if "SeedSequence(seed).spawn" in line]
    assert spawn_lines, "the NumPy section no longer names SeedSequence(seed).spawn"
    assert all("np.random.default_rng" in line for line in spawn_lines), (
        f"SeedSequence children are not passed to np.random.default_rng: {spawn_lines}"
    )


@pytest.mark.parametrize(
    ("rule_id", "ml_stack", "constant"),
    [
        ("ml-dtypes-at-load", ("pandas",), "REGION"),
        ("ml-dtypes-at-load", ("polars",), "REGION_LEVELS"),
        ("ml-dtypes-at-load", ("pandas",), "TIMESTAMP_FORMAT"),
        ("ml-frame-validation", ("pandas",), "TIMESTAMP_FORMAT"),
        ("ml-frame-validation", ("polars",), "TIMESTAMP_FORMAT"),
    ],
)
def test_example_constants_are_defined_before_their_first_use(
    rule_id: str, ml_stack: tuple[str, ...], constant: str
) -> None:
    """Review fix: the examples once used REGION and TIMESTAMP_FORMAT that only a sibling defined."""
    body = render_core_rule(rule_id, _ml_facts(*ml_stack))

    first_use = re.search(rf"\b{constant}\b", body)
    assert first_use is not None, f"{rule_id} with {list(ml_stack)} renders no {constant}"
    assert body.find(f"{constant} = ") == first_use.start(), (
        f"{rule_id} with {list(ml_stack)} uses {constant} before defining it"
    )


def _python_fences(body: str) -> list[str]:
    """The contents of every ```python fence of a rendered rule body."""
    return re.findall(r"```python\n(.*?)```", body, flags=re.DOTALL)


@pytest.mark.parametrize("rule_id", ["ml-vectorization", "ml-build-once"])
def test_each_fence_imports_every_module_once_at_its_top(rule_id: str) -> None:
    """Review fix: per-library branches once repeated ``import numpy as np`` mid-fence."""
    body = render_core_rule(rule_id, _ml_facts(*_EVERY_BRANCH_LIBRARY))

    for fence in _python_fences(body):
        lines = fence.splitlines()
        imports = [index for index, line in enumerate(lines) if line.startswith("import ")]
        assert imports == list(range(len(imports))), f"{rule_id}: an import below the top:\n{fence}"
        modules = [lines[index] for index in imports]
        assert len(modules) == len(set(modules)), f"{rule_id}: a module imported twice: {modules}"
