"""The pack tables of the compiled ``guard_config.json`` (specs/prK-hook-pack.md §E.0.5).

The top-level keys the runtime reads through ``GuardConfig.tables`` (K5's protect,
control-plane, detector and eval tables, the verify pack's ``prompts`` and
prompt-write-scope-guard's ``scopes``, the K8 secret tables and the allowlists),
compiled through ``compile_guard_config`` and, where it matters, parsed back by
``hook_runtime.config.guard_config``. K6's ``stop_gate`` is in
``test_tables_stop_gate``; the protected rows sync assembles are tested beside their
builder (``tests/sync/test_protect.py``).
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.config.tables.hooks import (
    GuardrailsConfig,
    HooksConfig,
    SecretsGuardrails,
)
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.config.schema import CONTROL_PLANE
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hooks.guard_config.compile import (
    HOOK_ARTIFACTS,
    compile_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.hooks.guard_config.inputs import (
    DetectInputs,
    ProtectInputs,
    applicability_rows,
)
from coding_agent_playbook.hooks.guard_config.resource_roots import resource_root_ids
from coding_agent_playbook.hooks.resolution.effective import resolve_effective_hooks
from coding_agent_playbook.security.patterns import (
    SECRET_CONTENT_RULES,
    SECRET_GLOB_EXEMPT,
    SECRET_PATH_EXEMPT,
    SECRET_RULESET_ID,
    SECRET_RULESET_VERSION,
)
from tests._catalog import CORE_ROOT, plugin_root
from tests.hook_samples import resolved_hook, sample_hook
from tests.hooks.guard_config.compile_kit import compiled_document, prompt, request_for, two_hooks

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.detector.facts import Facts


# --- the §E.0.5 protect and control-plane tables (Track K5) ----------------------------


def test_resource_roots_are_package_relative_ids(repo: Path) -> None:
    packages = ("coding_agent_playbook", "coding_agent_playbook.plugins.superpowers")

    table = compiled_document(request_for(repo))["protected"]

    assert resource_root_ids(packages) == [
        "pkg:coding_agent_playbook/resources",
        "pkg:coding_agent_playbook.plugins.superpowers/resources",
    ]
    assert table["resource_roots"] == resource_root_ids(packages)
    assert table["hook_artifacts"] == list(HOOK_ARTIFACTS)
    assert table["hook_artifacts"] == [
        ".coding-agent-playbook/hooks/",
        ".claude/hooks/playbook/",
        ".opencode/plugins/playbook-hooks.js",
    ]
    assert table["output_dirs"] == [".claude/commands/", "AGENTS.md"]


@pytest.mark.catalog
def test_bundled_layers_resolve_to_their_catalog_dirs_never_importing() -> None:
    """The engine and a bundled plugin resolve through ``catalog`` (SPEC v0.19):
    the ids keep their ``resources`` spelling, the paths are the layers' content dirs,
    and an unknown plugin leaf is left out like an unimportable overlay."""
    from coding_agent_playbook.hooks.guard_config.resource_roots import resolve_resource_roots

    roots = resolve_resource_roots(
        [
            "coding_agent_playbook",
            "coding_agent_playbook.plugins.superpowers",
            "coding_agent_playbook.plugins.no_such_plugin",
            "json",  # importable, ships no resources/
        ]
    )

    assert roots == {
        "pkg:coding_agent_playbook/resources": str(CORE_ROOT),
        "pkg:coding_agent_playbook.plugins.superpowers/resources": str(plugin_root("superpowers")),
    }


def test_sentinel_key_is_the_generated_output_sentinel(repo: Path) -> None:
    assert compiled_document(request_for(repo))["sentinel"] == SENTINEL


def test_control_plane_rows_are_engine_constants(repo: Path, tmp_path: Path) -> None:
    """Rendered from the runtime's own constants; no input changes them (overlays: extra_paths)."""
    bare = compiled_document(request_for(repo))["control_plane"]
    other = compiled_document(request_for(repo, two_hooks(tmp_path), ProtectInputs()))[
        "control_plane"
    ]

    assert bare == {key: list(rows) for key, rows in CONTROL_PLANE.items()}
    assert other == bare
    assert ".claude/settings.json" in bare["settings"]
    assert bare["toml_deny"] == ["hooks", "guardrails"]


def test_runtime_reads_the_control_plane_tables_back(repo: Path) -> None:
    (repo / ".pre-commit-config.yaml").write_text("- id: playbook-sync-check\n", "utf-8")

    parsed = parse_guard_config(compile_guard_config(request_for(repo)).data)

    assert isinstance(parsed, GuardConfig), parsed
    assert parsed.tables["precommit"] == {"playbook_hook_ids": ["playbook-sync-check"]}
    assert parsed.tables["control_plane"]["mcp"] == [".mcp.json"]


# --- K5 step 3: facts, applicability, eval, auto_sync (§E.0.5) -------------------------

_ML_RULE = Rule(
    RuleFrontmatter(
        id="ml-serialization-security",
        name="ML serialization",
        description="Never unpickle untrusted data.",
        scope="always",
        applies_if={"any_ml_stack": ["torch"]},
    ),
    "Use safetensors.\n",
    "Use safetensors.\n",
    False,
    None,
    "coding_agent_playbook",
)


