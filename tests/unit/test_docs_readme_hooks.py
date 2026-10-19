"""Docs-consistency guard: the README documents the lifecycle-hooks release (prK §H Track K11).

The README is a consumer's first stop, so it must name what PR K shipped: the
pre-commit ids, every lifecycle hook with its tier and where it is enforced,
the CLI subcommands, the dispatcher in the architecture overview, the caveats
SPEC §10.3.2 and §10.6 record, the metrics and a ``playbook ci`` job that never
interpolates the PR title into a ``run:`` line. Every test takes its expected
names from the landed code (``.pre-commit-hooks.yaml``, the shipped ``HOOK.md``
frontmatter, ``cli.parser._SUBCOMMANDS``, ``CI_STEPS``, the escape-hatch variables,
the metric families, the OpenCode floor), so a hook, command, step or metric
that lands undocumented fails here. Prose-only: the tests read markdown and
parse frontmatter and config snippets; they never run engine behaviour.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.cli.parser import _SUBCOMMANDS
from coding_agent_playbook.commands.twins._ci_commit_convention import PR_TITLE_ENV
from coding_agent_playbook.commands.twins.ci import CI_STEPS
from coding_agent_playbook.config.tables.hooks import parse_guardrails_config, parse_hooks_config
from coding_agent_playbook.grading.metric import all_metrics
from coding_agent_playbook.guard_config import GUARD_CONFIG_PATH
from coding_agent_playbook.hook_registrations import LAUNCHER_PATH, OPENCODE_SHIM_PATH
from coding_agent_playbook.hook_runtime._doctor_opencode import OPENCODE_MIN_VERSION
from coding_agent_playbook.hook_runtime.escape import HATCH_VARS
from coding_agent_playbook.hook_runtime.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hooks.enforcement import ADAPTER_LABELS, enforcement_targets
from coding_agent_playbook.metrics_gate.config import parse_metrics_config
from coding_agent_playbook.metrics_gate.policy import (
    METRIC_FAMILIES,
    OPT_IN_METRICS,
    resolve_metric_selection,
)
from tests._catalog import CORE_ROOT
from tests.unit.test_docs_lifecycle_hooks_cli import _metric_names, _precommit_ids
from tests.unit.test_docs_lifecycle_hooks_spec import _HOOK_INVARIANTS

_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_ROOT = CORE_ROOT / "hooks"
_LIFECYCLE = "## Assistant lifecycle hooks"
_FENCE = re.compile(r"^\s*```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,6}) ")
_PR_TITLE_EXPR = "${{ github.event.pull_request.title }}"


def _readme() -> str:
    return (_ROOT / "README.md").read_text(encoding="utf-8")


def _headings(text: str) -> list[tuple[int, int, str]]:
    """``(offset, level, line)`` of every heading outside fenced code (``# x`` in a block is not one)."""
    found: list[tuple[int, int, str]] = []
    fenced, offset = False, 0
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and (match := _HEADING.match(line)):
            found.append((offset, len(match.group(1)), line.rstrip("\n")))
        offset += len(line)
    return found


def _section(heading: str) -> str:
    """The README section under the heading line ``heading``, up to the next one of its level or above."""
    text = _readme()
    heads = _headings(text)
    starts = [(offset, level) for offset, level, line in heads if line == heading]
    assert starts, f"README has no {heading!r} heading"
    start, level = starts[0]
    end = next((at for at, lvl, _ in heads if at > start and lvl <= level), len(text))
    return text[start:end]


def _blocks(text: str, language: str) -> list[str]:
    """The bodies of every ```<language> fenced block in ``text``, dedented to their fence."""
    blocks: list[str] = []
    current: list[str] | None = None
    indent = 0
    for line in text.splitlines():
        match = _FENCE.match(line)
        if match and current is None and match.group(1) == language:
            current, indent = [], len(line) - len(line.lstrip())
        elif match and current is not None:
            blocks.append("\n".join(current) + "\n")
            current = None
        elif current is not None:
            current.append(line[indent:])
    return blocks


def _shipped_hooks() -> list[HookFrontmatter]:
    """Every hook the engine ships, parsed through the K1 frontmatter schema."""
    hooks = []
    for path in sorted(_HOOKS_ROOT.glob("**/HOOK.md*")):
        data, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        hooks.append(HookFrontmatter.from_mapping(data, where=str(path)))
    return hooks


def _enforced_on(hook: HookFrontmatter) -> str:
    """The pack table's "Enforced on" cell: where the hook blocks, then where it only checks.

    It is the same static claim as the advisory's enforcement line (``enforcement_targets``).
    """
    enforcing, checking = enforcement_targets(hook.events, hook.supports)
    parts = [", ".join(ADAPTER_LABELS[name] for name in enforcing)] if enforcing else []
    if checking:
        parts.append("checked on " + ", ".join(ADAPTER_LABELS[name] for name in checking))
    return "; ".join(parts) or "advisory only"


def test_readme_separates_precommit_and_lifecycle_hooks() -> None:
    lines = [line for _, _, line in _headings(_readme())]
    assert "### Pre-commit hooks" in lines
    assert _LIFECYCLE in lines
    assert "### Hooks" not in lines


@pytest.mark.parametrize("hook_id", _precommit_ids())
def test_readme_precommit_table_lists_every_shipped_precommit_hook(hook_id: str) -> None:
    assert f"| `{hook_id}` |" in _section("### Pre-commit hooks")


@pytest.mark.catalog
@pytest.mark.parametrize("hook", _shipped_hooks(), ids=lambda hook: hook.id)
def test_readme_lists_every_shipped_lifecycle_hook_with_its_tier(hook: HookFrontmatter) -> None:
    row = f"| `{hook.id}` | `{hook.tier}` | {_enforced_on(hook)} |"
    assert row in _section(_LIFECYCLE), f"README pack table lacks the row {row!r}"


def test_readme_architecture_overview_names_the_dispatcher() -> None:
    overview = _section("## Architecture")
    assert _blocks(overview, "text"), "the overview is an ASCII diagram in a ```text block"
    guard_config = GUARD_CONFIG_PATH.rsplit("/", 1)[-1]
    for token in ("playbook-hook", guard_config, LAUNCHER_PATH, OPENCODE_SHIM_PATH):
        assert token in overview, f"README architecture overview lacks {token!r}"
    assert "resolve_effective_hooks" in overview


@pytest.mark.parametrize("name", _SUBCOMMANDS)
def test_readme_status_lists_every_cli_subcommand(name: str) -> None:
    status = _section("## Status")
    assert f"`{name}`" in status
    assert "`playbook-hook`" in status


def test_readme_states_launch_directory_caveat() -> None:
    hooks = _section(_LIFECYCLE)
    assert "subdirectory" in hooks
    assert "Start Claude Code at the repository root" in hooks


def test_readme_warns_against_gemini_hooks_migrate() -> None:
    assert "never run `gemini hooks migrate`" in _section(_LIFECYCLE)


def test_readme_states_opencode_floor() -> None:
    hooks = _section(_LIFECYCLE)
    floor = ".".join(str(part) for part in OPENCODE_MIN_VERSION)
    assert f"OpenCode ≥ {floor}" in hooks
    assert "`setup()`" in hooks  # the inert V2 stub (OQ-11)


def test_readme_states_windows_and_copilot_reach() -> None:
    hooks = _section(_LIFECYCLE)
    assert "Git Bash" in hooks and "fail-open" in hooks  # OQ-14
    assert "Copilot CLI" in hooks  # OQ-15


def test_readme_states_one_interactive_sync_per_machine() -> None:
    hooks = _section(_LIFECYCLE)
    assert "allow_code_from" in hooks
    assert "one interactive `playbook sync` per machine" in hooks  # OQ-7


@pytest.mark.parametrize("variable", [*HATCH_VARS, UNATTENDED_ENV_VAR])
def test_readme_documents_every_escape_hatch(variable: str) -> None:
    assert f"`{variable}" in _section(_LIFECYCLE)


@pytest.mark.parametrize("phrase", _HOOK_INVARIANTS)
def test_readme_lists_the_hook_invariants(phrase: str) -> None:
    assert phrase in _section("### Invariants")  # CLAUDE.md is local-only (OQ-5)


def _metric_row(metric: str) -> list[str]:
    """The cells of the metrics table row for ``metric``."""
    rows = [
        line
        for line in _section("## Code-quality metrics gate").splitlines()
        if line.startswith(f"| `{metric}` |")
    ]
    assert len(rows) == 1, f"README metrics table needs exactly one row for {metric!r}"
    return [cell.strip() for cell in rows[0].strip("|").split("|")]


@pytest.mark.parametrize("metric", _metric_names())
def test_readme_metrics_table_lists_every_metric(metric: str) -> None:
    _, families, selection, *_ = _metric_row(metric)
    expected = [family for family, members in METRIC_FAMILIES.items() if metric in members]
    assert [family for family in METRIC_FAMILIES if f"`{family}`" in families] == expected
    assert ("opt-in" in selection) == (metric in OPT_IN_METRICS)


def test_readme_metrics_section_documents_no_run_tests_and_diff_coverage() -> None:
    metrics = _section("## Code-quality metrics gate")
    assert "--no-run-tests" in metrics
    assert "diff_coverage" in metrics
    assert "### Clean Code for AI Agents preset" in metrics


def _parse_policy(document: dict[str, Any]) -> set[str]:
    """Run every policy table of one snippet through its engine parser; return the tables seen."""
    if "hooks" in document:
        parse_hooks_config(document["hooks"])
    if "guardrails" in document:
        parse_guardrails_config(document["guardrails"])
    if "metrics" in document:
        cfg = parse_metrics_config(document["metrics"])
        resolve_metric_selection(
            all_metrics(),
            select=cfg.select,
            extend_select=cfg.extend_select,
            ignore=cfg.ignore,
            run_tests=cfg.run_tests,
        )
    return {"hooks", "guardrails", "metrics"} & set(document)


def test_readme_policy_snippets_parse_with_the_engine_parsers() -> None:
    seen: set[str] = set()
    for block in _blocks(_readme(), "toml"):
        seen |= _parse_policy(tomllib.loads(block))
    assert seen == {"hooks", "guardrails", "metrics"}


def test_readme_commitizen_section_documents_the_cutover() -> None:
    section = _section("## Commit-message convention (commitizen)")
    assert "[tool.commitizen]" in section
    tables = [tomllib.loads(block) for block in _blocks(section, "toml")]
    cutovers = [t["hooks"]["commit_convention"]["cutover_date"] for t in tables if "hooks" in t]
    assert cutovers and all(isinstance(value, str) for value in cutovers)


@pytest.mark.parametrize("step", [step.name for step in CI_STEPS])
def test_readme_ci_section_lists_every_ci_step(step: str) -> None:
    assert f"| `{step}` |" in _section("## `playbook ci`")


def test_readme_ci_snippet_passes_pr_title_only_through_env() -> None:
    (snippet,) = _blocks(_section("## `playbook ci`"), "yaml")
    run_lines = [line for line in snippet.splitlines() if line.strip().startswith("run:")]
    assert run_lines and not [line for line in run_lines if "github.event" in line]
    steps = yaml.safe_load(snippet)["jobs"]["playbook-ci"]["steps"]
    ci_step = next(step for step in steps if str(step.get("run", "")).startswith("playbook ci"))
    assert ci_step["env"] == {PR_TITLE_ENV: _PR_TITLE_EXPR}
    checkout = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0
