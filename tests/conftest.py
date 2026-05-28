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

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable


_DEFAULT_CONFIG = """\
schema_version = 1
[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

adapters_enabled = ["continue", "claude_code", "opencode"]

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""


def _write_rule(target: Path, rule_id: str, *, name: str | None = None, body: str = "Body\n") -> None:
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
        prompts: Iterable[tuple[str, dict]] | None = None,
        pyproject_extras: dict | None = None,
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
