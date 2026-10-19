"""Shared fixtures for PR 10 CLI tests.

The ``make_synthetic_repo`` fixture builds a self-contained consumer-repo tree
in ``tmp_path`` with:

- a ``pyproject.toml`` carrying configurable dependencies + python version,
- a ``.coding-agent-playbook.toml`` (committed) consistent with PR A's
  ``Config.from_dict`` shape,
- optionally one or more repo-local rules / prompts under ``playbook/``.

Synthetic repos are the substrate for the CLI tests (sync round-trip, check
dump, validate cross-refs, render, etc.). Engine-shipped artifacts are NOT
copied here: every sync reads the real engine catalog, so the rules in core
apply and the core skills whose rules apply (``python-coding`` and
``python-tooling`` in every synthetic repo) are written next to a test's own
content. Assert on the test's own artifacts, never on a whole skills root. The
fixture only seeds repo-local content when callers ask for it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.git_env import REPO_LOCATION_GIT_VARS
from tests.attendance_env import ATTENDANCE_ENV_VARS
from tests.hook_samples import write_hook

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from pathlib import Path

    from tests.hook_payloads import HookPayloadCase


def pytest_sessionstart(session: pytest.Session) -> None:
    """Drop the inherited variables that pin a git repository, for the whole run.

    Git exports absolute ``GIT_DIR``/``GIT_INDEX_FILE`` to hooks in a linked
    worktree, and pre-commit passes them on to the ``catalog-checks`` hook. Any
    test running real git without ``hermetic_git_env`` (``materialize`` in the
    shipped-task tests) would then commit onto the developer's branch and
    overwrite their index. Runs before collection, so collection-time git is
    covered too.
    """
    for name in REPO_LOCATION_GIT_VARS:
        os.environ.pop(name, None)


_DEFAULT_CONFIG = """\
schema_version = 1
adapters_enabled = ["continue", "claude_code", "opencode"]
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""


