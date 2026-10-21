"""The ``forge`` package is a pure stdlib leaf the hook hot path may load (spec prF §4, ADR 0003).

import-linter keeps the engine packages and the runtime dependencies out
(``stdlib-leaves``); these tests keep out the stdlib modules that would let it
reach a forge or cost the hot path: ``subprocess``, ``socket``, ``tomllib``,
``importlib.metadata``, ``argparse``, and any file or OS access.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

_PACKAGE: Final = Path(__file__).resolve().parents[2] / "src" / "coding_agent_playbook" / "forge"
#: What a forge module may import: a few stdlib modules and its own package.
_ALLOWED: Final = frozenset({"__future__", "collections.abc", "dataclasses", "re", "typing"})
_OWN: Final = f"{engine_module('coding_agent_playbook.forge')}."
_NEVER: Final = frozenset(
    {
        "argparse",
        "importlib.metadata",
        "jinja2",
        "packaging",
        "socket",
        "subprocess",
        "tomllib",
        "yaml",
    }
)


def _imports(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def test_forge_modules_import_only_the_allowed_stdlib_and_their_package() -> None:
    found = {
        path.name: sorted(
            name
            for name in _imports(path.read_text(encoding="utf-8"))
            if name not in _ALLOWED and not name.startswith(_OWN)
        )
        for path in sorted(_PACKAGE.glob("*.py"))
    }

    assert set(found) == {"__init__.py", "dialects.py", "hosts.py", "operations.py", "tokens.py"}
    assert {name: names for name, names in found.items() if names} == {}


def test_importing_forge_loads_no_forbidden_module() -> None:
    loaded = new_modules_after(
        "import coding_agent_playbook.forge.hosts, coding_agent_playbook.forge.dialects, "
        "coding_agent_playbook.forge.operations, coding_agent_playbook.forge.tokens"
    )

    assert sorted(set(loaded) & _NEVER) == []
    assert [name for name in loaded if name.startswith("coding_agent_playbook.")] == [
        "coding_agent_playbook.forge",
        "coding_agent_playbook.forge.dialects",
        "coding_agent_playbook.forge.hosts",
        "coding_agent_playbook.forge.operations",
        "coding_agent_playbook.forge.tokens",
    ]
