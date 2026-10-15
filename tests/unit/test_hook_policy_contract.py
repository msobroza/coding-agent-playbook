"""The per-hook trust contract, ``hook_policy.classify_hook`` (specs/prK-lifecycle-hooks.md §B.5).

``classify_hook`` is pure over one ``Hook`` and a ``HookCheckContext``: it judges
the value domains ``HookFrontmatter.from_mapping`` leaves alone (H2-H13, H17,
H18), as errors plus the few warnings the spec names (H4, H9, H11). Every
message names the offending value and the expected shape. H1 (structure) is
the parser's, H14/H15 the layer merge's, H19 validate's body check and the
set-level rules ``classify_hook_set``'s (``test_hook_policy_contract_set.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_policy import HookCheckContext, HookIssue, classify_hook
from coding_agent_playbook.types import Hook
from tests.hook_samples import HOOK_WHERE, sample_hook, write_hook

if TYPE_CHECKING:
    from pathlib import Path

ENGINE = "coding_agent_playbook"
OVERLAY = "acme_rules"
REPO_LOCAL = "<repo-local>"
PACK = "coding_agent_playbook.packs.superpowers"
_EXTERNAL = {"command": "python", "script": "scripts/check.py"}


def _messages(
    hook: Hook, ctx: HookCheckContext | None = None, *, severity: str = "error"
) -> list[str]:
    issues = classify_hook(hook, ctx or HookCheckContext())
    return [issue.message for issue in issues if issue.severity == severity]


def test_a_well_formed_hook_has_no_issues() -> None:
    assert classify_hook(sample_hook(path=HOOK_WHERE), HookCheckContext()) == []


def test_issues_are_located_at_the_hook_file() -> None:
    issues = classify_hook(sample_hook(path=HOOK_WHERE, timeout=0), HookCheckContext())

    assert issues == [HookIssue("error", HOOK_WHERE, "timeout 0 must be > 0 and <= 600 seconds")]


def test_a_hook_without_a_file_is_located_by_id_and_layer() -> None:
    issues = classify_hook(sample_hook(OVERLAY, timeout=0), HookCheckContext())

    assert [issue.where for issue in issues] == [f"hooks/guard-x ({OVERLAY})"]


# (case id, source package, frontmatter overrides, expected error message)
_ERROR_CASES: list[tuple[str, str, dict[str, Any], str]] = [
    (
        "H2-pattern",
        REPO_LOCAL,
        {"id": "Guard_X"},
        "id 'Guard_X' must match ^[a-z0-9][a-z0-9-]{0,62}$ and equal directory 'guard-x'",
    ),
    (
        "H2-directory",
        REPO_LOCAL,
        {"id": "guard-y"},
        "id 'guard-y' must match ^[a-z0-9][a-z0-9-]{0,62}$ and equal directory 'guard-x'",
    ),
    (
        "H3-camel-case",
        REPO_LOCAL,
        {"events": ["PreToolUse"]},
        "event 'PreToolUse' is not canonical; did you mean 'pre_tool_use'?",
    ),
    (
        "H3-unknown",
        REPO_LOCAL,
        {"events": ["pre_tool_use", "on_boot"]},
        "event 'on_boot' is not canonical; allowed: session_start, user_prompt_submit, "
        "pre_tool_use, post_tool_use, post_tool_use_failure, stop, subagent_stop, "
        "pre_compact, session_end",
    ),
    ("H3-empty", REPO_LOCAL, {"events": []}, "events: must list at least one canonical event"),
    (
        "H3-duplicate",
        REPO_LOCAL,
        {"events": ["pre_tool_use", "pre_tool_use"]},
        "events: 'pre_tool_use' is listed more than once",
    ),
    (
        "H4-field-not-for-event",
        REPO_LOCAL,
        {"events": ["pre_tool_use", "stop"], "matcher": {"stop": {"tools": ["shell"]}}},
        "matcher.stop.tools: 'tools' is not valid for event 'stop'",
    ),
    (
        "H4-undeclared-event",
        REPO_LOCAL,
        {"matcher": {"post_tool_use": {"tools": ["edit"]}}},
        "matcher.post_tool_use: 'post_tool_use' is not in events ['pre_tool_use']",
    ),
    (
        "H4-runtime-only-class",
        REPO_LOCAL,
        {"matcher": {"pre_tool_use": {"tools": ["other"]}}},
        "matcher.pre_tool_use.tools: tool class 'other' is runtime-only and cannot be authored",
    ),
    (
        "H4-unknown-class",
        REPO_LOCAL,
        {"matcher": {"pre_tool_use": {"tools": ["bash"]}}},
        "matcher.pre_tool_use.tools: unknown tool class 'bash'; allowed: shell, edit, write, "
        "notebook_edit, read, search, web, subagent, mcp",
    ),
    (
        "H4-regex",
        REPO_LOCAL,
        {"matcher": {"pre_tool_use": {"command": ["git (push"]}}},
        "matcher.pre_tool_use.command: regex 'git (push' does not compile: "
        "missing ), unterminated subpattern at position 4",
    ),
    (
        "H4-glob-escape",
        REPO_LOCAL,
        {"matcher": {"pre_tool_use": {"paths": ["src/../secrets/*"]}}},
        "matcher.pre_tool_use.paths: glob 'src/../secrets/*' must be a non-empty relative "
        "pattern without '..'",
    ),
    (
        "H4-glob-absolute",
        REPO_LOCAL,
        {"matcher": {"pre_tool_use": {"paths": ["/etc/*"]}}},
        "matcher.pre_tool_use.paths: glob '/etc/*' must be a non-empty relative pattern "
        "without '..'",
    ),
    (
        "H4-closed-vocabulary",
        REPO_LOCAL,
        {
            "events": ["session_start"],
            "decisions": ["context"],
            "on_error": "open",
            "matcher": {"session_start": {"sources": ["boot"]}},
        },
        "matcher.session_start.sources: unknown value 'boot'; allowed: clear, compact, fork, "
        "resume, startup",
    ),
    (
        "H5-allow",
        REPO_LOCAL,
        {"decisions": ["deny", "allow"]},
        "decision 'allow' is never permitted: it would bypass the harness permission system",
    ),
    (
        "H5-unknown",
        REPO_LOCAL,
        {"decisions": ["block"]},
        "decision 'block' is not one of deny, ask, context, none",
    ),
    (
        "H5-not-for-any-event",
        REPO_LOCAL,
        {"events": ["stop"], "decisions": ["ask"], "on_error": "open"},
        "decision 'ask' is not valid for any declared event ['stop']; they allow: context, "
        "deny, none",
    ),
    (
        "H5-empty",
        REPO_LOCAL,
        {"decisions": []},
        "decisions: must list at least one of deny, ask, context, none",
    ),
    (
        "H6-both",
        REPO_LOCAL,
        {"handlers": {"pre_tool_use": {"builtin": "guard_y"}}},
        "exactly one of handler / handlers is required, got both",
    ),
    (
        "H6-neither",
        REPO_LOCAL,
        {"handler": None},
        "exactly one of handler / handlers is required, got neither",
    ),
    (
        "H6-handlers-keys",
        REPO_LOCAL,
        {
            "events": ["pre_tool_use", "stop"],
            "handler": None,
            "handlers": {"pre_tool_use": {"builtin": "guard_x"}, "post_tool_use": {"builtin": "x"}},
        },
        "handlers: keys must equal events exactly; missing ['stop'], unexpected ['post_tool_use']",
    ),
    (
        "H6-two-forms",
        REPO_LOCAL,
        {"handler": {"builtin": "guard_x", "command": "python"}},
        "handler: exactly one form: builtin, or command + script (+ args); got builtin "
        "'guard_x' with command",
    ),
    (
        "H6-incomplete-external",
        REPO_LOCAL,
        {"handler": {"command": "python"}},
        "handler: an external handler needs both command and script; missing script",
    ),
    (
        "H6-builtin-name",
        REPO_LOCAL,
        {"handler": {"builtin": "GuardX"}},
        "handler.builtin 'GuardX' must be snake_case, or '<name>:<role>' for a companion",
    ),
    (
        "H7-launcher",
        REPO_LOCAL,
        {"handler": {"command": "ruby", "script": "scripts/check.rb"}},
        "handler.command 'ruby' is not a launcher; allowed: python, bash, sh, node",
    ),
    (
        "H7-escape",
        REPO_LOCAL,
        {"handler": {"command": "bash", "script": "../x.sh"}},
        "handler.script '../x.sh' escapes the hook directory",
    ),
    (
        "H7-not-under-scripts",
        REPO_LOCAL,
        {"handler": {"command": "bash", "script": "run.sh"}},
        "handler.script 'run.sh' must be a relative POSIX path under scripts/",
    ),
    (
        "H7-url-arg",
        REPO_LOCAL,
        {"handler": {**_EXTERNAL, "args": ["--from", "https://example.com/x"]}},
        "handler.args: 'https://example.com/x' must not contain '://' (static args only)",
    ),
    (
        "H9-tool-event-cap",
        REPO_LOCAL,
        {"timeout": 45},
        "timeout 45 exceeds 30 s for tool and prompt events ['pre_tool_use']",
    ),
    (
        "H9-bounds",
        REPO_LOCAL,
        {"events": ["stop"], "decisions": ["none"], "on_error": "open", "timeout": 601},
        "timeout 601 must be > 0 and <= 600 seconds",
    ),
    (
        "H10-deny-outside-overlay",
        REPO_LOCAL,
        {"on_error": "deny"},
        "on_error 'deny' (fail-closed) is reserved for overlay hooks",
    ),
    (
        "H10-unknown",
        REPO_LOCAL,
        {"on_error": "fail"},
        "on_error 'fail' is not one of ask, deny, open",
    ),
    (
        "H10-not-for-any-event",
        REPO_LOCAL,
        {"events": ["stop"], "decisions": ["deny"], "on_error": "ask"},
        "on_error 'ask' is not valid for any declared event ['stop']; they allow: open",
    ),
    (
        "H11-empty",
        REPO_LOCAL,
        {"supports": []},
        "supports: must list at least one of claude_code, opencode",
    ),
    (
        "H11-unknown-adapter",
        REPO_LOCAL,
        {"supports": ["claude_code", "continue"]},
        "supports: adapter 'continue' cannot enforce hooks; allowed: claude_code, opencode",
    ),
    (
        "H11-unreachable",
        REPO_LOCAL,
        {
            "events": ["session_end"],
            "decisions": ["none"],
            "on_error": "open",
            "supports": ["opencode"],
        },
        "no declared event of hook 'guard-x' is reachable on adapter 'opencode'",
    ),
    (
        "H12-unknown-tier",
        REPO_LOCAL,
        {"tier": "core"},
        "tier 'core' is not one of default, opt-in, overlay",
    ),
    (
        "H12-overlay-tier",
        OVERLAY,
        {"tier": "overlay"},
        "tier 'overlay' is reserved for engine mechanisms; an overlay's own hook uses "
        "'default' or 'opt-in'",
    ),
    (
        "H12-mandatory-outside-overlay",
        REPO_LOCAL,
        {"mandatory": True},
        "mandatory: true is reserved for overlay hooks",
    ),
    (
        "H12-mandatory-disabled",
        OVERLAY,
        {"mandatory": True, "enabled": False},
        "mandatory: true requires enabled: true",
    ),
    (
        "H13-engine-external",
        ENGINE,
        {"handler": _EXTERNAL},
        "engine hooks are builtin-only; handler is an external command",
    ),
    (
        "H17",
        REPO_LOCAL,
        {"applies_if": {"orm_version": ">=2"}},
        "applies_if: unknown predicate key: 'orm_version'",
    ),
]


@pytest.mark.parametrize(
    ("source", "overrides", "expected"),
    [case[1:] for case in _ERROR_CASES],
    ids=[case[0] for case in _ERROR_CASES],
)
def test_classify_hook_rule(source: str, overrides: dict[str, Any], expected: str) -> None:
    hook = sample_hook(source, path=HOOK_WHERE, **overrides)

    assert expected in _messages(hook)


def test_h17_checks_every_key_even_after_a_false_one() -> None:
    # evaluate_predicate stops at the first false key; each key is judged on its own.
    hook = sample_hook(applies_if={"python_version": ">=99", "orm_version": ">=2"})

    assert _messages(hook) == ["applies_if: unknown predicate key: 'orm_version'"]


def test_h18_linked_rule_must_resolve() -> None:
    ctx = HookCheckContext(rule_ids=frozenset({"python-error-handling"}))
    hook = sample_hook(linked_rule="python-error-handlng")

    assert _messages(hook, ctx) == [
        "linked_rule 'python-error-handlng' not found in the merged rule set; "
        "did you mean 'python-error-handling'?"
    ]
    assert _messages(sample_hook(linked_rule="python-error-handling"), ctx) == []


def test_h12_overlay_may_ship_config_for_an_engine_overlay_tier_mechanism() -> None:
    engine = sample_hook(ENGINE, tier="overlay")
    overlay = sample_hook(OVERLAY, tier="overlay")
    ctx = HookCheckContext(definitions={"guard-x": (engine, overlay)})

    assert _messages(engine, ctx) == []
    assert _messages(overlay, ctx) == []


def test_h13_engine_hooks_ship_no_scripts(tmp_path: Path) -> None:
    path = write_hook(tmp_path / "hooks", scripts=True)
    hook = Hook.from_markdown(path, ENGINE)

    assert "engine hooks ship no scripts/ directory" in _messages(hook)


def test_a_two_event_hook_may_declare_on_error_for_its_guard_half() -> None:
    # §A.2: on_error is clamped per firing event, so ask is valid via pre_tool_use.
    hook = sample_hook(
        events=["pre_tool_use", "stop"],
        decisions=["deny", "none"],
        on_error="ask",
        handler=None,
        handlers={"pre_tool_use": {"builtin": "guard_x:pre_edit"}, "stop": {"builtin": "guard_x"}},
    )

    assert _messages(hook) == []


def test_pack_source_package_is_overlay_not_engine() -> None:
    # A bundled pack is an overlay (exact engine match only): deny, mandatory and
    # external handlers are an overlay's to use.
    hook = sample_hook(PACK, on_error="deny", mandatory=True, handler=_EXTERNAL)

    assert _messages(hook) == []
    assert _messages(sample_hook(ENGINE, on_error="deny")) == [
        "on_error 'deny' (fail-closed) is reserved for overlay hooks"
    ]


# --- warnings (H4, H9, H11; OQ-43) -------------------------------------------------


def test_mcp_on_opencode_and_unreachable_event_are_warnings() -> None:
    hook = sample_hook(
        events=["pre_tool_use", "subagent_stop"],
        decisions=["deny", "none"],
        supports=["claude_code", "opencode"],
        matcher={"pre_tool_use": {"tools": ["shell", "mcp"]}},
    )

    assert _messages(hook) == []
    assert _messages(hook, severity="warning") == [
        "matcher.pre_tool_use.tools: tool class 'mcp' is unsupported on adapter 'opencode' "
        "(degraded there)",
        "event 'subagent_stop' is not supported by adapter 'opencode' (degraded)",
    ]


def test_engine_hook_degradation_is_not_a_consumer_warning() -> None:
    """The engine's degraded cells are the documented §C.5.1 matrix (``playbook check``
    labels them); warning about them would print in every consumer's sync (Track K5)."""
    hook = sample_hook(
        ENGINE,
        events=["pre_tool_use", "subagent_stop"],
        decisions=["deny", "none"],
        supports=["claude_code", "opencode"],
        matcher={"pre_tool_use": {"tools": ["edit", "notebook_edit", "mcp"]}},
    )

    assert _messages(hook) == []
    assert _messages(hook, severity="warning") == []


