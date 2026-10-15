"""Where the shipped content lives in this checkout, for tests that pin it by path.

The roots are anchored on the checkout (``REPO_ROOT``), not on the production
resolver, so path pins stay independent of the code under test: a resolver bug
cannot carry a test's expectations along with it. Tests import their roots from
here, so a change to the content layout edits this one module.
"""

from __future__ import annotations

from pathlib import Path

#: The repository checkout this test suite runs from.
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
#: The engine's core content: ``eval_tasks/``, ``prompts/``, ``rules/``, ``skills/``, ...
CORE_ROOT: Path = REPO_ROOT / "src/coding_agent_playbook/resources"
#: The parent of every bundled plugin's directory.
PLUGINS_ROOT: Path = REPO_ROOT / "src/coding_agent_playbook/packs"


def plugin_root(name: str) -> Path:
    """Return bundled plugin *name*'s content root, the directory holding ``skills/``.

    Example::

        plugin_root("python_design") / "skills" / "python-architecture"
    """
    return PLUGINS_ROOT / name / "resources"


def plugin_files_root(name: str) -> Path:
    """Return bundled plugin *name*'s top directory, holding ``LICENSE`` and ``ATTRIBUTIONS.md``.

    Example::

        plugin_files_root("python_design") / "ATTRIBUTIONS.md"
    """
    return PLUGINS_ROOT / name