def test_facts_carry_dependency_names_and_presence_flags(repo: Path) -> None:
    facts: Facts = {
        "dependencies": {"torch": ">=2", "fastapi": ""},
        "dev_dependencies": {"pytest": ">=8"},
        "ml_stack": {"torch": ">=2"},
        "has_dockerfile": True,
        "has_ci": False,
        "python_version": "3.12",
    }
    request = dataclasses.replace(request_for(repo), detect=DetectInputs(facts=facts))

    assert compiled_document(request)["facts"] == {
        "dependencies": ["fastapi", "torch"],
        "dev_dependencies": ["pytest"],
        "has_ci": False,
        "has_dockerfile": True,
        "has_notebooks": False,
    }


def test_applicability_rows_cover_rules_prompts_and_skipped_hooks(repo: Path) -> None:
    linked = sample_hook(
        "coding_agent_playbook", id="ml-guard", linked_rule=_ML_RULE.frontmatter.id
    )
    gated = sample_hook(id="nb-guard", applies_if={"has_notebooks": True})
    opt_in = sample_hook(id="later", tier="opt-in", applies_if={"has_notebooks": True})
    always = sample_hook(id="guard-x")
    hooks = [linked, gated, opt_in, always]
    view = resolve_effective_hooks(
        hooks,
        [_ML_RULE],
        HooksConfig(enabled=True),
        GuardrailsConfig(),
        {},
        repo,
        adapters_enabled=["claude_code"],
    )
    rows = applicability_rows(
        rules=[_ML_RULE],
        prompts=[prompt("security-review", {"any_ml_stack": ["torch"]}), prompt("explain")],
        hooks=hooks,
        view=view,
        facts={},
        repo_root=repo,
    )
    request = dataclasses.replace(request_for(repo), detect=DetectInputs(applicability=rows))

    table = compiled_document(request)["applicability"]

    torch = [{"any_ml_stack": ["torch"]}]
    assert table == [
        {
            "kind": "hook",
            "id": "guard-x",
            "applies_if": [],
            "source": "<repo-local>",
            "active": True,
        },
        {
            "kind": "hook",
            "id": "ml-guard",
            "applies_if": torch,
            "source": "coding_agent_playbook",
            "active": False,
        },
        {
            "kind": "hook",
            "id": "nb-guard",
            "applies_if": [{"has_notebooks": True}],
            "source": "<repo-local>",
            "active": False,
        },
        {
            "kind": "prompt",
            "id": "explain",
            "applies_if": [],
            "source": "<repo-local>",
            "active": True,
        },
        {
            "kind": "prompt",
            "id": "security-review",
            "applies_if": torch,
            "source": "<repo-local>",
            "active": False,
        },
        {
            "kind": "rule",
            "id": "ml-serialization-security",
            "applies_if": torch,
            "source": "coding_agent_playbook",
            "active": False,
        },
    ]  # the opt-in hook is off by tier: new facts can never turn it on


def test_eval_fixture_globs_default(repo: Path) -> None:
    document = compiled_document(request_for(repo))

    assert document["eval"] == {"fixture_globs": ["**/eval_samples/*/setup/**"]}
    assert document["path_classes"]["eval_fixture"] == document["eval"]["fixture_globs"]


def test_auto_sync_rendered_from_hooks_table(repo: Path) -> None:
    hooks_config = HooksConfig(enabled=True, auto_sync=True)
    on = dataclasses.replace(request_for(repo), hooks_config=hooks_config)

    assert compiled_document(request_for(repo))["auto_sync"] is False
    assert compiled_document(on)["auto_sync"] is True
    parsed = parse_guard_config(compile_guard_config(on).data)
    assert isinstance(parsed, GuardConfig) and parsed.tables["auto_sync"] is True


def test_facts_carry_the_package_manager_when_detected(repo: Path) -> None:
    """dependency-allowlist-guard's tier (a) reads ``facts.package_manager`` (§E.4)."""
    detected = dataclasses.replace(
        request_for(repo), detect=DetectInputs(facts={"package_manager": "uv"})
    )

    assert compiled_document(detected)["facts"]["package_manager"] == "uv"
    assert "package_manager" not in compiled_document(request_for(repo))["facts"]


# --- the verify-pack prompts table and prompt-write-scope-guard's scopes (§E.2, §E.3) ---


def _contract_prompt(prompt_id: str, slash: str, contract: list[str]) -> Prompt:
    fm = PromptFrontmatter(
        id=prompt_id, name=prompt_id, description="d", slash=slash, output_contract=contract
    )
    return Prompt(fm, "Body\n", "Body\n", False, None, "coding_agent_playbook")


