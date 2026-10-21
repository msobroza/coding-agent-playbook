"""Pins of core skill ``ml-data`` (spec 9.6.2): serialization plus four array and frame rules."""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_ML_FILES: Final = ("**/*.py", "**/*.ipynb")
_ML_ARRAY_GATE: Final = {"any_ml_stack": ["numpy", "pandas", "polars"]}

PINS: Final = CoreSkillPins(
    skill_id="ml-data",
    where="Model, array and data-frame code",
    members=(
        "ml-serialization-security",
        "ml-data-transforms",
        "ml-vectorization",
        "ml-dtypes-and-typing",
        "ml-reproducibility-and-testing",
    ),
    probe_inactive=frozenset(),
    rules={
        "ml-vectorization": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=71,
            name="Vectorization",
            tags=("ml", "numpy", "pandas", "polars", "performance"),
        ),
        "ml-data-transforms": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=71,
            name="Data transforms",
            tags=("ml", "pandas", "polars", "numpy"),
        ),
        "ml-dtypes-and-typing": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=73,
            name="Dtypes and typing",
            tags=("ml", "dtypes", "typing"),
        ),
        "ml-reproducibility-and-testing": RulePin(
            applies_if=_ML_ARRAY_GATE,
            globs=_ML_FILES,
            priority=73,
            name="Reproducibility and numeric tests",
            tags=("ml", "reproducibility", "testing"),
        ),
    },
)