def test_timeout_above_event_cap_is_warning() -> None:
    hook = sample_hook(events=["session_start"], decisions=["context"], on_error="open", timeout=20)

    assert _messages(hook) == []
    assert _messages(hook, severity="warning") == [
        "timeout 20 exceeds the 15 s deadline cap of event 'session_start'; it is clamped to 15 s"
    ]


# --- H7 on disk: the script must be a regular file contained in the hook dir --------


def _external(tmp_path: Path, script: str = "scripts/check.py", **handler: Any) -> Hook:
    path = write_hook(
        tmp_path / "hooks", scripts=True, handler={**_EXTERNAL, "script": script, **handler}
    )
    return Hook.from_markdown(path, REPO_LOCAL)


def test_h7_contained_regular_script_passes(tmp_path: Path) -> None:
    hook = _external(tmp_path)
    assert hook.scripts_dir is not None
    (hook.scripts_dir / "check.py").write_text("print('ok')\n", encoding="utf-8")

    assert _messages(hook) == []


def test_h7_missing_or_directory_script_is_not_a_regular_file(tmp_path: Path) -> None:
    hook = _external(tmp_path, script="scripts/sub")
    assert hook.scripts_dir is not None
    (hook.scripts_dir / "sub").mkdir()

    assert _messages(hook) == ["handler.script 'scripts/sub' is not a regular file"]


