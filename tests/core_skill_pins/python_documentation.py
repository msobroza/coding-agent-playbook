"""Pins of core skill ``python-documentation`` (prU D53, D60, D67, D69).

C-python-documentation-01 vendors the docs-in-sync, design-records and
repository-files rules; every one but the citation rule is ungated, so the
reference probe writes the skill, and it has no ``CITATION.cff``, so
``docs-citation-file`` stays inactive there. C-python-documentation-02 vendors
the user-docs and docs-build rules: the Sphinx pair gates on ``docs/conf.py`` and
the MkDocs pair on ``mkdocs.yml`` (D67: tool rules render only where the repo uses
the tool), so those four are probe-inactive too.
"""

from __future__ import annotations

from typing import Final

from tests.core_skill_pins import CoreSkillPins, RulePin

_TAGS: Final = ("python", "docs")
_SPHINX: Final = {"has_file": ["docs/conf.py"]}
_MKDOCS: Final = {"has_file": ["mkdocs.yml"]}

PINS: Final = CoreSkillPins(
    skill_id="python-documentation",
    where="README, changelog, CONTRIBUTING, CITATION.cff and docs/ pages",
    members=(
        "docs-same-change",
        "docs-runnable-examples",
        "docs-record-why",
        "docs-document-layout",
        "docs-architecture-overview",
        "docs-readme-essentials",
        "docs-changelog",
        "docs-contributing-guide",
        "docs-citation-file",
        "docs-page-kinds",
        "sphinx-api-reference",
        "mkdocs-api-reference",
        "docs-check-in-ci",
        "sphinx-docs-build",
        "mkdocs-docs-build",
    ),
    probe_inactive=frozenset(
        {
            "docs-citation-file",
            "sphinx-api-reference",
            "mkdocs-api-reference",
            "sphinx-docs-build",
            "mkdocs-docs-build",
        }
    ),
    section_ids=("in-sync", "design-records", "repo-files", "user-docs", "docs-build"),
    rules={
        "docs-same-change": RulePin(
            applies_if={},
            globs=("README*", "docs/**", "examples/**", "CHANGELOG*", "CONTRIBUTING*"),
            priority=40,
            name="Docs in the same change",
            tags=_TAGS,
            section="in-sync",
        ),
        "docs-runnable-examples": RulePin(
            applies_if={},
            globs=("README*", "docs/**", "examples/**", "*.rst"),
            priority=41,
            name="Runnable examples",
            tags=(*_TAGS, "doctest"),
            section="in-sync",
        ),
        "docs-record-why": RulePin(
            applies_if={},
            globs=("docs/adr/**",),
            priority=42,
            name="Record the why",
            tags=(*_TAGS, "adr"),
            section="design-records",
        ),
        "docs-document-layout": RulePin(
            applies_if={},
            globs=("docs/**", "CONTEXT.md", "CONTEXT-MAP.md", ".scratch/**"),
            priority=43,
            name="Engineering document paths",
            tags=(*_TAGS, "layout"),
            section="design-records",
        ),
        "docs-architecture-overview": RulePin(
            applies_if={},
            globs=("docs/architecture.md",),
            priority=44,
            name="Architecture overview",
            tags=(*_TAGS, "architecture"),
            section="design-records",
        ),
        "docs-readme-essentials": RulePin(
            applies_if={},
            globs=("README*",),
            priority=60,
            name="README essentials",
            tags=(*_TAGS, "readme"),
            section="repo-files",
        ),
        "docs-changelog": RulePin(
            applies_if={},
            globs=(
                "CHANGELOG*",
                "CHANGES*",
                "HISTORY*",
                "NEWS*",
                "changelog.d/**",
                "newsfragments/**",
            ),
            priority=61,
            name="Changelog",
            tags=(*_TAGS, "changelog"),
            section="repo-files",
        ),
        "docs-contributing-guide": RulePin(
            applies_if={},
            globs=("CONTRIBUTING*", ".github/CONTRIBUTING*", "docs/CONTRIBUTING*"),
            priority=62,
            name="Contributing guide",
            tags=(*_TAGS, "contributing"),
            section="repo-files",
        ),
        "docs-citation-file": RulePin(
            applies_if={"has_file": ["CITATION.cff"]},
            globs=("CITATION.cff",),
            priority=63,
            name="Citation file",
            tags=(*_TAGS, "citation"),
            section="repo-files",
        ),
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
