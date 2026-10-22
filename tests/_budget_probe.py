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
import itertools
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from jinja2 import nodes
from jinja2.sandbox import SandboxedEnvironment

import coding_agent_playbook
from coding_agent_playbook.commands import init as _init
from coding_agent_playbook.detector.facts import detect
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


def reference_probe_facts(repo: Path) -> Facts:
    """The detector facts of a freshly written probe (rule renders in PR 5-8 size tests).

    Example: ``reference_probe_facts(tmp_path)["frameworks"]`` names fastapi and pytest.
    """
    write_reference_probe(repo)
    return detect(repo)


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


#: prU D40: example code targets 3.10 as the lowest branch; the matrix renders each minor.
MATRIX_PYTHON_VERSIONS: Final = ("3.10", "3.11", "3.12", "3.13")
#: Library helper -> the fact it reads (``rendering.jinja.build_environment``).
_LIBRARY_HELPER_FACTS: Final[Mapping[str, str]] = {
    "has_framework": "frameworks",
    "has_ml_dep": "ml_stack",
    "has_dependency": "dependencies",
}
_ORDERING_OPS: Final[Mapping[str, str]] = {"gt": ">", "gteq": ">=", "lt": "<", "lteq": "<="}


def library_switches(template: str) -> tuple[tuple[str, str], ...]:
    """Every ``(helper, library)`` a template tests, sorted: its literal library-helper calls.

    Example: ``library_switches('{% if has_ml_dep("torch") %}x{% endif %}')`` ->
    ``(("has_ml_dep", "torch"),)``.
    """
    found = {
        (call.node.name, call.args[0].value)
        for call in _parse(template).find_all(nodes.Call)
        if isinstance(call.node, nodes.Name)
        and call.node.name in _LIBRARY_HELPER_FACTS
        and len(call.args) == 1
        and isinstance(call.args[0], nodes.Const)
        and isinstance(call.args[0].value, str)
    }
    return tuple(sorted(found))


def fact_matrix(template: str) -> list[Facts]:
    """The facts a template renders with: each matrix Python crossed with its libraries on/off.

    Every on/off combination of :func:`library_switches` (each in the fact its
    helper reads) for each of :data:`MATRIX_PYTHON_VERSIONS`. No other fact is
    set beyond ``project_kind``, which ``detect`` always reports, so a template
    that reads an undetected fact without a guard fails to render.

    Example: ``len(fact_matrix('{% if has_framework("fastapi") %}x{% endif %}'))`` -> 8.
    """
    libraries = library_switches(template)
    matrix: list[Facts] = []
    for version in MATRIX_PYTHON_VERSIONS:
        for switches in itertools.product((False, True), repeat=len(libraries)):
            facts: dict[str, object] = {"python_version": version, "project_kind": "python-unknown"}
            for (helper, library), on in zip(libraries, switches, strict=True):
                if on:
                    held = facts.setdefault(_LIBRARY_HELPER_FACTS[helper], {})
                    cast("dict[str, str]", held)[library] = "1.0"
            matrix.append(cast("Facts", facts))
    return matrix


def distinct_renderings(rule: Rule) -> dict[str, Facts]:
    """Each distinct body ``rule`` renders over its :func:`fact_matrix`, with the first facts behind it.

    Raises what the render raises, e.g. ``jinja2.UndefinedError`` naming a
    variable that is undefined in any branch the matrix reaches.

    Example: ``len(distinct_renderings(core_rules()["python-typing"]))`` -> 2.
    """
    renderings: dict[str, Facts] = {}
    for facts in fact_matrix(rule.template_body):
        renderings.setdefault(render_rule(rule, facts), facts)
    return renderings


def string_version_comparisons(template: str) -> list[str]:
    """Each ordering comparison of ``python_version`` or a string literal in ``template``.

    Strings order character by character (``"3.9" > "3.12"``), so a version
    branch goes through ``python_at_least`` (prU D40). Each finding reads like
    the template's condition, with string literals single-quoted.

    Example: ``string_version_comparisons('{% if python_version >= "3.11" %}{% endif %}')``
    -> ``["python_version >= '3.11'"]``.
    """
    found: list[str] = []
    for compare in _parse(template).find_all(nodes.Compare):
        operands = [compare.expr, *(operand.expr for operand in compare.ops)]
        ordering = any(operand.op in _ORDERING_OPS for operand in compare.ops)
        if ordering and any(_is_version_text(operand) for operand in operands):
            parts = [_describe(compare.expr)]
            for operand in compare.ops:
                parts += [_ORDERING_OPS.get(operand.op, operand.op), _describe(operand.expr)]
            found.append(" ".join(parts))
    return found


def _parse(template: str) -> nodes.Template:
    return SandboxedEnvironment().parse(template)


def _is_version_text(node: nodes.Node) -> bool:
    if isinstance(node, nodes.Name):
        return node.name == "python_version"
    return isinstance(node, nodes.Const) and isinstance(node.value, str)


def _describe(node: nodes.Node) -> str:
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Const):
        return repr(node.value)
    return type(node).__name__


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
