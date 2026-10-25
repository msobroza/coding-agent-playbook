"""Docs-consistency guard: the short user README and the contributor guide (prU D-03).

D55 (specs/prU-core-python-skills.md) shrinks ``README.md`` to a user README of about
80 lines and moves every other section, unchanged, into ``docs/``; D66, D57, D63, D70
and D71 fix what its install and setup lines say, and D19 asks for one sentence on
Continue's missing license copy. D32 turns the upstream rule template into a "Writing a
rule" section of ``catalog/README.md`` that must cover every frontmatter key the engine
accepts. Prose-only: these tests read markdown and the rule dataclass, never engine
behaviour.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from coding_agent_playbook.artifacts.rule import RuleFrontmatter
from tests._catalog import CATALOG_ROOT, REPO_ROOT
from tests._docs import USER_DOC_PAGES, user_docs
from tests._markdown import markdown_headings

_README = REPO_ROOT / "README.md"
#: D55's "about 80 lines", with a little slack for wrapping.
_README_MAX_LINES = 90
#: D55's "6-line ASCII overview": the content lines of the README's text block.
_OVERVIEW_LINES = 6
#: The only level-2 sections the short README holds (D55), in order.
_README_SECTIONS = (
    "## What it is",
    "## Install",
    "## Set up a repo",
    "## Keep it current",
    "## Contribute to the catalog",
    "## Links",
)
#: Every heading of the README before D55; each must survive somewhere under docs/.
_FORMER_README_HEADINGS = (
    "## Why coding-agent-playbook?",
    "## Status",
    "## Architecture",
    "### Engine packages",
    "## Editing content",
    "## Using the playbook in an external repo",
    "### 1. Install",
    "### 2. Initialize",
    "### 3. Generate",
    "### 4. Define which resources apply",
    "## Skills: one source, every Agent-Skills root",
    "### Rules inside skills",
    "## Bundled plugins: superpowers, mattpocock_skills",
    "## Agent Harness support (opt-in)",
    "### The `agent_harness` adapter",
    "### Importing and validating harness trees",
    "## Pre-commit integration",
    "### Pre-commit hooks",
    "## Assistant lifecycle hooks",
    "### Turning them on",
    "### The catalog's hooks",
    "#### Protect the playbook",
    "#### Verify before done",
    "#### Edit feedback",
    "#### Secrets and risky actions",
    "#### Audit",
    "### Where hooks run",
    "### Kill switches and escape hatches",
    "### Trust",
    "### Checking that they run",
    "### Caveats",
    "### Invariants",
    "## Code-quality metrics gate",
    "### The metrics",
    "### Clean Code for AI Agents preset",
    "### Running tests and coverage (`--run-tests`)",
    "### The `metrics` optional extra (maintainability index)",
    "## Commit-message convention (commitizen)",
    "## `playbook ci`",
    "## Running evals",
)
_WRITING_A_RULE = "## Writing a rule"


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def _readme_prose() -> str:
    """The README with its markdown line wrapping undone."""
    return " ".join(_readme().split())


def _writing_a_rule() -> str:
    """The contributor guide's "Writing a rule" section; its fenced template's ``##`` lines stay in."""
    text = (CATALOG_ROOT / "README.md").read_text(encoding="utf-8")
    heads = markdown_headings(text)
    start = next((offset for offset, _, line in heads if line == _WRITING_A_RULE), None)
    assert start is not None, f"catalog/README.md has no {_WRITING_A_RULE!r} heading"
    end = next((at for at, level, _ in heads if at > start and level <= 2), len(text))
    return text[start:end]


def test_readme_is_short() -> None:
    lines = _readme().splitlines()
    assert len(lines) <= _README_MAX_LINES, f"README.md has {len(lines)} lines (D55: about 80)"


def test_readme_holds_only_the_d55_sections() -> None:
    sections = tuple(line for _, level, line in markdown_headings(_readme()) if level == 2)
    assert sections == _README_SECTIONS


def test_readme_overview_is_a_six_line_diagram() -> None:
    blocks = re.findall(r"```text\n(.*?)```", _readme(), flags=re.DOTALL)
    assert blocks, "the README overview is a ```text block"
    lines = blocks[0].splitlines()
    assert len(lines) == _OVERVIEW_LINES, (
        f"the overview has {len(lines)} lines (D55: 6):\n{blocks[0]}"
    )


@pytest.mark.parametrize("heading", _FORMER_README_HEADINGS)
def test_every_former_readme_section_lives_in_docs(heading: str) -> None:
    lines = [line for _, _, line in markdown_headings(user_docs())]
    assert lines.count(heading) == 1, f"docs/ must hold {heading!r} exactly once"


@pytest.mark.parametrize("page", USER_DOC_PAGES)
def test_readme_links_every_docs_page(page: str) -> None:
    assert f"]({page})" in _readme(), f"README.md must link {page}"


def test_readme_install_is_the_git_url_dev_dependency() -> None:
    readme = _readme()
    assert 'uv add --dev "coding-agent-playbook @ git+' in readme
    assert "Python 3.12" in readme
    assert "internal index" in _readme_prose()
    assert "uv tool install" not in readme and "pipx" not in readme  # D66: they break the pin


@pytest.mark.parametrize(
    "token",
    [
        "playbook init --framework",  # D57
        "playbook sync",
        'platforms = ["domino"]',  # D63
        "`playbook/`",  # D70: a local layer
        "[layout]",  # D71
    ],
)
def test_readme_setup_names(token: str) -> None:
    assert token in _readme()


def test_readme_states_the_continue_license_gap() -> None:
    sentences = [s for s in _readme_prose().split(". ") if "Continue" in s and "license" in s]
    assert sentences, "README.md needs a sentence naming Continue and its license gap (D19)"
    assert "no license file" in sentences[0], sentences[0]


@pytest.mark.parametrize("doc", ["README.md", "catalog/README.md"])
def test_no_doc_says_four_skills(doc: str) -> None:
    assert "four skills" not in (REPO_ROOT / doc).read_text(encoding="utf-8")


def test_docs_say_core_rules_live_in_their_skill() -> None:
    docs = " ".join(user_docs().split())
    assert "`<skills root>/<skill>/rules/<rule-id>.md`" in docs
    assert "unrelated to Claude Code's `.claude/rules/`" in docs


@pytest.mark.parametrize("key", [field.name for field in dataclasses.fields(RuleFrontmatter)])
def test_writing_a_rule_covers_every_frontmatter_key(key: str) -> None:
    assert f"`{key}`" in _writing_a_rule(), f"'Writing a rule' must document {key!r}"


@pytest.mark.parametrize(
    "token",
    [
        "## Description",
        "## Bad Example",
        "## Good Example",
        "## Notes",
        "[IMPACT]",
        "100 lines",
        "750 words",
        "CRITICAL 20-39",
        "applies_if",
        "ruff format",
    ],
)
def test_writing_a_rule_states_the_template(token: str) -> None:
    assert token in _writing_a_rule()
