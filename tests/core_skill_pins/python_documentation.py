"""Pins of core skill ``python-documentation`` (prU D53, D67, D69; C-python-documentation-02).

The Sphinx pair gates on ``docs/conf.py`` and the MkDocs pair on ``mkdocs.yml``
(D67: tool rules render only where the repo uses the tool); the reference probe
has neither file, so those four are probe-inactive. ``docs-page-kinds`` and
``docs-check-in-ci`` are ungated, so the skill is written in every Python repo.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_SPHINX: Final = {"has_file": ["docs/conf.py"]}
_MKDOCS: Final = {"has_file": ["mkdocs.yml"]}

PINS: Final = CoreSkillPins(
    skill_id="python-documentation",
    where="README, changelog, CONTRIBUTING, CITATION.cff and docs/ pages",
    members=(
        "docs-page-kinds",
        "sphinx-api-reference",
        "mkdocs-api-reference",
        "docs-check-in-ci",
        "sphinx-docs-build",
        "mkdocs-docs-build",
    ),
    probe_inactive=frozenset(
        {
            "sphinx-api-reference",
            "mkdocs-api-reference",
            "sphinx-docs-build",
            "mkdocs-docs-build",
        }
    ),
    section_ids=("in-sync", "design-records", "repo-files", "user-docs", "docs-build"),
    rules={
        "docs-page-kinds": RulePin(
            applies_if={},
            globs=("docs/**", "*.rst"),
            priority=64,
            name="Page kinds",
            tags=("python", "docs"),
            section="user-docs",
        ),
        "sphinx-api-reference": RulePin(
            applies_if=_SPHINX,
            globs=("docs/conf.py", "docs/**"),
            priority=65,
            name="Sphinx API reference",
            tags=("python", "docs", "sphinx"),
            section="user-docs",
        ),
        "mkdocs-api-reference": RulePin(
            applies_if=_MKDOCS,
            globs=("mkdocs.yml", "docs/**"),
            priority=66,
            name="MkDocs API reference",
            tags=("python", "docs", "mkdocs"),
            section="user-docs",
        ),
        "docs-check-in-ci": RulePin(
            applies_if={},
            globs=("docs/**", "README*", "*.rst"),
            priority=67,
            name="Docs check",
            tags=("python", "docs", "ci"),
            section="docs-build",
        ),
        "sphinx-docs-build": RulePin(
            applies_if=_SPHINX,
            globs=("docs/conf.py", "docs/Makefile", ".readthedocs.y*ml"),
            priority=68,
            name="Sphinx build",
            tags=("python", "docs", "sphinx"),
            section="docs-build",
        ),
        "mkdocs-docs-build": RulePin(
            applies_if=_MKDOCS,
            globs=("mkdocs.yml", ".readthedocs.y*ml"),
            priority=69,
            name="MkDocs build",
            tags=("python", "docs", "mkdocs"),
            section="docs-build",
        ),
    },
)
