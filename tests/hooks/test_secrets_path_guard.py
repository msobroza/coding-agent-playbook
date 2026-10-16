"""secrets-path-guard: credential paths stay out of the agent's reach (specs/prK-hook-pack.md §E.4).

Every case is a real ``playbook-hook simulate pre_tool_use`` dispatch against a
fixture repository holding a ``.env``, its ``.env.example``, a symlink and a
hard link to it, and a credentials module that is code. The guard is
path-only: no case needs git or a subprocess (``FakeProc`` refuses them all).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.handlers._secret_inodes import build_inode_index
from coding_agent_playbook.hook_runtime.handlers.secret_paths import ADVICE, ENV_CONTEXT
from coding_agent_playbook.security.paths import DEFAULT_PATH_POLICY
from tests.hook_runtime.fakes import FakeClock

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "secrets-path-guard"
SECRET: Final = "TOKEN=not-a-real-value\n"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write(".env", SECRET)
    pack_repo.write(".env.example", "TOKEN=\n")
    pack_repo.write("src/auth/credentials.py", "def load() -> str: ...\n")
    pack_repo.write("config/credentials.json", "{}\n")
    os.symlink(".env", pack_repo.root / "notes.txt")
    os.link(pack_repo.root / ".env", pack_repo.root / "notes2.txt")
    aws = _home(pack_repo) / ".aws" / "credentials"
    aws.parent.mkdir(parents=True)
    aws.write_text("[default]\n", encoding="utf-8")
    pack_repo.install_pack([HOOK_ID], wrapper_prefixes=["proxy"])
    return pack_repo


def _home(repo: PackRepo) -> Path:
    """The hook process's home: a real directory, so ``~/.aws/credentials`` exists."""
    return repo.root.parent / "home"


def _run(
    repo: PackRepo,
    deps: Deps,
    tool: str,
    tool_input: dict[str, Any],
    *,
    harness: Harness = Harness.CLAUDE_CODE,
    platform: str = "linux",
    state: Path | None = None,
) -> SimulateReport:
    payload = repo.tool_payload(tool, tool_input)
    runtime = deps(platform=platform, home=str(_home(repo)))
    return repo.simulate(payload, runtime, harness=harness, state=state)


def _read(repo: PackRepo, rel: str) -> tuple[str, dict[str, Any]]:
    return "Read", {"file_path": str(repo.root / rel)}


def _bash(command: str) -> tuple[str, dict[str, Any]]:
    return "Bash", {"command": command}


GOLDEN: Final[list[tuple[str, Callable[[PackRepo], tuple[str, dict[str, Any]]], str, str]]] = [
    ("read-env", lambda r: _read(r, ".env"), "linux", "deny"),
    ("read-ENV-darwin", lambda r: _read(r, ".ENV"), "darwin", "deny"),
    ("read-env-example", lambda r: _read(r, ".env.example"), "linux", "none"),
    ("read-credentials-code", lambda r: _read(r, "src/auth/credentials.py"), "linux", "none"),
    ("read-credentials-json", lambda r: _read(r, "config/credentials.json"), "linux", "deny"),
    ("read-symlink-to-env", lambda r: _read(r, "notes.txt"), "linux", "deny"),
    ("read-hard-link-to-env", lambda r: _read(r, "notes2.txt"), "linux", "ask"),
    ("cat-env", lambda r: _bash("cat .env"), "linux", "deny"),
    ("git-show-env", lambda r: _bash("git show HEAD:.env"), "linux", "deny"),
    ("proxy-cat-aws", lambda r: _bash("proxy cat ~/.aws/credentials"), "linux", "deny"),
    ("bash-c-source", lambda r: _bash("bash -c 'source .env'"), "linux", "deny"),
    (
        "mcp-read-env",
        lambda r: ("mcp__filesystem__read_file", {"path": ".env"}),
        "linux",
        "deny",
    ),
    ("printenv", lambda r: _bash("printenv"), "linux", "context"),
]


@pytest.mark.parametrize(
    ("make", "platform", "expected"),
    [case[1:] for case in GOLDEN],
    ids=[case[0] for case in GOLDEN],
)
def test_golden(
    repo: PackRepo,
    deps: Deps,
    make: Callable[[PackRepo], tuple[str, dict[str, Any]]],
    platform: str,
    expected: str,
) -> None:
    tool, tool_input = make(repo)

    report = _run(repo, deps, tool, tool_input, platform=platform)

    assert report.trace.combined.decision.value == expected


@pytest.mark.parametrize("harness", [Harness.CLAUDE_CODE, Harness.OPENCODE])
def test_both_harnesses_deny_a_read_of_env(repo: PackRepo, deps: Deps, harness: Harness) -> None:
    report = _run(repo, deps, *_read(repo, ".env"), harness=harness)

    assert report.trace.combined.decision is Decision.DENY


def test_reason_is_two_lines_and_names_env_example(repo: PackRepo, deps: Deps) -> None:
    report = _run(repo, deps, *_bash("git log -p -- config/credentials.json"))

    assert report.trace.combined.reason.splitlines() == [
        'Blocked: "config/credentials.json" holds credentials.',
        ADVICE,
    ]
    assert ".env.example" in ADVICE
    assert SECRET.strip() not in report.trace.combined.reason


