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
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from tests._catalog import core_rules

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.detector.facts import Facts

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

    A render session like ``render_artifacts``' (facts, then the project
    metadata, then the installed engine version). ``metadata`` replaces the
    probe's ``project_name`` and empty ``project_description``, or any fact such
    as ``project_kind``, for tests that pin how an always rule renders them. The
    rule renders whatever its ``applies_if``. Raises ``KeyError`` naming the id
    when core ships no such rule.

    Example: ``render_core_rule("project-context", facts, {"project_name": "demo"})``.
    """
    rules = core_rules()
    if rule_id not in rules:
        raise KeyError(f"core ships no rule {rule_id!r}; expected one of {sorted(rules)}")
    context = TemplateContext(
        facts=facts,
        project_name=REFERENCE_PROBE_NAME,
        engine_version=coding_agent_playbook.__version__,
        overrides=dict(metadata or {}),
    )
    # No rule to filter, so no has_file path to anchor: the session renders one rule.
    session = RenderSession.open((), context, repo_root=Path())
    return session.render_rule(rules[rule_id]).body


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
