"""Source guard: engine code never builds an unsandboxed Jinja environment (prK §P1).

Templates are author-controlled *and* agent-writable (``playbook/**/*.md.j2``,
overlay ``resources/``), so every Jinja construction site must go through
``jinja2.sandbox``. ``jinja2.Environment(...)`` and ``jinja2.Template(...)``
(which renders through a shared plain environment) are the two unsandboxed
factories; this test fails on any call to either in ``src/``. The packaged
``resources/`` tree is skipped: its eval-fixture ``setup/`` code is
deliberately unclean needle material, never engine code.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "coding_agent_playbook"

#: jinja2 callables that construct (or implicitly use) a plain, unsandboxed environment.
_UNSANDBOXED_FACTORIES = frozenset({"Environment", "Template"})


def _local_factory_names(tree: ast.Module) -> set[str]:
    """Local names bound to an unsandboxed factory by ``from jinja2... import``."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("jinja2"):
            names |= {a.asname or a.name for a in node.names if a.name in _UNSANDBOXED_FACTORIES}
    return names


def _is_unsandboxed_call(func: ast.expr, local_names: set[str]) -> bool:
    """``Environment(...)`` bound by a jinja2 import, or ``jinja2.Environment(...)``."""
    if isinstance(func, ast.Name):
        return func.id in local_names
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _UNSANDBOXED_FACTORIES
        and isinstance(func.value, ast.Name)
        and func.value.id == "jinja2"
    )


def _unsandboxed_lines(tree: ast.Module) -> list[int]:
    """Line numbers of every unsandboxed Jinja construction in ``tree``."""
    local_names = _local_factory_names(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_unsandboxed_call(node.func, local_names)
    )


def _engine_modules() -> list[Path]:
    return [p for p in sorted(_SRC.rglob("*.py")) if "resources" not in p.relative_to(_SRC).parts]


def test_src_constructs_no_unsandboxed_jinja_environment() -> None:
    offenders = [
        f"{path.relative_to(_SRC).as_posix()}:{line}"
        for path in _engine_modules()
        for line in _unsandboxed_lines(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == [], f"use jinja2.sandbox.SandboxedEnvironment instead at: {offenders}"


def test_guard_flags_plain_constructions_only() -> None:
    tree = ast.parse(
        "from jinja2 import Environment as Env\n"
        "from jinja2.sandbox import SandboxedEnvironment\n"
        "import jinja2\n"
        "a = Env()\n"
        "b = SandboxedEnvironment()\n"
        "c = jinja2.Template('x')\n"
    )
    assert _unsandboxed_lines(tree) == [4, 6]
