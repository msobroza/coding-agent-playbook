"""The D5 reference probe: one consumer repo every context-budget and core-content test reads.

The probe (specs/prS-skills-context.md 6.8.10) is a FastAPI + ML service with a
pytest suite and one notebook, synced with hooks on, the superpowers bundled plugin
enabled and every adapter that renders rules or skills. It is built from the inline
constants below, so no nested ``pyproject.toml`` or ``.ipynb`` is committed under
``tests/``. ``tests/integration/conftest.py`` syncs it once per module through
:func:`init_and_sync_reference_probe`; the context-budget, core-skill and
content-size tests then read its output.

:func:`render_core_rule` renders through ``rendering.session.RenderSession``, the
render pass sync opens, so the size and content tests read what sync would write.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

import coding_agent_playbook
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.detector.facts import (
    DETECTED_BOOL_FACTS,
    KNOWN_DEV_TOOLS,
    KNOWN_FRAMEWORKS,
    detect,
)
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from coding_agent_playbook.skills.document import WhereEntry, skill_catalog_block
from coding_agent_playbook.skills.naming import skill_id_of
from tests._catalog import CORE_ROOT, core_rules, core_skills

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.detector.facts import Facts

#: prU D18 as amended by D54 (6,000 -> 6,500 -> 7,000): core plus EACH bundled plugin's
#: skill listing, on the reference probe and in the per-plugin listing test.
LISTING_MAX_CHARS: Final = 7000

REFERENCE_PROBE_PYPROJECT: Final = """\
[project]
name = "mlsvc"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115", "httpx>=0.27", "pydantic>=2.9", "torch>=2.4",
    "numpy>=2.0", "pandas>=2.2", "scikit-learn>=1.5",
]