def test_h7_symlinked_script_is_refused(tmp_path: Path) -> None:
    hook = _external(tmp_path)
    assert hook.scripts_dir is not None
    outside = tmp_path / "outside.py"
    outside.write_text("print('x')\n", encoding="utf-8")
    (hook.scripts_dir / "check.py").symlink_to(outside)

    assert _messages(hook) == [
        "handler.script 'scripts/check.py' is a symlink; copy the file into the hook directory"
    ]


def test_h7_scripts_dir_linking_out_escapes(tmp_path: Path) -> None:
    path = write_hook(tmp_path / "hooks", handler=_EXTERNAL)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "check.py").write_text("print('x')\n", encoding="utf-8")
    (path.parent / "scripts").symlink_to(elsewhere, target_is_directory=True)
    hook = Hook.from_markdown(path, REPO_LOCAL)

    assert _messages(hook) == [
        "handler.script 'scripts/check.py' is a symlink; copy the file into the hook directory"
    ]


def test_h7_scripts_dir_only_for_external_handlers(tmp_path: Path) -> None:
    hook = Hook.from_markdown(write_hook(tmp_path / "hooks", scripts=True), REPO_LOCAL)

    assert _messages(hook) == [
        "scripts/ exists but no handler is external; only an external handler may ship scripts"
    ]


def test_h7_external_config_must_be_json_serializable(tmp_path: Path) -> None:
    import datetime

    hook = _external(tmp_path, config={"since": datetime.date(2026, 1, 1)})
    assert hook.scripts_dir is not None
    (hook.scripts_dir / "check.py").write_text("", encoding="utf-8")

    assert _messages(hook) == [
        "handler.config is not JSON-serializable (it is passed to the script as JSON): "
        "Object of type date is not JSON serializable"
    ]
