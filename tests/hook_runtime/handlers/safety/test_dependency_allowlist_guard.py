"""dependency-allowlist-guard: the package manager, new direct deps, lockfiles (specs/prK-hook-pack.md §E.4).

The golden table runs the shipped ``HOOK.md`` through ``playbook-hook simulate
pre_tool_use`` against a uv fixture repo (``facts.package_manager = uv``; the
declared dependencies ``httpx``, ``foo-bar`` and ``pytest``). Every case starts from fresh session state
unless it passes ``state``; ``FakeProc`` fails the test on any spawn, and no
case may reach an index.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.config.tables.hooks import HooksConfig, parse_guardrails_config
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.judges.dependency_tiers import dependency_policy
from coding_agent_playbook.hooks.contract.handler_catalog import RegistryCatalog
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from coding_agent_playbook.hooks.resolution.effective import merged_handler_config
from tests.engine_modules import engine_module
from tests.hook_runtime.fakes import FakeGit
from tests.hook_runtime.handlers.pack_repo import engine_hook

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "dependency-allowlist-guard"
#: The guard's handler and its judges (hook_runtime/judges/ since N14): the import spy's importers.
_GUARD_PACKAGES: Final = tuple(
    f"{engine_module(package)}."
    for package in (
        "coding_agent_playbook.hook_runtime.handlers",
        "coding_agent_playbook.hook_runtime.judges",
    )
)
#: What ``detect()`` reads from :data:`PYPROJECT` with a ``uv.lock`` beside it.
UV_FACTS: Final = {
    "package_manager": "uv",
    "dependencies": {"httpx": ">=0.27", "foo-bar": ""},
    "dev_dependencies": {"pytest": ""},
}
PYPROJECT: Final = (
    '[project]\nname = "demo"\ndependencies = ["httpx>=0.27", "Foo_Bar"]\n\n'
    '[dependency-groups]\ndev = ["pytest"]\n'
)
ADDED: Final = PYPROJECT.replace('"Foo_Bar"]', '"Foo_Bar", "rich>=13"]')
REFORMATTED: Final = (
    '[project]\nname = "demo"\ndependencies = [\n    "HTTPX >= 0.28",\n    "foo-bar",\n]\n\n'
    '[dependency-groups]\ndev = ["pytest>=8"]\n'
)


def _install(repo: PackRepo, **per_hook: Any) -> PackRepo:
    repo.write("pyproject.toml", PYPROJECT)
    repo.write("uv.lock", "version = 1\n")
    repo.install_pack(
        [HOOK_ID],
        detect=DetectInputs(facts=dict(UV_FACTS)),
        per_hook={HOOK_ID: per_hook} if per_hook else None,
    )
    return repo


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    return _install(pack_repo)


def _run(
    repo: PackRepo, deps: Deps, tool: str, tool_input: dict[str, Any], *, state: Path | None = None
) -> SimulateReport:
    payload = repo.tool_payload(tool, tool_input)
    return repo.simulate(payload, deps(git=FakeGit()), state=state)


def _bash(repo: PackRepo, deps: Deps, command: str, *, state: Path | None = None) -> SimulateReport:
    return _run(repo, deps, "Bash", {"command": command}, state=state)


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


GOLDEN: Final[list[tuple[str, Decision]]] = [
    ("pip install requests", Decision.DENY),
    ("python3 -m pip install requests", Decision.DENY),
    ("uv pip install requests", Decision.DENY),
    ("poetry add requests", Decision.DENY),
    ("uv add requests", Decision.ASK),
    ("uv add --dev Pytest-Cov", Decision.ASK),
    ("uv add HTTPX", Decision.NONE),  # declared: grandfathered
    ("uv sync", Decision.NONE),
    ("uv lock", Decision.NONE),
    ("uv run pytest -q", Decision.NONE),
    ("uv run --with rich python x.py", Decision.ASK),
    ("uvx ruff check", Decision.ASK),
    ("uvx --from git+https://github.com/org/tool.git tool", Decision.ASK),
    ("pip install -e .", Decision.NONE),
    ('pip install -e ".[dev]"', Decision.NONE),
    ("pip install -r requirements.txt", Decision.NONE),  # the project's own manifest
    ("pip install -U pip", Decision.NONE),
    ("uv add --extra-index-url https://download.pytorch.org/whl/cu121 torch", Decision.ASK),
    ("uv add --index-url https://pypi.org/simple httpx", Decision.NONE),
    ("pip download sdist-pkg", Decision.ASK),
    ("npm install left-pad", Decision.ASK),
    ("npm ci", Decision.NONE),
    ("conda install -c conda-forge numpy=1.26", Decision.ASK),
    ("echo pip install requests", Decision.NONE),
    ("ls -la", Decision.NONE),
]


@pytest.mark.parametrize(("command", "expected"), GOLDEN)
def test_golden(repo: PackRepo, deps: Deps, command: str, expected: Decision) -> None:
    assert _decision(_bash(repo, deps, command)) is expected


def test_mismatch_names_the_corrected_command(repo: PackRepo, deps: Deps) -> None:
    report = _bash(repo, deps, "pip install requests")
    dev = _bash(repo, deps, "poetry add --group dev Pytest_Cov")

    assert report.trace.combined.reason.splitlines()[0] == (
        "This repository uses uv: run `uv add requests` instead of `pip install`."
    )
    assert "`uv add --dev pytest-cov`" in dev.trace.combined.reason


def test_new_dependency_asks_once_per_package_per_session(
    repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    state = tmp_path / "state"

    first = _bash(repo, deps, "uv add requests", state=state)
    again = _bash(repo, deps, "uv add requests", state=state)
    other = _bash(repo, deps, "uv add rich", state=state)

    assert first.trace.combined.reason == (
        "Adding requests. The playbook says don't add new dependencies without asking."
    )
    assert [_decision(r) for r in (first, again, other)] == [
        Decision.ASK,
        Decision.NONE,
        Decision.ASK,
    ]


def test_pep503_spellings_are_one_package(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    """``Foo_Bar`` == ``foo-bar`` == ``foo.bar``: one ask for all three spellings."""
    state = tmp_path / "state"

    decisions = [
        _decision(_bash(repo, deps, f"uv add {name}", state=state))
        for name in ("Baz_Qux", "baz-qux", "baz.qux")
    ]

    assert decisions == [Decision.ASK, Decision.NONE, Decision.NONE]


def test_a_deny_marks_nothing_so_the_corrected_command_still_asks(
    repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    state = tmp_path / "state"

    wrong = _bash(repo, deps, "pip install requests", state=state)
    right = _bash(repo, deps, "uv add requests", state=state)

    assert [_decision(wrong), _decision(right)] == [Decision.DENY, Decision.ASK]


def _edit(old: str, new: str) -> dict[str, str]:
    return {"file_path": "pyproject.toml", "old_string": old, "new_string": new}


def test_manifest_edits_count_only_new_names(repo: PackRepo, deps: Deps) -> None:
    added = _run(repo, deps, "Edit", _edit(PYPROJECT, ADDED))
    reformatted = _run(repo, deps, "Write", {"file_path": "pyproject.toml", "content": REFORMATTED})
    requirements = _run(
        repo, deps, "Write", {"file_path": "requirements-dev.txt", "content": "Foo.Bar\nrich\n"}
    )

    assert _decision(added) is Decision.ASK
    assert added.trace.combined.reason.startswith("Adding rich.")
    assert _decision(reformatted) is Decision.NONE
    assert _decision(requirements) is Decision.ASK
    assert "foo-bar" not in requirements.trace.combined.reason  # declared in pyproject


def test_manifest_edit_adding_an_index_asks(repo: PackRepo, deps: Deps) -> None:
    content = "--extra-index-url https://download.pytorch.org/whl/cu121\nhttpx\n"

    report = _run(repo, deps, "Write", {"file_path": "requirements.txt", "content": content})

    assert _decision(report) is Decision.ASK
    assert report.trace.combined.reason.startswith(
        '`requirements.txt` adds the package index "download.pytorch.org"'
    )


@pytest.mark.parametrize("lockfile", ["uv.lock", "poetry.lock"])
def test_lockfile_hand_edit_denies(repo: PackRepo, deps: Deps, lockfile: str) -> None:
    report = _run(repo, deps, "Write", {"file_path": lockfile, "content": "version = 2\n"})

    assert _decision(report) is Decision.DENY
    assert report.trace.combined.reason.splitlines()[1].startswith("Regenerate it with `")


def test_unparsable_pyproject_edit_asks(repo: PackRepo, deps: Deps) -> None:
    report = _run(repo, deps, "Edit", _edit("[project]", "[project"))

    assert _decision(report) is Decision.ASK


def test_index_mode_deny_from_the_overlay(pack_repo: PackRepo, deps: Deps) -> None:
    repo = _install(pack_repo, index_mode="deny")

    report = _bash(repo, deps, "uvx --extra-index-url https://download.pytorch.org/whl/cu121 x")

    assert _decision(report) is Decision.DENY
    assert '"download.pytorch.org"' in report.trace.combined.reason


def test_overlay_allowlist_denies_with_did_you_mean(pack_repo: PackRepo, deps: Deps) -> None:
    repo = _install(pack_repo, allowlist=["requests", "numpy"])

    typo = _bash(repo, deps, "uv add reqeusts")
    allowed = _bash(repo, deps, "uv add numpy")

    assert _decision(typo) is Decision.DENY
    assert "reqeusts (did you mean requests?)" in typo.trace.combined.reason
    assert _decision(allowed) is Decision.NONE


def test_required_index_denies_any_other_index(pack_repo: PackRepo, deps: Deps) -> None:
    repo = _install(pack_repo, required_index="https://pypi.corp.example/simple/")

    other = _bash(repo, deps, "uv add --index-url https://pypi.org/simple httpx")
    internal = _bash(repo, deps, "uv add --index-url https://pypi.corp.example/simple httpx")

    assert _decision(other) is Decision.DENY
    assert _decision(internal) is Decision.NONE


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        # prF §14: the URLs compare without userinfo, case-blind in scheme and host, no trailing /
        ("https://ci:xxx@pypi.corp.example/simple", Decision.NONE),
        ("HTTPS://PyPI.Corp.Example/simple/", Decision.NONE),
        ("https://pypi.corp.example/simple//", Decision.NONE),
        ("https://pypi.corp.example/Simple", Decision.DENY),  # a path stays case-sensitive
        ("https://pypi.corp.example.evil.io/simple", Decision.DENY),
        ("http://pypi.corp.example/simple", Decision.DENY),
    ],
)
def test_required_index_compares_normalized_urls(
    pack_repo: PackRepo, deps: Deps, index: str, expected: Decision
) -> None:
    repo = _install(pack_repo, required_index="https://deploy@Pypi.Corp.Example/simple/")

    assert _decision(_bash(repo, deps, f"uv add --index-url {index} httpx")) is expected


def test_unparsed_install_asks(repo: PackRepo, deps: Deps) -> None:
    assert _decision(_bash(repo, deps, "pip install 'requests")) is Decision.ASK


@pytest.fixture
def import_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every ``tomllib`` / ``difflib`` import statement a guard module executes.

    The importer's globals tell a handler's import from the dispatcher's own
    (its lockfile digest read uses ``tomllib`` on a cold cache).
    """
    seen: list[str] = []
    real_import = builtins.__import__

    def spy(name: str, globals: Any = None, *args: Any, **kwargs: Any) -> Any:
        importer = (globals or {}).get("__name__", "")
        if name in ("tomllib", "difflib") and importer.startswith(_GUARD_PACKAGES):
            seen.append(name)
        return real_import(name, globals, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", spy)
    yield seen


def test_tomllib_imported_only_on_manifest_branch(
    repo: PackRepo, deps: Deps, import_spy: list[str]
) -> None:
    """§D.1 branch-local rows: ``tomllib`` for a pyproject edit, ``difflib`` for an allowlist."""
    _bash(repo, deps, "uv add requests")
    on_bash = list(import_spy)
    _run(repo, deps, "Edit", _edit(PYPROJECT, ADDED))

    assert "tomllib" not in on_bash and "difflib" not in on_bash
    assert "tomllib" in import_spy[len(on_bash) :]
    assert "difflib" not in import_spy


def test_guardrails_dependencies_domain_reaches_the_policy() -> None:
    """``[guardrails.dependencies]`` mode (as ``mode``) and allowlist merge into the config (§B.3)."""
    hook = engine_hook(HOOK_ID)
    assert hook.frontmatter.handler is not None
    guardrails = parse_guardrails_config({"dependencies": {"mode": "deny", "allowlist": ["Rich"]}})

    merged = merged_handler_config(
        hook, hook.frontmatter.handler, HooksConfig(), guardrails, schemas=RegistryCatalog()
    )
    policy = dependency_policy({}, merged)

    assert (policy.index_mode, policy.allowlist) == (Decision.DENY, ("rich",))