[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.8", "mypy>=1.13"]
"""

#: PR 1's init default plus the opt-in continue, so the probe covers every adapter
#: that renders rules or skills and does not depend on which PR lands first.
REFERENCE_PROBE_ADAPTERS: Final = "claude_code,opencode,shared_skills,continue"

#: The superpowers bundled plugin: the skill-listing budget counts every enabled plugin
#: (D5). mattpocock_skills is budgeted on its own (tests/plugins/mattpocock_skills/test_budget.py).
REFERENCE_PROBE_OVERLAYS: Final = "coding_agent_playbook.plugins.superpowers"

#: The ``[project]`` answers ``playbook init`` records, also the rule context's metadata.
REFERENCE_PROBE_NAME: Final = "mlsvc"
REFERENCE_PROBE_KIND: Final = "python-application"

_MAIN_PY: Final = '''\
"""The probe's FastAPI app."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
'''

_TEST_APP_PY: Final = '''\
"""The probe's one test."""

from app.main import health


def test_health_reports_ok() -> None:
    assert health() == {"status": "ok"}
'''

#: The smallest valid nbformat 4 notebook: one code cell, no outputs.
_NOTEBOOK: Final = {
    "cells": [
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": ["import pandas as pd\n"],
        }
    ],
    "metadata": {},
    "nbformat": 4,
    "nbformat_minor": 5,
}


def write_reference_probe(repo: Path) -> None:
    """Write the probe's pyproject, ``src/app/main.py``, ``tests/test_app.py`` and a notebook.

    Example: ``write_reference_probe(tmp_path)`` then ``detect(tmp_path)``.
    """
    files = {
        "pyproject.toml": REFERENCE_PROBE_PYPROJECT,
        "src/app/__init__.py": "",
        "src/app/main.py": _MAIN_PY,
        "tests/test_app.py": _TEST_APP_PY,
        "notebooks/explore.ipynb": json.dumps(_NOTEBOOK, indent=1) + "\n",
    }
    for relative, text in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


#: prU D63's reliable Domino markers, every kind at once: the D54/D59 worst-case probe.
_DOMINO_MARKERS: Final = {
    ".dominoignore": "results/\n",
    "dominostats.json": "{}\n",
}
_DOMINO_DEPENDENCY: Final = '"dominodatalab>=1.4", '


def write_domino_probe(repo: Path) -> None:
    """The reference probe plus reliable Domino markers (prU D54, D59, D63).

    Adds ``.dominoignore``, a ``dominostats.json`` and the ``dominodatalab``
    dependency, so the Domino skills apply once they ship and the budget tests
    measure the worst case with the D59 caps.

    Example: ``write_domino_probe(tmp_path)`` then ``init_and_sync_reference_probe(tmp_path)``.
    """
    write_reference_probe(repo)
    pyproject = REFERENCE_PROBE_PYPROJECT.replace(
        '"fastapi>=0.115", ', f'{_DOMINO_DEPENDENCY}"fastapi>=0.115", ', 1
    )
    assert pyproject != REFERENCE_PROBE_PYPROJECT, "the probe pyproject lost its fastapi pin"
    (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    for relative, text in _DOMINO_MARKERS.items():
        (repo / relative).write_text(text, encoding="utf-8")


#: The consumer repo's own layer (prU D70): an empty ``playbook/`` turns ``playbook_layer`` on.
AUTHORING_PROBE_LAYER: Final = "playbook"


def add_empty_playbook_layer(repo: Path) -> None:
    """Give ``repo`` an empty ``playbook/`` layer, which turns ``playbook_layer`` on (prU D70).

    A no-op when the layer exists, so a repo whose hooks already live there keeps them.

    Example: ``add_empty_playbook_layer(plain)`` keeps a plain repo's facts equal to a hook repo's.
    """
    (repo / AUTHORING_PROBE_LAYER).mkdir(exist_ok=True)


def write_authoring_probe(repo: Path) -> None:
    """The reference probe plus an empty ``playbook/`` layer (prU D70).

    ``mkdir playbook`` is how a consumer repo starts its own layer, so the
    detector reports ``playbook_layer`` and the ``playbook-creator`` skill
    applies, without the engine's ``catalog/core`` (its engine-only rule stays off).

    Example: ``write_authoring_probe(tmp_path)`` then ``init_and_sync_reference_probe(tmp_path)``.
    """
    write_reference_probe(repo)
    add_empty_playbook_layer(repo)


def reference_probe_facts(repo: Path) -> Facts:
    """The detector facts of a freshly written probe (rule renders in PR 5-8 size tests).

    Example: ``reference_probe_facts(tmp_path)["frameworks"]`` names fastapi and pytest.
    """
    write_reference_probe(repo)
    return detect(repo)


#: The ML libraries :func:`every_gate_facts` declares: each opens its own rule sections.
_EVERY_GATE_ML_STACK: Final = ("numpy", "pandas", "polars", "torch")
#: Runtime dependencies rules gate on by name (``has_dependency``), beyond the frameworks.
_EVERY_GATE_DEPENDENCIES: Final = ("pydantic-settings", "anyio")


def every_gate_facts() -> Facts:
    """Facts that open every gate a core rule can take at once: the worst case for its size.

    Every framework the detector knows (``pytest-asyncio`` among them), NumPy,
    pandas, polars and torch, ``pydantic-settings`` and ``anyio``, ``uv`` as the
    package manager, Python 3.13 and every boolean fact true (prU D20, L0-13).
    The reference probe never activates some rules (SQLAlchemy, uv,
    pydantic-settings), so the size bound renders each rule with these too.
    Built directly, not detected, so no repo is written.

    Example: ``render_core_rule("python-uv-workflow", every_gate_facts())``.
    """
    frameworks = dict.fromkeys(sorted(KNOWN_FRAMEWORKS), "")
    ml_stack = dict.fromkeys(_EVERY_GATE_ML_STACK, "")
    facts: Facts = {
        "python_version": "3.13",
        "package_manager": "uv",
        "project_kind": "python-application",
        "dependencies": {**frameworks, **ml_stack, **dict.fromkeys(_EVERY_GATE_DEPENDENCIES, "")},
        "dev_dependencies": dict.fromkeys(sorted(KNOWN_DEV_TOOLS), ""),
        "frameworks": frameworks,
        "ml_stack": ml_stack,
        "dev_tools": set(KNOWN_DEV_TOOLS),
    }
    for flag in DETECTED_BOOL_FACTS:
        facts[flag] = True
    return facts


def render_core_rule(
    rule_id: str, facts: Facts, metadata: Mapping[str, object] | None = None
) -> str:
    """The body of core rule ``rule_id`` rendered as sync renders it, with ``facts``.

    :func:`render_rule` on the core rule with that id. Raises ``KeyError``
    naming the id when core ships no such rule.

    Example: ``render_core_rule("project-context", facts, {"project_name": "demo"})``.
    """
    rules = core_rules()
    if rule_id not in rules:
        raise KeyError(f"core ships no rule {rule_id!r}; expected one of {sorted(rules)}")
    return render_rule(rules[rule_id], facts, metadata)


def render_rule(rule: Rule, facts: Facts, metadata: Mapping[str, object] | None = None) -> str:
    """The body of ``rule`` rendered as sync renders it, with ``facts``.

    A render session like ``render_artifacts``' (facts, then the project
    metadata, then the installed engine version). ``metadata`` replaces the
    probe's ``project_name`` and empty ``project_description``, or any fact such
    as ``project_kind``, for tests that pin how an always rule renders them. The
    rule renders whatever its ``applies_if``.

    Example: ``render_rule(core_rules()["pytest"], {"python_version": "3.12"})``.
    """
    context = TemplateContext(
        facts=facts,
        project_name=REFERENCE_PROBE_NAME,
        engine_version=coding_agent_playbook.__version__,
        overrides=dict(metadata or {}),
    )
    # No rule to filter, so no has_file path to anchor: the session renders one rule.
    session = RenderSession.open((), context, repo_root=Path())
    return session.render_rule(rule).body


def every_core_where_entry(skills_root: Path = CORE_ROOT / "skills") -> list[WhereEntry]:
    """A ``Where guidance lives`` row for every skill under ``skills_root`` declaring ``playbook.files``.

    The worst case of prU D35: sync lists a skill only when one of its members
    is active, so the probe's own map shrinks with its facts; this one does not.
    Loaded through :func:`tests._catalog.core_skills` (the engine's own walker,
    ``SKILL.md`` or ``SKILL.md.j2``), so a new core skill joins without an edit here.

    Example: ``where_guidance_section(every_core_where_entry())``.
    """
    entries: list[WhereEntry] = []
    for skill in core_skills(skills_root):
        files = skill_catalog_block(skill).files
        if files is not None:
            entries.append(WhereEntry(skill_id=skill_id_of(skill), files=files))
    return entries


def init_and_sync_reference_probe(repo: Path) -> None:
    """``playbook init --non-interactive`` in process: hooks on, probe adapters and plugins.

    Init ends with a sync, so ``repo`` holds the synced output afterwards. The
    caller isolates git first (``tests.conftest.apply_hermetic_git_env``).
    Raises ``AssertionError`` carrying the exit code when init fails.

    Example::

        write_reference_probe(repo)
        init_and_sync_reference_probe(repo)
    """
    args = argparse.Namespace(
        repo_root=str(repo),
        non_interactive=True,
        name=REFERENCE_PROBE_NAME,
        kind=REFERENCE_PROBE_KIND,
        description="",
        adapters=REFERENCE_PROBE_ADAPTERS,
        overlays=REFERENCE_PROBE_OVERLAYS,
    )
    code = _init.run(args)
    assert code == 0, f"playbook init on the reference probe exited {code}, expected 0"
