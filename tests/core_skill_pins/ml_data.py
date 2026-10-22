"""Pins of core skill ``ml-data`` (spec 9.6.2): serialization plus four array and frame rules.

Sections and priorities follow mapping-ml-data.md (prU D17, L0-16; the priority
formula is on :class:`RulePin`). The retired ids ``ml-dtypes-and-typing`` and
``ml-reproducibility-and-testing`` stay until their content lane retires them,
filed under their first successor's section and priority (``ml-dtypes-at-load``,
``ml-seeded-randomness``).
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_ML_FILES: Final = ("**/*.py", "**/*.ipynb")
_ML_ARRAY_GATE: Final = {"any_ml_stack": ["numpy", "pandas", "polars"]}
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
        "ml-reproducibility-and-testing",
    ),
    probe_inactive=frozenset(),
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
