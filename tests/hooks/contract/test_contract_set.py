"""The hook trust contract across hooks, artifacts and config (specs/prK-lifecycle-hooks.md §B.5).

``classify_hook_set`` is pure over a ``HookSetInputs``: merged hooks and rules,
the parsed committed ``[hooks]`` table and what the effective view switched on.
It owns H15's config half, H16, H20 and H21 (table parsing itself is the
parser's, ``tests/config/test_tables_hooks.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME
from coding_agent_playbook.config.tables.hooks import parse_hooks_config
from coding_agent_playbook.hooks.contract.contract_set import HookSetInputs, classify_hook_set
from coding_agent_playbook.hooks.contract.findings import HookIssue, Severity
from tests.hook_samples import sample_hook

OVERLAY = "acme_rules"
CONFIG = "/repo/.coding-agent-playbook.toml"
LOCAL = "/repo/.coding-agent-playbook.local.toml"
_EXTERNAL = {"command": "python", "script": "scripts/check.py"}


def _rule(rule_id: str) -> Rule:
    frontmatter = RuleFrontmatter(id=rule_id, name="R", description="d", scope="always")
    path = Path(f"/repo/playbook/rules/{rule_id}.md")
    return Rule(frontmatter, "Body\n", "Body\n", False, path, "<repo-local>")


def _inputs(hooks_table: dict[str, Any] | None = None, **fields: Any) -> HookSetInputs:
    defaults: dict[str, Any] = {
        "hooks": (sample_hook(path="/repo/playbook/hooks/guard-x/HOOK.md"),),
        "config_where": CONFIG,
        "local_where": LOCAL,
    }
    if hooks_table is not None:
        defaults["hooks_cfg"] = parse_hooks_config(hooks_table)
        defaults["hooks_table_present"] = True
    return HookSetInputs(**{**defaults, **fields})


def _messages(inputs: HookSetInputs, *, severity: str = "error") -> list[str]:
    return [issue.message for issue in classify_hook_set(inputs) if issue.severity == severity]


def test_nothing_to_report_without_config() -> None:
    assert classify_hook_set(HookSetInputs()) == []
    assert classify_hook_set(_inputs()) == []


def test_the_where_defaults_name_the_two_config_files() -> None:
    """The defaults take the one spelling from ``config.files`` (spec B.5.4)."""
    inputs = HookSetInputs()

    assert (inputs.config_where, inputs.local_where) == (CONFIG_FILENAME, CONFIG_LOCAL_FILENAME)


def test_a_clean_hooks_table_has_no_issues() -> None:
    table = {
        "enabled": True,
        "enable": ["guard-x"],
        "allow_code_from": [OVERLAY, "<repo-local>"],
        "wrapper_prefixes": ["proxy", "proxy run"],
    }

    assert classify_hook_set(_inputs(table, overlays_enabled=(OVERLAY,))) == []


_MANDATORY = sample_hook(OVERLAY, mandatory=True, path="/o/hooks/guard-x/HOOK.md")

# (case id, [hooks] table, extra HookSetInputs fields, expected error)
_CASES: list[tuple[str, dict[str, Any], dict[str, Any], str]] = [
    (
        "H15-disable-mandatory",
        {"enabled": True, "disable": ["guard-x"]},
        {"hooks": (_MANDATORY,)},
        f"[hooks] disable: 'guard-x' is mandatory (overlay {OVERLAY}) and cannot be disabled",
    ),
    (
        "H15-off-around-mandatory",
        {"enabled": False},
        {"hooks": (_MANDATORY,), "overlays_enabled": (OVERLAY,)},
        f"[hooks] enabled = false while overlay {OVERLAY!r} ships mandatory hook 'guard-x'; "
        "mandatory hooks cannot be switched off: set enabled = true",
    ),
    (
        "H21-unknown-enable",
        {"enabled": True, "enable": ["guard-y"]},
        {},
        "[hooks] enable: unknown hook id 'guard-y'; did you mean 'guard-x'?",
    ),
    (
        "H21-unknown-disable",
        {"enabled": True, "disable": ["post-edit-ruff"]},
        {},
        "[hooks] disable: unknown hook id 'post-edit-ruff'",
    ),
    (
        "H21-enable-and-disable",
        {"enabled": True, "enable": ["guard-x"], "disable": ["guard-x"]},
        {},
        "[hooks] enable and disable both name 'guard-x'; disable wins, so list it in one of "
        "them only",
    ),
    (
        "H21-allow-code-from",
        {"enabled": True, "allow_code_from": ["other_rules"]},
        {"overlays_enabled": (OVERLAY,)},
        "[hooks] allow_code_from: 'other_rules' is neither an enabled overlay nor "
        "'<repo-local>'; allowed: acme_rules, <repo-local>",
    ),
    (
        "H21-unknown-sub-table",
        {"enabled": True, "guard-z": {"mode": "warn"}},
        {},
        "[hooks.guard-z]: unknown hook id 'guard-z'; did you mean 'guard-x'?",
    ),
    (
        "H21-wrapper-hides-git",
        {"enabled": True, "wrapper_prefixes": ["proxy", "git"]},
        {},
        "[hooks] wrapper_prefixes: 'git' would hide 'git' from every shell guard; declare "
        "only a launcher that is not itself a guarded command (e.g. 'proxy')",
    ),
    (
        "H21-wrapper-hides-a-later-token",
        {"enabled": True, "wrapper_prefixes": ["proxy rm"]},
        {},
        "[hooks] wrapper_prefixes: 'proxy rm' would hide 'rm' from every shell guard; declare "
        "only a launcher that is not itself a guarded command (e.g. 'proxy')",
    ),
    (
        "H21-stop-gate-stages",
        {"enabled": True, "stop-ci-parity-gate": {"stages": ["typecheck", "coverage"]}},
        {},
        "[hooks.stop-ci-parity-gate] stages: must be a list drawn from 'typecheck', 'tests', "
        "got ['typecheck', 'coverage']",
    ),
]


@pytest.mark.parametrize(
    ("table", "fields", "expected"),
    [case[1:] for case in _CASES],
    ids=[case[0] for case in _CASES],
)
def test_set_level_config_rule(
    table: dict[str, Any], fields: dict[str, Any], expected: str
) -> None:
    issues = classify_hook_set(_inputs(table, **fields))

    assert HookIssue("error", CONFIG, expected) in issues


def test_an_absent_hooks_table_is_not_an_opt_out_of_mandatory_hooks() -> None:
    # Absent [hooks] is the no-upgrade-drift default (§B.1): not an H15 error.
    inputs = _inputs(None, hooks=(_MANDATORY,), overlays_enabled=(OVERLAY,))

    assert classify_hook_set(inputs) == []


def test_h16_external_handler_of_an_on_hook_needs_allow_code_from() -> None:
    hook = sample_hook(OVERLAY, handler=_EXTERNAL, path="/o/hooks/guard-x/HOOK.md")
    inputs = _inputs({"enabled": True}, hooks=(hook,), on_hook_ids=frozenset({"guard-x"}))

    assert classify_hook_set(inputs) == [
        HookIssue(
            "error",
            "/o/hooks/guard-x/HOOK.md",
            f"hook 'guard-x' runs code from {OVERLAY!r}; add it to [hooks] allow_code_from",
        )
    ]


def test_h16_spares_allowed_sources_and_hooks_that_are_off() -> None:
    hook = sample_hook(OVERLAY, handler=_EXTERNAL)
    allowed = _inputs(
        {"enabled": True, "allow_code_from": [OVERLAY]},
        hooks=(hook,),
        overlays_enabled=(OVERLAY,),
        on_hook_ids=frozenset({"guard-x"}),
    )
    off = _inputs({"enabled": True}, hooks=(hook,))

    assert classify_hook_set(allowed) == []
    assert classify_hook_set(off) == []


def test_h20_reserved_advisory_prefix_on_a_rule() -> None:
    inputs = _inputs(rules=(_rule("guardrail-x"),))

    assert classify_hook_set(inputs) == [
        HookIssue(
            "error",
            "/repo/playbook/rules/guardrail-x.md",
            "rule id 'guardrail-x' uses the reserved 'guardrail-' prefix",
        )
    ]


@pytest.mark.parametrize("kind", ["rule", "prompt"])
def test_h20_hook_id_equal_to_a_rule_or_prompt_id(kind: str) -> None:
    clash = (
        {"rules": (_rule("guard-x"),)} if kind == "rule" else {"prompt_ids": frozenset({"guard-x"})}
    )

    assert _messages(_inputs(**clash)) == [
        f"hook id 'guard-x' is also a {kind} id; playbook render looks ids up across kinds, "
        "so rename one"
    ]


@pytest.mark.parametrize(("is_error", "severity"), [(True, "error"), (False, "warning")])
def test_local_toml_policy_keys_are_an_error_for_validate_and_a_warning_for_sync(
    is_error: bool, severity: Severity
) -> None:
    inputs = _inputs(
        local_keys=("hooks.enabled", "guardrails.git.protected_branches"),
        local_policy_is_error=is_error,
    )

    assert classify_hook_set(inputs) == [
        HookIssue(
            severity,
            LOCAL,
            "hooks.enabled, guardrails.git.protected_branches: [hooks] and [guardrails] are "
            "read from the committed config only, so these local values are ignored; move "
            "them to the committed config or delete them",
        )
    ]
