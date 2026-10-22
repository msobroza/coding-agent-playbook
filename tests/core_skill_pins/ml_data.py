"""Pins of core skill ``ml-data`` (spec 9.6.2): serialization plus array and frame rules.

Sections and priorities follow mapping-ml-data.md (prU D17, L0-16; the priority
formula is on :class:`RulePin`). The retired id ``ml-dtypes-and-typing`` stays
until its content lane retires it, filed under its first successor's section and
priority (``ml-dtypes-at-load``). Each member gates on the ml_stack libraries its
topic exists in; the gates here are the one place those libraries are pinned.
"""

from __future__ import annotations

from typing import Final

from tests._catalog import TEST_FILE_GLOBS
from tests.core_skill_pins import CoreSkillPins, RulePin

_ML_FILES: Final = ("**/*.py", "**/*.ipynb")
_ML_ARRAY_GATE: Final = {"any_ml_stack": ["numpy", "pandas", "polars"]}
_ML_FRAME_GATE: Final = {"any_ml_stack": ["pandas", "polars"]}
_ML_TYPING_GATE: Final = {"any_ml_stack": ["numpy", "pandas"]}
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
        "ml-data-transforms",
        "ml-dtypes-and-typing",
        "ml-seeded-randomness",
        "ml-method-chaining",
        "ml-named-aggregation",
        "ml-array-typing",
        "ml-numeric-assertions",
    ),
    probe_inactive=frozenset(),
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
        "ml-data-transforms": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=23,
            name="Data transforms",
            tags=("ml", "pandas", "polars", "numpy"),
            section="mutation",
        ),
        "ml-dtypes-and-typing": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=40,
            name="Dtypes and typing",
            tags=("ml", "dtypes", "typing"),
            section="dtypes",
        ),
        "ml-seeded-randomness": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=45,
            name="Seeded randomness",
            tags=("ml", "numpy", "pandas", "polars", "reproducibility", "random"),
            section="reproducibility",
        ),
        "ml-method-chaining": RulePin(
            applies_if=_ML_FRAME_GATE,
            globs=_ML_FILES,
            priority=60,
            name="Method chaining",
            tags=("ml", "pandas", "polars", "style"),
            section="style",
        ),
        "ml-named-aggregation": RulePin(
            applies_if=_ML_FRAME_GATE,
            globs=_ML_FILES,
            priority=61,
            name="Named aggregation",
            tags=("ml", "pandas", "polars", "groupby", "style"),
            section="style",
        ),
        "ml-array-typing": RulePin(
            applies_if=_ML_TYPING_GATE,
            globs=_ML_FILES,
            priority=62,
            name="Array and frame typing",
            tags=("ml", "numpy", "pandas", "typing"),
            section="typing",
        ),
        "ml-numeric-assertions": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=TEST_FILE_GLOBS,
            priority=63,
            name="Numeric assertions",
            tags=("ml", "testing", "pytest"),
            section="testing",
        ),
    },
)
