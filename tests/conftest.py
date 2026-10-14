"""Shared fixtures for PR 10 CLI tests.

The ``make_synthetic_repo`` fixture builds a self-contained consumer-repo tree
in ``tmp_path`` with:

- a ``pyproject.toml`` carrying configurable dependencies + python version,
- a ``.coding-agent-playbook.toml`` (committed) consistent with PR A's
  ``Config.from_dict`` shape,
- optionally one or more repo-local rules / prompts under ``playbook/``.

Synthetic repos are the substrate for the CLI tests (sync round-trip, check
dump, validate cross-refs, render, etc.). Engine-shipped artifacts are NOT
created here — the engine ships no rules in v1 (PR 13 adds them), so the
fixture only seeds repo-local content when callers ask for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from pathlib import Path


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
    import os

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


@pytest.fixture
def make_synthetic_repo():
    """Return a builder that creates a synthetic consumer repo in ``tmp_path``.

    Usage::

        def test_x(tmp_path, make_synthetic_repo):
            repo = make_synthetic_repo(
                tmp_path,
                rules=[("python-style", "Body content\\n")],
                prompts=[("refactor", {"slash": "refactor"})],
                pyproject_extras={"dependencies": ["fastapi"]},
            )
            # repo is the path to the consumer-repo root.
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