def test_hardlink_outside_secret_index_passes(repo: PackRepo, deps: Deps) -> None:
    """uv hard-links ``.venv`` installs: a linked file that is no secret's twin is read freely."""
    installed = repo.write(".venv/lib/python3.13/site-packages/pkg/mod.py", "x = 1\n")
    os.link(installed, repo.root / "src" / "vendored.py")

    report = _run(repo, deps, *_read(repo, "src/vendored.py"))

    assert report.trace.combined.decision is Decision.NONE


def test_inode_index_walk_is_bounded_and_skips_ignore_dirs(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    for rel in (".env", ".venv/.env", "node_modules/pkg/.env", "src/a.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x\n", encoding="utf-8")

    def index(**bounds: int) -> tuple[set[str], bool]:
        built = build_inode_index(
            str(root),
            DEFAULT_PATH_POLICY,
            home=str(tmp_path / "home"),
            platform="linux",
            clock=FakeClock(),
            **bounds,
        )
        names = {rel for rel in (".env", ".venv/.env") if _inode(root / rel) in built.inodes}
        return names, built.complete

    assert index() == ({".env"}, True)
    assert index(max_entries=1)[1] is False


def _inode(path: Path) -> tuple[int, int]:
    status = os.lstat(path)
    return status.st_dev, status.st_ino


def test_new_dotenv_write_asks_existing_env_write_denied(repo: PackRepo, deps: Deps) -> None:
    new = _run(repo, deps, "Write", {"file_path": str(repo.root / ".env.local"), "content": "A=\n"})
    old = _run(repo, deps, "Write", {"file_path": str(repo.root / ".env"), "content": "A=\n"})
    scaffold = _run(repo, deps, *_bash("cp .env.example .env.test"))

    assert new.trace.combined.decision is Decision.ASK
    assert new.trace.combined.reason.splitlines()[0] == (
        '".env.local" would be a new credentials file.'
    )
    assert old.trace.combined.decision is Decision.DENY
    assert scaffold.trace.combined.decision is Decision.ASK


def test_secret_search_glob_denied_repo_wide_grep_passes(repo: PackRepo, deps: Deps) -> None:
    globbed = _run(repo, deps, "Glob", {"pattern": "**/.env*"})
    filtered = _run(repo, deps, "Grep", {"pattern": "TOKEN", "glob": "*.pem"})
    repo_wide = _run(repo, deps, "Grep", {"pattern": "TOKEN"})

    assert globbed.trace.combined.decision is Decision.DENY
    assert filtered.trace.combined.decision is Decision.DENY
    assert repo_wide.trace.combined.decision is Decision.NONE


def test_env_context_once_per_session(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    state = tmp_path / "state"

    first = _run(repo, deps, *_bash("env"), state=state)
    second = _run(repo, deps, *_bash("printenv | sort"), state=state)

    assert first.trace.combined.context == (ENV_CONTEXT,)
    assert second.trace.combined.decision is Decision.NONE


def test_extra_globs_extend_allow_paths_relax(pack_repo: PackRepo, deps: Deps) -> None:
    pack_repo.write("tests/fixtures/.env", "FAKE=1\n")
    per_hook = {HOOK_ID: {"extra_globs": ["*.vault"], "allow_paths": ["tests/fixtures/**"]}}
    pack_repo.install_pack([HOOK_ID], per_hook=per_hook)

    vault = _run(pack_repo, deps, *_read(pack_repo, "ops/prod.vault"))
    fixture = _run(pack_repo, deps, *_read(pack_repo, "tests/fixtures/.env"))
    real = _run(pack_repo, deps, *_read(pack_repo, "app/.env"))

    assert vault.trace.combined.decision is Decision.DENY
    assert fixture.trace.combined.decision is Decision.NONE
    assert real.trace.combined.decision is Decision.DENY


def test_degraded_parse_still_judges_words(repo: PackRepo, deps: Deps) -> None:
    report = _run(repo, deps, *_bash("cat <.env 'unterminated"))

    assert report.trace.combined.decision is Decision.DENY


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m ".env loading fix"',
        "grep -rn id_rsa src",
        "echo .env.production",
        "cat config/missing.pem",
    ],
)
def test_prose_and_absent_read_targets_pass(repo: PackRepo, deps: Deps, command: str) -> None:
    """A read leaks only an existing file: search terms and messages are not paths."""
    report = _run(repo, deps, *_bash(command))

    assert report.trace.combined.decision is Decision.NONE


def test_redirect_creating_a_dotenv_asks(repo: PackRepo, deps: Deps) -> None:
    created = _run(repo, deps, *_bash("echo DEBUG=1 > .env.development"))
    appended = _run(repo, deps, *_bash("echo DEBUG=1 >> .env"))

    assert created.trace.combined.decision is Decision.ASK
    assert appended.trace.combined.decision is Decision.DENY
