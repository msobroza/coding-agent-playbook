"""Pins of core skill ``ml-data`` (spec 9.6.2): serialization plus four array and frame rules.

Sections and priorities follow mapping-ml-data.md (prU D17, L0-16; the priority
formula is on :class:`RulePin`). The retired ids ``ml-dtypes-and-typing`` and
``ml-reproducibility-and-testing`` stay until their content lane retires them,
filed under their first successor's section and priority (``ml-dtypes-at-load``,
``ml-seeded-randomness``).

The serialization security, vectorization, indexing & mutation and dtypes &
validation sections are vendored (C-ml-data-01): their ten rules are pinned at
the mapping's priorities 20-24 and 40-44, and ``ml-dtypes-and-typing`` is gone.
``ml-frame-validation`` gates on pandera, which the reference probe lacks.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_ML_FILES: Final = ("**/*.py", "**/*.ipynb")
_ML_ARRAY_GATE: Final = {"any_ml_stack": ["numpy", "pandas", "polars"]}
_ML_PANDAS_GATE: Final = {"any_ml_stack": ["pandas"]}
_ML_FRAME_GATE: Final = {"any_ml_stack": ["pandas", "polars"]}
_ML_MODEL_GATE: Final = {
    "any_ml_stack": [
        "torch",
        "tensorflow",
        "jax",
        "transformers",
        "scikit-learn",
        "xgboost",
        "lightgbm",
    ]
}

PINS: Final = CoreSkillPins(
    skill_id="ml-data",
    where="Model, array and data-frame code",
    members=(
        "ml-serialization-security",
        "ml-vectorization",
        "ml-build-once",
        "ml-data-transforms",
        "ml-loc-assignment",
        "ml-dtypes-at-load",
        "ml-check-after-load",
        "ml-frame-validation",
        "ml-numpy-dtypes",
        "ml-categorical-labels",
        "ml-reproducibility-and-testing",
    ),
    probe_inactive=frozenset({"ml-frame-validation"}),
    section_ids=(
        "security",
        "vectorization",
        "mutation",
        "dtypes",
        "reproducibility",
        "style",
        "typing",
        "testing",
    ),
    rules={
        "ml-serialization-security": RulePin(
            applies_if=_ML_MODEL_GATE,
            globs=("**/*.py",),
            priority=20,
            name="ML serialization & deserialization security",
            tags=("ml", "security", "serialization"),
            section="security",
        ),
        "ml-vectorization": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=21,
            name="Vectorization",
            tags=("ml", "numpy", "pandas", "polars", "performance"),
            section="vectorization",
        ),
        "ml-build-once": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=22,
            name="Build once",
            tags=("ml", "numpy", "pandas", "polars", "performance"),
            section="vectorization",
        ),
        "ml-data-transforms": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=23,
            name="Data transforms",
            tags=("ml", "pandas", "polars", "numpy"),
            section="mutation",
        ),
        "ml-loc-assignment": RulePin(
            applies_if=_ML_PANDAS_GATE,
            globs=_ML_FILES,
            priority=24,
            name="Assignment with .loc",
            tags=("ml", "pandas", "indexing"),
            section="mutation",
        ),
        "ml-dtypes-at-load": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=40,
            name="Dtypes at load",
            tags=("ml", "dtypes", "io"),
            section="dtypes",
        ),
        "ml-check-after-load": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=41,
            name="Check after loading",
            tags=("ml", "dtypes", "validation"),
            section="dtypes",
        ),
        "ml-frame-validation": RulePin(
            applies_if={**_ML_FRAME_GATE, "has_dependency": ["pandera"]},
            globs=_ML_FILES,
            priority=42,
            name="Frame validation with pandera",
            tags=("ml", "pandas", "polars", "validation"),
            section="dtypes",
        ),
        "ml-numpy-dtypes": RulePin(
            applies_if={"any_ml_stack": ["numpy"]},
            globs=_ML_FILES,
            priority=43,
            name="NumPy dtypes",
            tags=("ml", "numpy", "dtypes"),
            section="dtypes",
        ),
        "ml-categorical-labels": RulePin(
            applies_if=_ML_FRAME_GATE,
            globs=_ML_FILES,
            priority=44,
            name="Categorical labels",
            tags=("ml", "pandas", "polars", "dtypes"),
            section="dtypes",
        ),
        "ml-reproducibility-and-testing": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=45,
            name="Reproducibility and numeric tests",
            tags=("ml", "reproducibility", "testing"),
            section="reproducibility",
        ),
    },
)