def test_prompts_table_maps_slash_to_contract(repo: Path) -> None:
    verdict = r"(?im)^\W*(approve|request changes)\W*$"
    prompts = [
        _contract_prompt("review", "review", [verdict]),
        _contract_prompt("explain", "explain", []),
        _contract_prompt(
            "review-overlay", "review", ["shadowed"]
        ),  # the first prompt per slash wins
    ]
    request = dataclasses.replace(request_for(repo), prompts=prompts)

    table = compiled_document(request)["prompts"]

    assert table == {
        "review": {"id": "review", "output_contract": [verdict]},
        "explain": {"id": "explain", "output_contract": []},
    }
    parsed = parse_guard_config(compile_guard_config(request).data)
    assert isinstance(parsed, GuardConfig) and parsed.tables["prompts"] == table
    assert compiled_document(request_for(repo))["prompts"] == {}


def _scoped_prompt(slash: str, scope: dict[str, Any]) -> Prompt:
    scoped = prompt(slash)
    scoped.frontmatter.write_scope = scope
    return scoped


def test_prompt_scopes_rendered_into_the_scope_guard_config_only(repo: Path) -> None:
    guard = resolved_hook("prompt-write-scope-guard", config={"keep": 1})
    other = resolved_hook("guard-y")
    prompts = [
        _scoped_prompt("review", {"read_only": True}),
        _scoped_prompt("generate-tests", {"globs": ["tests/**", "**/conftest.py"]}),
        prompt("refactor"),  # no write_scope: no row
    ]
    request = dataclasses.replace(request_for(repo, [guard, other]), prompts=prompts)

    hooks = compiled_document(request)["hooks"]

    assert hooks["prompt-write-scope-guard"]["handlers"]["pre_tool_use"]["config"] == {
        "keep": 1,
        "scopes": {
            "generate-tests": {"globs": ["tests/**", "**/conftest.py"]},
            "review": {"read_only": True},
        },
    }
    assert hooks["guard-y"] == other.to_json()
    assert guard.handlers["pre_tool_use"].config == {"keep": 1}  # the resolved hook is untouched


def test_runtime_reads_the_scopes_back(repo: Path) -> None:
    guard = resolved_hook("prompt-write-scope-guard")
    scoped = [_scoped_prompt("x", {"read_only": True})]
    request = dataclasses.replace(request_for(repo, [guard]), prompts=scoped)

    parsed = parse_guard_config(compile_guard_config(request).data)

    assert isinstance(parsed, GuardConfig)
    spec = parsed.hooks["prompt-write-scope-guard"].handlers[EventName.PRE_TOOL_USE]
    assert spec.config["scopes"] == {"x": {"read_only": True}}


# --- the K8 secret tables and the allowlists (§E.4, §D.8.2) -----------------------------


def test_secret_rules_table_rendered(repo: Path) -> None:
    """The §E.4 secret tables: exemptions beside the globs, the ruleset and overlay rows."""
    acme = {"id": "acme-token", "regex": "acme_[0-9a-f]{32}", "label": "Acme token"}
    content = resolved_hook(
        "secret-content-guard",
        config={"extra_patterns": [acme, "corp_[A-Z0-9]{20}", "(a+)+$"]},
    )
    sweep = resolved_hook("stop-diff-sweep", events=("stop",), config={"extra_patterns": [acme]})
    request = dataclasses.replace(
        request_for(repo, [content, sweep]),
        guardrails=GuardrailsConfig(secrets=SecretsGuardrails(allow_paths=("tests/fixtures/**",))),
    )

    cfg = compiled_document(request)

    assert cfg["secret_path_exempt"] == [*SECRET_PATH_EXEMPT, "tests/fixtures/**"]
    assert cfg["secret_glob_exempt"] == {g: list(e) for g, e in SECRET_GLOB_EXEMPT.items()}
    rules = cfg["secret_rules"]
    assert (rules["ruleset"], rules["version"]) == (SECRET_RULESET_ID, SECRET_RULESET_VERSION)
    assert rules["rule_ids"] == [rule_id for rule_id, _, _ in SECRET_CONTENT_RULES]
    corp_id = "extra-" + hashlib.sha256(b"corp_[A-Z0-9]{20}").hexdigest()[:8]
    assert rules["extra_patterns"] == [  # deduped across both hooks; the ReDoS row dropped
        acme,
        {"id": corp_id, "regex": "corp_[A-Z0-9]{20}", "label": "overlay secret pattern"},
    ]
    parsed = parse_guard_config(serialize_guard_config(cfg))
    assert isinstance(parsed, GuardConfig)
    assert parsed.tables["secret_rules"] == rules


def test_allowlists_table_rendered_from_the_guards_configs(repo: Path) -> None:
    """§D.8.2 ``allowlists``: the dependency allowlist, its index and the egress hosts."""
    deps = resolved_hook(
        "dependency-allowlist-guard",
        config={"allowlist": ["Foo_Bar", "numpy"], "required_index": "https://pypi.corp/simple"},
    )
    egress = resolved_hook("exfil-channel-guard", config={"allowed_hosts": ["Corp.Example"]})

    table = compiled_document(request_for(repo, [deps, egress]))["allowlists"]

    assert table == {
        "dependencies": ["foo-bar", "numpy"],
        "required_index": "https://pypi.corp/simple",
        "egress_hosts": ["corp.example"],
    }
    assert compiled_document(request_for(repo))["allowlists"] == {
        "dependencies": [],
        "required_index": "",
        "egress_hosts": [],
    }
