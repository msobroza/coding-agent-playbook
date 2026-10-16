"""Where the catalog (the shipped content) lives in this checkout, for tests that pin it by path.

The catalog roots are anchored on the checkout (``REPO_ROOT / "catalog"``), not
on the production resolver, so path pins stay independent of the code under
test: a resolver bug cannot carry a test's expectations along with it. The one
exception is ``PRECOMMIT_TEMPLATE_DIR``: it is engine wiring, not content, and is
computed through the imported package with ``importlib.resources``. Tests import
their roots from here, so a change to the catalog layout edits this one module.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

#: The repository checkout this test suite runs from.
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
#: The checkout's catalog: ``README.md``, ``core/`` and ``plugins/``.
CATALOG_ROOT: Path = REPO_ROOT / "catalog"
#: The engine's core layer: ``ATTRIBUTIONS.md``, ``eval_tasks/``, ``hooks/``, ``prompts/``, ``rules/``.
CORE_ROOT: Path = CATALOG_ROOT / "core"
#: The parent of every bundled plugin's directory.
PLUGINS_ROOT: Path = CATALOG_ROOT / "plugins"
#: The pre-commit template's directory. It is engine wiring, not content, so it
#: stays inside the package and resolves through the imported package rather
#: than ``REPO_ROOT``: it must ship wherever the engine's code does.
PRECOMMIT_TEMPLATE_DIR: Path = Path(
    str(resources.files("coding_agent_playbook") / "templates" / "precommit")
)


def bundled_plugin_dirs() -> list[Path]:
    """Return every directory directly under :data:`PLUGINS_ROOT`, sorted.

    Catalog gates iterate this listing rather than naming plugins, so a new
    ``catalog/plugins/<name>/`` is gated with no test edit (acceptance 5). It is
    not filtered by the leaf rule: a misnamed directory is still scanned, and the
    leaf-rule guard in ``test_catalog_layout.py`` fails on its name.

    Example::

        [path.name for path in bundled_plugin_dirs()]  # ['python_design', 'superpowers']
    """
    return sorted(entry for entry in PLUGINS_ROOT.iterdir() if entry.is_dir())


def plugin_root(name: str) -> Path:
    """Return bundled plugin *name*'s layer root, the directory holding ``skills/``.

    Example::

        plugin_root("python_design") / "skills" / "python-architecture"
    """
    return PLUGINS_ROOT / name


def plugin_files_root(name: str) -> Path:
    """Return bundled plugin *name*'s top directory, holding ``LICENSE`` and ``ATTRIBUTIONS.md``.

    Since the move to ``catalog/plugins/<name>/`` this is the same directory as
    :func:`plugin_root`: the root files sit next to ``skills/``.

    Example::

        plugin_files_root("python_design") / "ATTRIBUTIONS.md"
    """
    return PLUGINS_ROOT / name
