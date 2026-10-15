"""The registry half of the hook contract at sync: H6, H21 and entry-point resolution (prK §B.5, §D.3.1).

Catalogs are built on an injected in-tree module map and an injected
entry-point list (``FakeEntryPoint``), so no test depends on what happens to
be installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_policy import (
    HookCheckContext,
    HookSetInputs,
    RegistryCatalog,
    classify_hook,
    classify_hook_set,
    merge_config,
    resolve_effective_hooks,
)
from coding_agent_playbook.hook_policy.handler_catalog import config_findings, registry_findings
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
from tests.hook_samples import sample_hook

if TYPE_CHECKING:
    import pytest

    from coding_agent_playbook.hook_policy.merge import ConfigKeySpec

THIS_MODULE = __name__


@register_hook_handler(
    "k2cat_guard",
    events=["pre_tool_use"],
    decisions=["deny", "none"],
    config_schema={
        "mode": ConfigKey("string", "strictest", ("off", "warn", "block")),
        "paths": ConfigKey("list", "extend"),
    },
)
def k2cat_guard(ev: object, ctx: object) -> None:
    return None


@register_hook_handler(
    "k2cat_rewriter", events=["pre_tool_use"], decisions=["deny"], mutates_input=True
)
def k2cat_rewriter(ev: object, ctx: object) -> None:
    return None


def not_a_handler(ev: object, ctx: object) -> None:
    return None


@dataclass
class FakeDist:
    name: str = "acme-rules"
    version: str = "1.2.0"


@dataclass
class FakeEntryPoint:
    """The parts of ``importlib.metadata.EntryPoint`` the catalog reads."""

    name: str
    value: str
    obj: Any = None
    error: Exception | None = None
    dist: FakeDist | None = field(default_factory=FakeDist)

    def load(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.obj


def _catalog(
    *entry_points: FakeEntryPoint, in_tree: dict[str, str] | None = None
) -> RegistryCatalog:
    return RegistryCatalog(modules=in_tree or {}, entry_points=lambda: entry_points)


IN_TREE = {"k2cat_guard": THIS_MODULE, "k2cat_rewriter": THIS_MODULE}


def _messages(findings: list[Any]) -> list[str]:
    return [message for _, message in findings]


# --- H6 -----------------------------------------------------------------------------------


def test_h6_unregistered_builtin_lists_known_handlers() -> None:
    hook = sample_hook(handler={"builtin": "guard_nope"})

    issues = classify_hook(hook, HookCheckContext(handlers=_catalog(in_tree=IN_TREE)))

    assert [i.message for i in issues] == [
        "handler.builtin 'guard_nope' is not a registered handler; "
        "known handlers: k2cat_guard, k2cat_rewriter"
    ]


def test_registry_half_is_skipped_without_a_catalog() -> None:
    assert classify_hook(sample_hook(handler={"builtin": "guard_nope"}), HookCheckContext()) == []


def test_h6_handler_decisions_must_be_subset_of_declared() -> None:
    hook = sample_hook(handler={"builtin": "k2cat_guard"}, decisions=["deny", "ask", "none"])

    findings = registry_findings(hook, _catalog(in_tree=IN_TREE))

    assert _messages(findings) == [
        "decisions ['ask'] are not declared by handler 'k2cat_guard' (it declares deny, none)"
    ]


def test_h6_handler_must_serve_every_bound_event() -> None:
    hook = sample_hook(handler={"builtin": "k2cat_guard"}, events=["pre_tool_use", "post_tool_use"])

    findings = registry_findings(hook, _catalog(in_tree=IN_TREE))

    assert _messages(findings) == [
        "handler: handler 'k2cat_guard' does not serve ['post_tool_use'] "
        "(it serves ['pre_tool_use'])"
    ]


def test_h6_mutates_input_true_is_rejected() -> None:
    hook = sample_hook(handler={"builtin": "k2cat_rewriter"}, decisions=["deny"])

    findings = registry_findings(hook, _catalog(in_tree=IN_TREE))

    assert _messages(findings) == [
        "handler 'k2cat_rewriter' declares MUTATES_INPUT = True; hooks never rewrite tool input (L6)"
    ]


def test_h6_authored_config_is_checked_against_config_schema() -> None:
    hook = sample_hook(
        handler={"builtin": "k2cat_guard", "config": {"mode": "loud", "extra": 1, "paths": ["a"]}},
        decisions=["deny"],
    )

    findings = registry_findings(hook, _catalog(in_tree=IN_TREE))

    assert _messages(findings) == [
        "handler.config.mode: expected a string one of ['off', 'warn', 'block'], got 'loud'",
        "handler.config.extra: not a config key of handler 'k2cat_guard'; allowed: mode, paths",
    ]


def test_broken_entry_point_is_a_finding_not_a_crash() -> None:
    catalog = _catalog(
        FakeEntryPoint("guard_x", "acme.broken:guard", error=ImportError("no module")),
        FakeEntryPoint("guard_y", f"{THIS_MODULE}:not_a_handler", obj=not_a_handler),
    )

    x = registry_findings(sample_hook(handler={"builtin": "guard_x"}), catalog)
    y = registry_findings(sample_hook(handler={"builtin": "guard_y"}), catalog)

    assert _messages(x) == [
        "handler.builtin 'guard_x': entry point 'acme.broken:guard' failed to load: ImportError"
    ]
    assert "is not a @register_hook_handler function" in _messages(y)[0]


# --- H21 ----------------------------------------------------------------------------------


def test_h21_hooks_subtable_validated_against_config_schema() -> None:
    hook = sample_hook(handler={"builtin": "k2cat_guard"}, decisions=["deny"])
    cfg = HooksConfig(
        enabled=True, per_hook={"guard-x": {"mode": "block", "nope": 1, "paths": "x"}}
    )

    issues = classify_hook_set(
        HookSetInputs(hooks=[hook], hooks_cfg=cfg, handlers=_catalog(in_tree=IN_TREE))
    )

    assert [(i.where, i.message) for i in issues] == [
        (
            ".coding-agent-playbook.toml",
            "[hooks.guard-x] nope: not a config key of handler 'k2cat_guard'; allowed: mode, paths",
        ),
        (".coding-agent-playbook.toml", "[hooks.guard-x] paths: expected a list, got 'x'"),
    ]


def test_h21_skips_external_only_hooks_and_unknown_ids() -> None:
    external = sample_hook(handler={"command": "python", "script": "scripts/a.py"})

    findings = config_findings(
        [external], {"guard-x": {"anything": 1}, "nope": {"a": 1}}, _catalog(in_tree=IN_TREE)
    )

    assert findings == []


# --- sync-time resolution -----------------------------------------------------------------


def _effective(hook: Any, catalog: RegistryCatalog) -> dict[str, Any]:
    view = resolve_effective_hooks(
        [hook],
        [],
        HooksConfig(enabled=True),
        GuardrailsConfig(),
        {},
        Path("."),
        adapters_enabled=["claude_code"],
        handlers=catalog,
    )
    (resolved,) = view.resolved
    handler: dict[str, Any] = resolved.to_json()["handlers"]["pre_tool_use"]
    return handler


def test_entry_point_handler_resolved_at_sync_in_tree_wins() -> None:
    from_overlay = FakeEntryPoint("acme_guard", f"{THIS_MODULE}:k2cat_guard", obj=k2cat_guard)
    shadowing = FakeEntryPoint("k2cat_guard", "acme.evil:guard", error=AssertionError("loaded"))
    catalog = _catalog(from_overlay, shadowing, in_tree=IN_TREE)

    external = _effective(sample_hook(handler={"builtin": "acme_guard"}), catalog)
    in_tree = _effective(sample_hook(handler={"builtin": "k2cat_guard"}), catalog)

    assert external == {
        "kind": "entry_point",
        "target": f"{THIS_MODULE}:k2cat_guard",
        "dist": "acme-rules==1.2.0",
        "config": {},
    }
    assert in_tree == {"kind": "builtin", "name": "k2cat_guard", "config": {}}
    assert catalog.known() == ("acme_guard", "k2cat_guard", "k2cat_rewriter")


def test_entry_point_without_a_distribution_has_no_dist_pin() -> None:
    point = FakeEntryPoint("acme_guard", f"{THIS_MODULE}:k2cat_guard", obj=k2cat_guard, dist=None)

    entry = _catalog(point).lookup("acme_guard")

    assert entry is not None and (entry.source, entry.dist) == ("entry_point", None)


def test_catalog_key_specs_feed_the_layer_merge() -> None:
    specs: dict[str, ConfigKeySpec] = dict(_catalog(in_tree=IN_TREE).key_specs("k2cat_guard"))

    merged = merge_config(
        {"mode": "block", "paths": ["a"]}, {"mode": "warn", "paths": ["b"]}, specs
    )

    assert merged == {"mode": "block", "paths": ["a", "b"]}
    assert _catalog().key_specs("unknown") == {}
    assert _catalog(in_tree=IN_TREE).config_domain("k2cat_guard") is None


def test_in_tree_name_whose_module_does_not_register_it_is_a_finding() -> None:
    catalog = _catalog(in_tree={"guard_x": "json"})

    findings = registry_findings(sample_hook(), catalog)

    assert _messages(findings) == [
        "handler.builtin 'guard_x': module 'json' does not register handler 'guard_x'"
    ]


def test_validate_reports_unregistered_builtin(
    tmp_path: Path, make_synthetic_repo: Any, make_hook: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    import argparse

    from coding_agent_playbook.commands import validate as _validate

    repo = make_synthetic_repo(tmp_path)
    path = make_hook(repo / "playbook" / "hooks", "guard-q", handler={"builtin": "guard_nope"})

    assert _validate.run(argparse.Namespace(repo_root=str(repo))) == 1

    out = capsys.readouterr().out
    assert f"FAIL {path}: handler.builtin 'guard_nope' is not a registered handler" in out
