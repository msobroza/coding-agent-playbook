"""The ``[hooks]`` / ``[guardrails]`` tables (specs/prK-lifecycle-hooks.md §B.1, §B.3).

``parse_hooks_config`` and ``parse_guardrails_config`` are pure: a decoded TOML
table in, a frozen dataclass out, or one ``ValueError`` naming every offending
value and its expected shape. ``policy_tables`` applies the ``.local.toml``
exclusion: the policy tables come from the committed file only, and the local
keys are recorded for the sync warning and validate's H21.
"""

from __future__ import annotations

import datetime
import sys
from typing import Any

import pytest

from coding_agent_playbook.config import (
    Config,
    GuardrailsConfig,
    HooksConfig,
    check_enabled_keys,
    parse_guardrails_config,
    parse_hooks_config,
)
from coding_agent_playbook.hooks_config import (
    CommitConventionConfig,
    GitGuardrails,
    NetworkGuardrails,
    PolicyTables,
    SecretsGuardrails,
    policy_tables,
)
from tests.import_probe import new_modules_after

# --- [hooks] -------------------------------------------------------------------


@pytest.mark.parametrize("table", [None, {}, {"tiers": ["default", "opt-in"]}])
def test_absent_table_and_table_without_enabled_both_mean_off(table: Any) -> None:
    assert parse_hooks_config(table).enabled is False


def test_absent_table_is_the_default_config() -> None:
    assert parse_hooks_config(None) == HooksConfig()


def test_full_hooks_table_parses() -> None:
    table = {
        "enabled": True,
        "adapters": ["claude_code"],
        "tiers": ["default", "opt-in"],
        "enable": ["precompact-checkpoint"],
        "disable": ["post-edit-ruff-format"],
        "advisory": False,
        "unattended_ask": "warn",
        "allow_code_from": ["playbook_rules_bnp", "<repo-local>"],
        "auto_sync": True,
        "wrapper_prefixes": ["proxy"],
        "state_ttl_days": 3,
        "render_remediation_allow": True,
    }

    assert parse_hooks_config(table) == HooksConfig(
        enabled=True,
        adapters=("claude_code",),
        tiers=("default", "opt-in"),
        enable=("precompact-checkpoint",),
        disable=("post-edit-ruff-format",),
        advisory=False,
        unattended_ask="warn",
        allow_code_from=("playbook_rules_bnp", "<repo-local>"),
        auto_sync=True,
        wrapper_prefixes=("proxy",),
        state_ttl_days=3,
        render_remediation_allow=True,
    )


def test_hooks_defaults_match_the_b1_table() -> None:
    parsed = parse_hooks_config({"enabled": True})

    assert parsed.adapters is None  # adapters_enabled ∩ {claude_code, opencode}, resolved later
    assert parsed.tiers == ("default",)
    assert parsed.advisory is True
    assert parsed.unattended_ask == "deny"
    assert parsed.state_ttl_days == 7
    assert (parsed.auto_sync, parsed.render_remediation_allow) == (False, False)
    assert parsed.per_hook == {}
    assert parsed.commit_convention == CommitConventionConfig()


