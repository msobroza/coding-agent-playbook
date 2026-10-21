"""The shipped rules' ``lint_codes`` and their sync-time resolution (specs/prK-hook-pack.md §E.3).

``RuleFrontmatter.lint_codes`` is the single source of the codes the three
rule-linked lint hooks report (specs/prK-lifecycle-hooks.md §A.7): these tests
pin the shipped codes, the ``when`` resolution against the facts the rule body
reads, the warn-only shape, and that declaring codes never changes a rendered
rule (only the agent_harness sidecar records them).
"""

from __future__ import annotations

import copy
import dataclasses
from typing import TYPE_CHECKING, Any, Final, cast

import pytest

from coding_agent_playbook.adapters.agents_md import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_ import ContinueAdapter
from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.hooks.resolution.lint_codes import resolve_lint_codes
from coding_agent_playbook.validation._frontmatter import lint_codes_problems
from tests._catalog import core_rules

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

SIDECAR: Final = ".playbook/manifest.toml"
#: §E.3's codes per linked rule, verbatim.
SPEC_CODES: Final[Mapping[str, dict[str, Any]]] = {
    "python-error-handling": {
        "warn": ["E722", "BLE001", "S110", "S112", "B904", "TRY400", "TRY401", "S101"]
    },
    "python-typing": {
        "warn": ["ANN001", "ANN201", "ANN401", "B006", "PGH003", "UP007", "UP045"],
        "when": [{"applies_if": {"python_version": ">=3.12"}, "warn": ["UP040", "UP046", "UP047"]}],
    },
    "pytest": {"warn": ["PT006", "PT007", "PT009", "PT011", "PT018", "PT027"]},
    # specs/prK-hook-pack.md §F.3.1: docstring-nonregression's post-edit bucket.
    "python-docstrings": {"warn": ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]},
}


def _engine_rules() -> dict[str, Rule]:
    """Every core rule by id, wherever it lives (``rules/`` or a skill's ``rules/``)."""
    return core_rules()


def _evaluate(predicate: dict[str, Any], facts: Mapping[str, Any]) -> bool:
    return evaluate_predicate(predicate, cast("Facts", facts))


def test_shipped_rules_declare_spec_codes() -> None:
    """Exactly the four linked rules carry codes, each a valid warn-only ``lint_codes``."""
    rules = _engine_rules()

    declared = {
        rule_id: r.frontmatter.lint_codes
        for rule_id, r in rules.items()
        if r.frontmatter.lint_codes
    }

    assert declared == SPEC_CODES
    assert all(
        lint_codes_problems(codes, lambda p: _evaluate(p, {})) == [] for codes in declared.values()
    )


@pytest.mark.parametrize(
    ("python_version", "pep695"),
    [("3.11", False), ("3.12", True), ("3.13", True)],
)
def test_when_block_applies_only_for_py312(python_version: str, pep695: bool) -> None:
    """The PEP 695 codes follow the same ``python_version`` fact as the rule body's branch."""
    codes = _engine_rules()["python-typing"].frontmatter.lint_codes

    resolved = resolve_lint_codes(codes, {"python_version": python_version}, _evaluate)

    assert resolved[:7] == SPEC_CODES["python-typing"]["warn"]
    assert ("UP046" in resolved) is pep695
    assert resolved[7:] == (["UP040", "UP046", "UP047"] if pep695 else [])


def test_python_docstrings_round_trips_lint_codes(tmp_path: Path) -> None:
    """SPEC §6.6.3: the plain-markdown rule writes back to the same frontmatter, codes included."""
    rule = _engine_rules()["python-docstrings"]
    copy_path = tmp_path / "docstrings.md"
    copy_path.write_text(rule.to_markdown(), encoding="utf-8")

    again = Rule.from_markdown(copy_path, "coding_agent_playbook")

    assert again.frontmatter == rule.frontmatter
    assert again.frontmatter.lint_codes == SPEC_CODES["python-docstrings"]
    assert (rule.frontmatter.scope, rule.frontmatter.globs) == ("scoped", ["**/*.py"])


def test_no_block_key_allowed() -> None:
    """Lint feedback is warn-only (§A.7): a ``block`` key is a validate error, never honoured."""
    problems = lint_codes_problems({"warn": ["E722"], "block": ["S101"]}, lambda p: True)

    assert len(problems) == 1 and "unknown key(s) ['block']" in problems[0]
    assert resolve_lint_codes({"block": ["S101"]}, {}, _evaluate) == []


_ADAPTERS: Final[Mapping[str, Callable[[], Adapter]]] = {
    "claude_code": ClaudeCodeAdapter,
    "agents_md": AgentsMdAdapter,
    "continue": ContinueAdapter,
    "agent_harness": AgentHarnessAdapter,
}


def _render(name: str, rule: Rule, root: Path) -> dict[str, bytes]:
    root.mkdir(parents=True)
    adapter = _ADAPTERS[name]()
    adapter.write_rule(rule, root)
    adapter.finalize(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("adapter", sorted(_ADAPTERS))
@pytest.mark.parametrize("rule_id", sorted(SPEC_CODES))
def test_rules_without_lint_codes_render_byte_identically(
    tmp_path: Path, adapter: str, rule_id: str
) -> None:
    """Codes never reach the Claude Code rules file, AGENTS.md or Continue.

    Only the sidecar records them.
    """
    linked = _engine_rules()[rule_id]
    plain = dataclasses.replace(
        linked, frontmatter=dataclasses.replace(linked.frontmatter, lint_codes={})
    )

    # Same directory name: HARNESS.md names the repository.
    with_codes = _render(adapter, copy.deepcopy(linked), tmp_path / "with" / "repo")
    without = _render(adapter, plain, tmp_path / "without" / "repo")

    sidecar = without.pop(SIDECAR, None), with_codes.pop(SIDECAR, None)
    assert with_codes == without
    if adapter == "agent_harness":
        assert sidecar[0] is not None and b"lint_codes" not in sidecar[0]
        assert sidecar[1] is not None and b"lint_codes = {" in sidecar[1]