def _write_rule(
    target: Path, rule_id: str, *, name: str | None = None, body: str = "Body\n"
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    display_name = name or rule_id.replace("-", " ").title()
    text = (
        "---\n"
        f"id: {rule_id}\n"
        f"name: {display_name}\n"
        "description: A repo-local rule\n"
        "scope: always\n"
        "priority: 50\n"
        "---\n"
        f"{body}"
    )
    target.write_text(text, encoding="utf-8")


def _write_prompt(
    target: Path,
    prompt_id: str,
    *,
    slash: str | None = None,
    name: str | None = None,
    body: str = "Prompt body\n",
    includes_rules: Iterable[str] | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    display_name = name or prompt_id.replace("-", " ").title()
    slash_value = slash or prompt_id
    lines = [
        "---",
        f"id: {prompt_id}",
        f"name: {display_name}",
        "description: A repo-local prompt",
        f"slash: {slash_value}",
    ]
    if includes_rules is not None:
        rules_list = list(includes_rules)
        if rules_list:
            lines.append("includes_rules:")
            for rid in rules_list:
                lines.append(f"  - {rid}")
    lines.append("---")
    lines.append(body)
    target.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(scope="session", autouse=True)
def attended_session_env() -> Iterator[None]:
    """Clear the runner's attendance variables (``CI``, ``GITHUB_ACTIONS``, ...) for the session.

    ``is_unattended`` turns every ``ask`` into a ``deny`` under them, so an
    in-process dispatch, a ``RuntimeDeps()`` snapshot of ``os.environ`` or a
    subprocess inheriting it would test the unattended path on CI only (PR #32).
    Session scope also covers module-scoped fixtures, and a function-scoped
    ``monkeypatch`` that sets one is undone back to "unset". A test that wants
    an unattended run sets one itself. See :mod:`tests.attendance_env`.
    """
    with pytest.MonkeyPatch.context() as patch:
        for name in ATTENDANCE_ENV_VARS:
            patch.delenv(name, raising=False)
        yield


def apply_hermetic_git_env(
    monkeypatch: pytest.MonkeyPatch, *, ceiling: Path, config_home: Path
) -> None:
    """Point every real ``git`` call at the test's own tree and config only.

    - Drops **every** inherited ``GIT_*`` variable first. Git exports absolute
      ``GIT_DIR``/``GIT_INDEX_FILE`` to hooks in a linked worktree, so a suite run
      from a pre-commit/pre-push hook would otherwise ``init``/``add``/``commit``
      into the developer's own repository.
    - Ignores the global and system gitconfig (``GIT_CONFIG_GLOBAL`` /
      ``GIT_CONFIG_NOSYSTEM``: no hooksPath, signing, identity, excludesFile).
    - Points ``XDG_CONFIG_HOME`` at the empty ``config_home``: git reads its
      *default* global excludes (``$XDG_CONFIG_HOME/git/ignore``, else
      ``~/.config/git/ignore``) and attributes files even with no gitconfig.
    - Stops repository discovery at ``ceiling`` and sets a fixed identity.

    Only environment variables change — ``subprocess`` itself is never patched.
    """
    for name in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(ceiling))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "playbook-test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "playbook-test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "playbook-test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "playbook-test@example.invalid")


@pytest.fixture
def hermetic_git_env(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isolate real ``git`` calls from the developer's machine and repository.

    See :func:`apply_hermetic_git_env`; discovery stops at ``tmp_path``'s parent
    and the empty config home lives outside ``tmp_path`` (often the repo root).
    """
    apply_hermetic_git_env(
        monkeypatch, ceiling=tmp_path.parent, config_home=tmp_path_factory.mktemp("xdg-config")
    )


#: Bound on each fixture-building ``git`` call of :func:`real_git`.
GIT_TIMEOUT_S = 30


@pytest.fixture
def real_git(hermetic_git_env: None) -> Callable[..., str]:
    """Return ``run(*args, cwd=path) -> stdout`` for the real git, or skip without one.

    Shared by the hook runtime and the pack hook suites; git is isolated from
    the developer's machine through :func:`hermetic_git_env`.

    Example::

        def test_x(real_git, tmp_path):
            real_git("init", "-q", cwd=tmp_path)
    """
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    def _run(*args: str, cwd: Path) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
        return completed.stdout.strip()

    return _run


@pytest.fixture
def make_synthetic_repo():
    """Return a builder that creates a synthetic consumer repo in ``tmp_path``.

    Usage::

        def test_x(tmp_path, make_synthetic_repo):
            repo = make_synthetic_repo(
                tmp_path,
                rules=[("python-style", "Body content\\n")],
                prompts=[("tidy-up", {"slash": "tidy-up"})],
                pyproject_extras={"dependencies": ["fastapi"]},
            )
            # repo is the path to the consumer-repo root.

    Prefer artifact ids the engine does not ship: a repo-local ``refactor``
    prompt overrides the engine's without its ``eval_tasks``, which fails
    ``playbook validate`` and so makes ``playbook sync`` refuse to write.
    """

    def _build(
        tmp_path: Path,
        *,
        config_text: str = _DEFAULT_CONFIG,
        rules: Iterable[tuple[str, str]] | None = None,
        prompts: Iterable[tuple[str, dict[str, Any]]] | None = None,
        pyproject_extras: dict[str, Any] | None = None,
        write_config: bool = True,
    ) -> Path:
        repo = tmp_path
        # pyproject.toml: simple but parseable. Dependencies/python pin
        # adjustable by callers via ``pyproject_extras``.
        py_lines = [
            "[project]",
            'name = "synthetic"',
            'requires-python = ">=3.12"',
        ]
        if pyproject_extras and "dependencies" in pyproject_extras:
            deps = pyproject_extras["dependencies"]
            quoted = ", ".join(f'"{d}"' for d in deps)
            py_lines.append(f"dependencies = [{quoted}]")
        else:
            py_lines.append("dependencies = []")
        (repo / "pyproject.toml").write_text("\n".join(py_lines) + "\n", encoding="utf-8")

        if write_config:
            (repo / ".coding-agent-playbook.toml").write_text(config_text, encoding="utf-8")

        # Optional repo-local artifacts under ``playbook/``.
        for rule_id, body in rules or []:
            _write_rule(repo / "playbook" / "rules" / f"{rule_id}.md", rule_id, body=body)
        for prompt_id, kwargs in prompts or []:
            _write_prompt(
                repo / "playbook" / "prompts" / f"{prompt_id}.md",
                prompt_id,
                **kwargs,
            )
        return repo

    return _build


@pytest.fixture
def make_package(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., str]]:
    """Return a builder for throwaway packages importable during this test only.

    ``make_package("cap_boom", init="raise RuntimeError('boom')", resources=True)``
    writes ``cap_boom/__init__.py`` (and an empty ``resources/`` dir) under a fresh
    directory outside ``tmp_path`` that is prepended to ``sys.path``, and returns
    the name. Dotted names nest (build the parent first to give it an
    ``__init__.py``). Every name built is dropped from ``sys.modules`` afterwards.
    """
    import sys

    root = tmp_path_factory.mktemp("packages")
    monkeypatch.syspath_prepend(str(root))
    built: list[str] = []

    def _make(name: str, *, init: str = "", resources: bool = False) -> str:
        package = root.joinpath(*name.split("."))
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text(init, encoding="utf-8")
        if resources:
            (package / "resources").mkdir()
        built.append(name)
        return name

    yield _make
    for name in built:
        sys.modules.pop(name, None)


@pytest.fixture
def make_hook() -> Callable[..., Path]:
    """Return a builder that writes one hook directory (specs/prK-lifecycle-hooks.md §A.1).

    ``make_hook(root, "guard-y", tier="opt-in")`` writes
    ``<root>/protect/guard-y/HOOK.md`` from a minimal valid frontmatter with
    those keys replaced, and returns the path (``category=``, ``marker=``,
    ``body=`` and ``scripts=`` adjust the layout; see
    :func:`tests.hook_samples.write_hook`).
    """
    return write_hook


@pytest.fixture
def sample_hook_handlers(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, ...]]:
    """Install the sample handler distribution so the sample hooks' builtins are registered.

    ``playbook validate`` checks every builtin name against the handler registry
    (H6); the engine ships no handlers before K5, so tests whose hooks bind
    ``guard_x`` / ``guard_y`` / ``guard_z`` resolve them through a real
    ``coding_agent_playbook.hook_handlers`` entry point. Yields the names.
    """
    import sys

    from tests.hook_samples import (
        SAMPLE_HANDLER_NAMES,
        SAMPLE_HANDLERS_PACKAGE,
        install_sample_handlers,
    )

    root = tmp_path_factory.mktemp("sample-handlers")
    install_sample_handlers(root)
    monkeypatch.syspath_prepend(str(root))
    yield SAMPLE_HANDLER_NAMES
    sys.modules.pop(SAMPLE_HANDLERS_PACKAGE, None)


@pytest.fixture
def hook_payload() -> Callable[[str, str, str], HookPayloadCase]:
    """Return the loader of the golden harness payloads (specs/prK-lifecycle-hooks.md §D.9).

    ``hook_payload("claude_code", "pre_tool_use", "bash_rm_root")`` reads
    ``tests/fixtures/hook_payloads/claude_code/pre_tool_use/bash_rm_root.json``
    and its ``.expected.json``; shared by ``tests/hook_runtime``, ``tests/hooks``
    and ``tests/security``. See :mod:`tests.hook_payloads` for the file format.
    """
    # Imported here so that only the suites using payloads load the hook runtime.
    from tests.hook_payloads import load_hook_payload

    return load_hook_payload


#: CPython's default int-to-str digit limit (``sys.int_info.default_max_str_digits``).
DEFAULT_INT_MAX_STR_DIGITS = 4300


@pytest.fixture
def default_int_max_str_digits() -> Iterator[int]:
    """Pin ``sys.set_int_max_str_digits`` to CPython's default for one test; yield it.

    The big-integer writer tests exercise the path past that limit, which
    ``PYTHONINTMAXSTRDIGITS`` (``0`` disables it) or another test can move, so
    each pins it and restores the old value afterwards (F.I.R.S.T.: repeatable).
    """
    import sys

    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(DEFAULT_INT_MAX_STR_DIGITS)
    try:
        yield DEFAULT_INT_MAX_STR_DIGITS
    finally:
        sys.set_int_max_str_digits(previous)
