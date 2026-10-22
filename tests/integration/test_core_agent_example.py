"""CI gate: the vendored simple-agent-api example keeps every adaptation (prU D64, D78(6)).

The example under ``catalog/core/skills/domino-agents/examples/simple-agent-api/``
runs its own tests in its own environment (the ``core-examples`` CI job), so the
engine never imports it. This gate reads the example as text and syntax trees only
(stdlib, no FastAPI, pydantic-ai or Domino SDK) and pins the points where the
upstream ``simple_agent_api_only`` agent broke an engine rule: the file set, the
byte-identical Apache-2.0 license, the change notice on every adapted file, no
blocking ``requests`` and no ``logging.basicConfig``, nothing built at import, the
Domino SDK behind its two adapter modules, no wildcard CORS origin, a launch
script that execs one server, an agent config with no secret or host key, and no
private framework field read by the evaluation Jobs.
"""

from __future__ import annotations

import ast
import hashlib
import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import LICENSE_SHA256
from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("domino-agents")
EXAMPLE_ROOT: Final = SKILL_ROOT / "examples" / "simple-agent-api"
LICENSE_COPY: Final = SKILL_ROOT / "references" / "LICENSE.simple-agent-api"

#: D78(6): the example's 25 files, A2A included.
EXAMPLE_FILES: Final = frozenset(
    {
        "README.md",
        "pyproject.toml",
        "app.sh",
        "agent_config.yaml",
        "sample_questions.csv",
        "app/settings.py",
        "app/logs.py",
        "app/domino_token.py",
        "app/llm.py",
        "app/agent.py",
        "app/tracing.py",
        "app/chat.py",
        "app/a2a.py",
        "app/main.py",
        "app/asgi.py",
        "evals/evaluators.py",
        "evals/trace_store.py",
        "evals/dev_eval.py",
        "evals/prod_eval.py",
        "tests/conftest.py",
        "tests/fakes.py",
        "tests/test_api.py",
        "tests/test_agent.py",
        "tests/test_domino_token.py",
        "tests/test_evals.py",
    }
)
#: The files that hold changed upstream code (Apache-2.0 section 4(b)); each opens
#: with a one-line change notice (after the shebang of a script).
ADAPTED_FILES: Final = (
    "app.sh",
    "agent_config.yaml",
    "sample_questions.csv",
    "app/domino_token.py",
    "app/llm.py",
    "app/agent.py",
    "app/chat.py",
    "app/a2a.py",
    "app/main.py",
    "evals/evaluators.py",
    "evals/dev_eval.py",
    "evals/prod_eval.py",
)
CHANGE_NOTICE: Final = (
    "# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md."
)
#: The only modules that may import the Domino SDK: the tracer and trace-store adapters.
DOMINO_ADAPTERS: Final = frozenset({"app/tracing.py", "evals/trace_store.py"})
#: Calls nothing may make at module level: the composition root builds these (D64).
BUILT_IN_THE_FACTORY: Final = frozenset({"Agent", "AsyncClient", "AgentSettings"})
#: A config key that names a secret or a host: exact names, then suffixes.
_SECRET_KEYS: Final = frozenset({"api_key", "key", "token", "url", "base_url", "host"})
_SECRET_SUFFIXES: Final = ("_key", "_token", "_url", "_host")
_YAML_KEY_RE: Final = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*:")


def _modules() -> dict[str, ast.Module]:
    """Every Python module under app/ and evals/, parsed, by POSIX path."""
    return {
        rel: ast.parse((EXAMPLE_ROOT / rel).read_text(encoding="utf-8"), filename=rel)
        for rel in sorted(EXAMPLE_FILES)
        if rel.endswith(".py") and rel.split("/")[0] in {"app", "evals"}
    }


def _call_name(node: ast.Call) -> str:
    """``Agent(...)`` -> ``"Agent"``; ``httpx.AsyncClient(...)`` -> ``"AsyncClient"``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _imported_modules(tree: ast.Module) -> set[str]:
    """Every module an import statement or ``importlib.import_module("...")`` names."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif (
            isinstance(node, ast.Call)
            and _call_name(node) == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def _module_level_calls(tree: ast.Module) -> list[str]:
    """The names of calls made when the module is imported (not inside a def or class)."""
    found: list[str] = []
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        found += [_call_name(node) for node in ast.walk(statement) if isinstance(node, ast.Call)]
    return found


def _example_files(root: Path) -> set[str]:
    """Every shipped file of the example: dot entries and bytecode caches are tool output."""
    files = set()
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if path.is_file() and not any(p.startswith(".") or p == "__pycache__" for p in parts):
            files.add("/".join(parts))
    return files


def test_the_example_ships_exactly_its_25_files() -> None:
    assert _example_files(EXAMPLE_ROOT) == EXAMPLE_FILES


def test_the_apache_license_copy_is_byte_identical() -> None:
    digest = hashlib.sha256(LICENSE_COPY.read_bytes()).hexdigest()
    assert digest == "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
    assert LICENSE_SHA256["simple-agent-api"] == digest


@pytest.mark.parametrize("rel", ADAPTED_FILES)
def test_every_adapted_file_opens_with_the_change_notice(rel: str) -> None:
    lines = (EXAMPLE_ROOT / rel).read_text(encoding="utf-8").splitlines()
    first = lines[1] if lines[0].startswith("#!") else lines[0]
    assert first == CHANGE_NOTICE


def test_no_module_imports_requests_or_calls_basic_config() -> None:
    for rel, tree in _modules().items():
        assert not {m for m in _imported_modules(tree) if m.split(".")[0] == "requests"}, rel
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        assert "basicConfig" not in {_call_name(call) for call in calls}, rel


def test_only_asgi_builds_settings_and_nothing_builds_the_agent_or_a_client_at_import() -> None:
    built = {
        rel: [name for name in _module_level_calls(tree) if name in BUILT_IN_THE_FACTORY]
        for rel, tree in _modules().items()
    }
    assert {rel: names for rel, names in built.items() if names} == {
        "app/asgi.py": ["AgentSettings"]
    }


def test_only_the_two_adapters_import_the_domino_sdk() -> None:
    importers = {
        rel
        for rel, tree in _modules().items()
        if any(name.split(".")[0] == "domino" for name in _imported_modules(tree))
    }
    assert importers == DOMINO_ADAPTERS


def test_cors_origins_never_hold_a_wildcard() -> None:
    for rel, tree in _modules().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "allow_origins":
                literals = [c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant)]
                assert "*" not in literals, rel


def test_the_launch_script_execs_one_server_on_the_app_port() -> None:
    script = (EXAMPLE_ROOT / "app.sh").read_text(encoding="utf-8")
    assert "exec " in script
    assert "0.0.0.0" in script
    assert "8888" in script
    assert "--debug" not in script


def test_the_agent_config_names_no_secret_or_host_key() -> None:
    text = (EXAMPLE_ROOT / "agent_config.yaml").read_text(encoding="utf-8")
    keys = {m.group(1) for line in text.splitlines() if (m := _YAML_KEY_RE.match(line))}
    assert "max_tokens" in keys
    offending = {k for k in keys if k in _SECRET_KEYS or k.endswith(_SECRET_SUFFIXES)}
    assert offending == set()


def test_the_evaluation_jobs_read_no_private_framework_field() -> None:
    for rel, tree in _modules().items():
        if not rel.startswith("evals/"):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                assert node.slice.value != "_state", rel
