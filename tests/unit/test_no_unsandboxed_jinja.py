"""Source guard: engine code never builds an unsandboxed Jinja environment (prK §P1).

Templates are author-controlled *and* agent-writable (``playbook/**/*.md.j2``,
overlay ``resources/``), so every Jinja construction site must go through
``jinja2.sandbox``. The guard is an allow-list, because a deny-list of spellings
is easy to get around by accident (``jinja2.environment.Environment()``, a
module alias, ``NativeEnvironment``):

- a runtime import from ``jinja2`` or a submodule may bind only the names in
  :data:`_ALLOWED_IMPORTS` (the sandbox, loader/undefined helpers and the
  ``jinja2.exceptions`` classes); imports under ``if TYPE_CHECKING:`` are
  annotations and exempt;
- any call whose callee ends in an unsandboxed factory name fails, whatever the
  receiver chain (``a.b.Environment(...)``).

The packaged ``resources/`` tree is skipped: its eval-fixture ``setup/`` code is
deliberately unclean needle material, never engine code. A runtime test then
records every environment the engine actually builds during a sync and an eval
prompt render.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2
import jinja2.exceptions
import pytest
from jinja2.sandbox import SandboxedEnvironment

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.evals.loader import load_eval_task_from_dir
from coding_agent_playbook.evals.prompting import render_prompt
from tests._catalog import CORE_ROOT
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    SyntheticRepoFactory = Callable[..., Path]

_SRC = Path(__file__).resolve().parents[2] / "src" / "coding_agent_playbook"

#: Callables that construct (or implicitly use) a plain, unsandboxed environment.
_UNSANDBOXED_FACTORIES = frozenset(
    {"Environment", "Template", "NativeEnvironment", "NativeTemplate"}
)

_JINJA_EXCEPTIONS = frozenset(
    name
    for name, obj in vars(jinja2.exceptions).items()
    if inspect.isclass(obj) and issubclass(obj, Exception)
)

#: The only names engine code may import from jinja2 at runtime.
_ALLOWED_IMPORTS = _JINJA_EXCEPTIONS | {
    "SandboxedEnvironment",
    "ImmutableSandboxedEnvironment",
    "StrictUndefined",
    "FileSystemLoader",
}


def _is_type_checking_guard(node: ast.If) -> bool:
    """``if TYPE_CHECKING:`` or ``if typing.TYPE_CHECKING:``."""
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _runtime_nodes(tree: ast.Module) -> Iterator[ast.AST]:
    """Every node outside an ``if TYPE_CHECKING:`` body (its ``else`` still runs)."""
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            stack.extend(node.orelse)
            continue
        stack.extend(ast.iter_child_nodes(node))


def _disallowed_import_lines(tree: ast.Module) -> list[int]:
    """Lines of runtime ``from jinja2[.x] import name`` binding a name off the allow-list."""
    return [
        node.lineno
        for node in _runtime_nodes(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "jinja2"
        and any(alias.name not in _ALLOWED_IMPORTS for alias in node.names)
    ]


def _factory_call_lines(tree: ast.Module) -> list[int]:
    """Lines of runtime calls to ``<anything>.Environment(...)`` and friends."""
    return [
        node.lineno
        for node in _runtime_nodes(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _UNSANDBOXED_FACTORIES
    ]


def _unsandboxed_lines(tree: ast.Module) -> list[int]:
    """Line numbers of every guard violation in ``tree``."""
    return sorted({*_disallowed_import_lines(tree), *_factory_call_lines(tree)})


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
    assert _unsandboxed_lines(tree) == [1, 6]


def test_guard_flags_deep_chains_aliases_and_native_environments() -> None:
    """Regression: the guard missed every one of these but ``d``."""
    tree = ast.parse(
        "import jinja2\n"
        "import jinja2.environment\n"
        "from jinja2 import environment as je\n"
        "from jinja2.nativetypes import NativeEnvironment\n"
        "a = jinja2.environment.Environment()\n"
        "b = NativeEnvironment()\n"
        "c = je.Environment()\n"
        "d = jinja2.Environment()\n"
        "e = jinja2.nativetypes.NativeTemplate('x')\n"
    )
    assert _unsandboxed_lines(tree) == [3, 4, 5, 7, 8, 9]


def test_guard_allows_sandbox_exceptions_and_type_checking_imports() -> None:
    tree = ast.parse(
        "from typing import TYPE_CHECKING\n"
        "from jinja2 import FileSystemLoader, StrictUndefined, TemplateError\n"
        "from jinja2.exceptions import SecurityError\n"
        "from jinja2.sandbox import ImmutableSandboxedEnvironment, SandboxedEnvironment\n"
        "if TYPE_CHECKING:\n"
        "    from jinja2 import Environment\n"
        "else:\n"
        "    from jinja2 import Template\n"
    )
    assert _unsandboxed_lines(tree) == [8]


@pytest.fixture
def built_environments(monkeypatch: pytest.MonkeyPatch) -> list[type]:
    """Record the type of every Jinja environment constructed while the test runs."""
    built: list[type] = []
    real_init = jinja2.Environment.__init__

    def recording_init(self: jinja2.Environment, *args: Any, **kwargs: Any) -> None:
        built.append(type(self))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(jinja2.Environment, "__init__", recording_init)
    return built


@pytest.mark.catalog
def test_sync_and_eval_prompts_build_only_sandboxed_environments(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    built_environments: list[type],
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    task_dir = CORE_ROOT / "eval_tasks" / "review-spot-the-bug"
    task = load_eval_task_from_dir(task_dir, source_package="coding_agent_playbook")
    assert "### " in render_prompt(task, strict=True)  # a rule() inclusion rendered

    assert built_environments, "expected the engine to build Jinja environments"
    assert all(issubclass(kind, SandboxedEnvironment) for kind in built_environments)