def test_unknown_hooks_key_names_key_and_allowed_set() -> None:
    with pytest.raises(ValueError, match="unknown key 'deadlines_ms'") as caught:
        parse_hooks_config({"enabled": True, "deadlines_ms": 5000})

    message = str(caught.value)
    assert message.startswith("[hooks] ")
    assert "allowed: adapters, advisory, allow_code_from, auto_sync" in message
    assert "a [hooks.<hook-id>] table" in message


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("enabled", "yes", "[hooks] enabled: must be true or false, got 'yes'"),
        ("advisory", 1, "[hooks] advisory: must be true or false, got 1"),
        (
            "adapters",
            "claude_code",
            "[hooks] adapters: must be a list of strings, got 'claude_code'",
        ),
        ("enable", ["guard-x", 1], "[hooks] enable: must be a list of strings, got ['guard-x', 1]"),
        ("state_ttl_days", 0, "[hooks] state_ttl_days: must be a positive integer, got 0"),
        ("state_ttl_days", True, "[hooks] state_ttl_days: must be a positive integer, got True"),
        ("tiers", {"default": True}, "[hooks] tiers: must be a list drawn from"),
    ],
)
def test_wrong_types_name_value_and_shape(key: str, value: Any, expected: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_hooks_config({key: value})

    assert str(caught.value).startswith(expected)


def test_every_problem_is_reported_in_one_error() -> None:
    with pytest.raises(ValueError) as caught:
        parse_hooks_config({"enabled": "true", "unattended_ask": "ask", "bogus": 1})

    lines = str(caught.value).splitlines()
    assert len(lines) == 3
    assert all(line.startswith("[hooks] ") for line in lines)


def test_non_table_hooks_value_is_refused() -> None:
    with pytest.raises(ValueError, match=r"^\[hooks\] must be a table, got 'on'$"):
        parse_hooks_config("on")


@pytest.mark.parametrize("value", ["deny", "warn"])
def test_unattended_ask_accepts_deny_or_warn(value: str) -> None:
    assert parse_hooks_config({"unattended_ask": value}).unattended_ask == value


@pytest.mark.parametrize("value", ["ask", "allow", ["deny"]])
def test_unattended_ask_refuses_anything_else(value: Any) -> None:
    with pytest.raises(ValueError, match=r"unattended_ask: must be one of 'deny', 'warn', got"):
        parse_hooks_config({"unattended_ask": value})


def test_tiers_accept_default_and_opt_in() -> None:
    assert parse_hooks_config({"tiers": ["opt-in"]}).tiers == ("opt-in",)


def test_tiers_refuse_the_overlay_tier_with_the_activation_path() -> None:
    with pytest.raises(ValueError) as caught:
        parse_hooks_config({"tiers": ["default", "overlay"]})

    message = str(caught.value)
    assert "got ['default', 'overlay']" in message
    assert "an overlay promoting it to tier: default" in message


def test_per_hook_subtables_collected_as_consumer_layer() -> None:
    table: dict[str, Any] = {
        "enabled": True,
        "stop-ci-parity-gate": {"stages": ["typecheck"], "max_blocks": 3},
        "command-convention-guard": {"rules": [{"pattern": "^pip ", "decision": "deny"}]},
    }

    parsed = parse_hooks_config(table)
    table["stop-ci-parity-gate"]["stages"].append("tests")

    assert parsed.per_hook == {
        "stop-ci-parity-gate": {"stages": ["typecheck"], "max_blocks": 3},
        "command-convention-guard": {"rules": [{"pattern": "^pip ", "decision": "deny"}]},
    }


def test_commit_convention_is_reserved_subtable() -> None:
    parsed = parse_hooks_config({"commit_convention": {"cutover_date": "2026-10-15"}})

    assert parsed.commit_convention == CommitConventionConfig(cutover_date="2026-10-15")
    assert parsed.per_hook == {}


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        (datetime.date(2026, 10, 15), "not a TOML date literal"),
        ("2026-13-01", "got '2026-13-01'"),
        ("15/10/2026", "got '15/10/2026'"),
        (20261015, "got 20261015"),
    ],
)
def test_cutover_date_must_be_a_yyyy_mm_dd_string(value: Any, fragment: str) -> None:
    with pytest.raises(ValueError, match=r"^\[hooks\.commit_convention\] cutover_date: ") as caught:
        parse_hooks_config({"commit_convention": {"cutover_date": value}})

    assert fragment in str(caught.value)


def test_commit_convention_unknown_key_is_refused() -> None:
    with pytest.raises(ValueError, match=r"\[hooks\.commit_convention\] unknown key 'convention'"):
        parse_hooks_config({"commit_convention": {"convention": "cz_conventional_commits"}})


def test_commit_convention_must_be_a_table() -> None:
    with pytest.raises(ValueError, match=r"\[hooks\] commit_convention: must be a table"):
        parse_hooks_config({"commit_convention": "2026-10-15"})


def test_hooks_adapters_key_is_not_mistaken_for_legacy_adapters_table() -> None:
    """``[hooks] adapters = [...]`` is a list, while the legacy ``[adapters]``
    shape check_enabled_keys refuses nested is a table holding ``enabled``."""
    data = {
        "schema_version": 1,
        "project": {"name": "x", "kind": "python-library"},
        "engine": {"version": "0.1"},
        "adapters_enabled": ["claude_code"],
        "hooks": {"enabled": True, "adapters": ["claude_code"], "enable": ["guard-x"]},
    }

    check_enabled_keys(data, source="cfg.toml")
    config = Config.from_dict(data)

    assert parse_hooks_config(config.extra_tables["hooks"]).adapters == ("claude_code",)


# --- [guardrails] --------------------------------------------------------------


def test_guardrails_domains_parse_with_defaults() -> None:
    absent = parse_guardrails_config(None)

    assert absent == GuardrailsConfig()
    assert absent.git.protected_branches == ("main", "master", "release/*")
    assert absent.network == NetworkGuardrails(mode="off", allowed_hosts=())
    assert absent.stop_sweep.mode == "block"
    assert (absent.dependencies.mode, absent.audit.retain_days) == (None, None)


def test_guardrails_explicit_values_replace_the_defaults() -> None:
    parsed = parse_guardrails_config(
        {
            "secrets": {"extra_globs": ["*.vault"], "allow_paths": ["tests/fixtures/**"]},
            "git": {"protected_branches": ["develop"]},
            "network": {"mode": "enforce", "allowed_hosts": ["artifactory.corp"]},
            "dependencies": {"mode": "allowlist", "allowlist": ["requests"]},
            "audit": {"retain_days": 30},
            "stop_sweep": {"mode": "warn"},
        }
    )

    assert parsed.secrets == SecretsGuardrails(("*.vault",), ("tests/fixtures/**",))
    assert parsed.git == GitGuardrails(("develop",))
    assert parsed.network == NetworkGuardrails("enforce", ("artifactory.corp",))
    assert (parsed.dependencies.mode, parsed.dependencies.allowlist) == ("allowlist", ("requests",))
    assert (parsed.audit.retain_days, parsed.stop_sweep.mode) == (30, "warn")


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        (
            {"network": {"mode": "strict"}},
            "[guardrails.network] mode: must be one of 'off', 'ask', 'enforce', got 'strict'",
        ),
        (
            {"stop_sweep": {"mode": "deny"}},
            "[guardrails.stop_sweep] mode: must be one of 'block', 'warn', 'off', got 'deny'",
        ),
        (
            {"audit": {"retain_days": "30"}},
            "[guardrails.audit] retain_days: must be a positive integer, got '30'",
        ),
        (
            {"dependencies": {"mode": ""}},
            "[guardrails.dependencies] mode: must be a non-empty string, got ''",
        ),
    ],
)
def test_guardrails_mode_values_are_checked(table: dict[str, Any], expected: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_guardrails_config(table)

    assert str(caught.value) == expected


def test_guardrails_unknown_domain_and_key_are_refused() -> None:
    with pytest.raises(ValueError) as caught:
        parse_guardrails_config({"metrics": {}, "git": {"branches": ["main"]}})

    assert str(caught.value).splitlines() == [
        "[guardrails] unknown domain 'metrics'; allowed: audit, dependencies, git, network, "
        "secrets, stop_sweep",
        "[guardrails.git] unknown key 'branches'; allowed: protected_branches",
    ]


def test_guardrails_domain_must_be_a_table() -> None:
    with pytest.raises(ValueError, match=r"^\[guardrails\] git: must be a table, got 'main'$"):
        parse_guardrails_config({"git": "main"})


def test_guardrails_domain_values_hold_only_explicit_keys() -> None:
    """Only what the consumer wrote merges into a handler's config (§B.3): a
    default never overrides a value an engine or overlay layer set."""
    parsed = parse_guardrails_config({"git": {}, "network": {"allowed_hosts": ["a.corp"]}})

    assert parsed.domain_values("network") == {"allowed_hosts": ["a.corp"]}
    assert parsed.domain_values("git") == {}
    assert parsed.domain_values("secrets") == {}
    assert parsed.domain_values("no-such-domain") == {}


# --- the .local.toml exclusion ---------------------------------------------------


def test_policy_tables_come_from_the_committed_tables_only() -> None:
    committed = {"hooks": {"enabled": True}, "guardrails": {"git": {}}, "links": {}}
    local = {"hooks": {"enabled": False}, "user_choices": {"style": "google"}}

    tables = policy_tables(committed, local)

    assert tables.hooks == {"enabled": True}
    assert tables.guardrails == {"git": {}}
    assert tables.hooks_config().enabled is True


def test_policy_tables_record_every_local_policy_key() -> None:
    local = {
        "hooks": {"enabled": False, "stop-ci-parity-gate": {"stages": []}},
        "guardrails": {"network": {"mode": "off"}, "secrets": {}},
        "user_choices": {"style": "google"},
    }

    tables = policy_tables({}, local)

    assert tables.local_keys == (
        "hooks.enabled",
        "hooks.stop-ci-parity-gate.stages",
        "guardrails.network.mode",
        "guardrails.secrets",
    )
    assert (tables.hooks, tables.guardrails) == (None, None)


def test_policy_tables_deep_copy_the_committed_tables() -> None:
    committed: dict[str, Any] = {"hooks": {"enable": ["guard-x"]}}

    tables = policy_tables(committed, {})
    committed["hooks"]["enable"].append("guard-y")

    assert tables.hooks == {"enable": ["guard-x"]}


def test_empty_policy_tables_mean_hooks_off_and_default_guardrails() -> None:
    tables = PolicyTables()

    assert tables.hooks_config() == HooksConfig()
    assert tables.guardrails_config() == GuardrailsConfig()
    assert tables.local_keys == ()


def test_policy_tables_parse_lazily() -> None:
    """A malformed table is kept raw, so validate can report it (H21) instead
    of every command dying while it builds the context."""
    tables = policy_tables({"hooks": {"enabled": "yes"}}, {})

    with pytest.raises(ValueError, match="enabled: must be true or false"):
        tables.hooks_config()


def test_hooks_config_imports_only_the_stdlib() -> None:
    """``sources.base`` imports it at module top and promises a light import."""
    loaded = new_modules_after("import coding_agent_playbook.hooks_config")

    ours = [name for name in loaded if name.startswith("coding_agent_playbook")]
    foreign = [
        name
        for name in loaded
        if name not in ours and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert ours == ["coding_agent_playbook._table_shapes", "coding_agent_playbook.hooks_config"]
    assert foreign == []
