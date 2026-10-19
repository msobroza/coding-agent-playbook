"""The handler registry and run-time resolution (specs/prK-lifecycle-hooks.md §D.3.1, D-12).

Builtins resolve through the static module map (no scan), entry-point
handlers through a direct import gated by ``[hooks] allow_code_from`` (no
``importlib.metadata`` at run time), external handlers behind a trust
approval of exactly the copied script, its launcher and its args.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import pkgutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import coding_agent_playbook.hook_runtime.handlers as handlers_package
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.escape import EscapeHatches
from coding_agent_playbook.hook_runtime.dispatch.event import (
    CanonicalEvent,
    EventName,
    Harness,
    ToolCall,
    ToolClass,
)
from coding_agent_playbook.hook_runtime.dispatch.external import (
    EVENT_SCHEMA,
    ExternalContractError,
    parse_external_output,
)
from coding_agent_playbook.hook_runtime.dispatch.registry import (
    HANDLER_ATTR,
    ConfigKey,
    HandlerResolutionError,
    ResolveContext,
    Untrusted,
    builtin_handler_modules,
    declaration_of,
    load_builtin,
    register_hook_handler,
    registered_handlers,
    resolve_handler,
)
from coding_agent_playbook.hook_runtime.dispatch.routing import (
    ASYNC_EVENT,
    ASYNC_SAFE_HANDLERS,
    DECISION_SINK_HANDLERS,
    handler_route,
)
from coding_agent_playbook.hook_runtime.dispatch.run import run_event
from coding_agent_playbook.hook_runtime.dispatch.selection import select_hooks
from coding_agent_playbook.hook_runtime.harness.wire import DENY_EXIT
from coding_agent_playbook.security.trust import HandlerApproval, sha256_of_json
from tests.hook_runtime.fakes import FakeProc, FakeTrustStore
from tests.hook_runtime.guard_repo import GuardRepo, canonical, hook_record
from tests.import_probe import run_python_probe

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

PRE = EventName.PRE_TOOL_USE
type PackageFactory = Callable[..., str]


def _config(*records: dict[str, Any], **extra: Any) -> GuardConfig:
    document = {"schema_version": 1, "hooks": {r["id"]: r for r in records}, **extra}
    cfg = parse_guard_config(canonical(document), platform="linux")
    assert isinstance(cfg, GuardConfig), cfg
    return cfg


def _ctx(cfg: GuardConfig, repo: GuardRepo, **kwargs: Any) -> ResolveContext:
    fields: dict[str, Any] = {
        "cfg": cfg,
        "repo": repo.repo,
        "proc": FakeProc(),
        "env": {},
        "trust": FakeTrustStore,
        **kwargs,
    }
    return ResolveContext(**fields)


# --- the static map and the decorator ---------------------------------------------------


def test_static_module_map_equals_decorator_registry() -> None:
    modules = builtin_handler_modules()
    for module in set(modules.values()):
        importlib.import_module(module)
    mapped = {
        name: d.module for name, d in registered_handlers().items() if d.module in modules.values()
    }

    assert mapped == dict(modules)
    for name in modules:
        declaration = registered_handlers()[name]
        assert declaration.events and declaration.decisions
        assert isinstance(declaration.config_schema, type(declaration.config_schema))
        assert declaration.mutates_input is False


def test_every_in_tree_handler_module_is_in_the_static_map() -> None:
    """Public handler modules are mapped; ``_``-prefixed ones are helpers registering nothing.

    The walk descends into the pack packages: a module under a ``_``-prefixed
    segment (``_shared/``) is a helper too.
    """
    prefix = f"{handlers_package.__name__}."
    infos = pkgutil.walk_packages(handlers_package.__path__, prefix)
    names = {info.name for info in infos if not info.ispkg}
    segments = {name: name.removeprefix(prefix).split(".") for name in names}
    helpers = {name for name in names if any(s.startswith("_") for s in segments[name])}
    for module in sorted(names):
        importlib.import_module(module)

    assert names - helpers <= set(builtin_handler_modules().values())
    assert not {d.module for d in registered_handlers().values()} & helpers


def test_routing_sets_match_the_handler_modules() -> None:
    """``routing`` routes without importing: its static sets mirror the modules (K9, OQ-19).

    Every ``ASYNC_SAFE = True`` module is listed (and decides nothing), and every
    sink is a builtin that can only return ``none``.
    """
    modules = builtin_handler_modules()
    async_safe = set()
    for name, module in modules.items():
        if getattr(importlib.import_module(module), "ASYNC_SAFE", False) is True:
            async_safe.add(name)

    assert async_safe == ASYNC_SAFE_HANDLERS
    for name in ASYNC_SAFE_HANDLERS | DECISION_SINK_HANDLERS:
        assert load_builtin(name).decisions == {Decision.NONE}
    assert EventName(ASYNC_EVENT) in load_builtin("activity_log").events
    assert load_builtin("decision_log").events == frozenset(EventName)


@pytest.mark.parametrize(
    ("event", "name", "decisions", "route"),
    [
        ("pre_tool_use", "decision_log", ["none"], "sink"),
        ("post_tool_use", "activity_log", ["none"], "async"),
        ("session_start", "activity_log", ["none"], "sync"),
        ("post_tool_use", "activity_log", ["context", "none"], "sync"),
        ("post_tool_use", "guard_x", ["none"], "sync"),
    ],
)
def test_handler_route(event: str, name: str, decisions: list[str], route: str) -> None:
    assert handler_route(event, kind="builtin", name=name, decisions=decisions) == route
    assert handler_route(event, kind="external", name=None, decisions=decisions) == "sync"


def test_sink_and_async_routed_hooks_are_selected_only_where_they_run() -> None:
    sink = hook_record(
        "guard-decision-log",
        events=["pre_tool_use", "post_tool_use"],
        decisions=["none"],
        handler={"kind": "builtin", "name": "decision_log"},
    )
    audit = hook_record(
        "local-audit-log",
        events=["post_tool_use"],
        decisions=["none"],
        handler={"kind": "builtin", "name": "activity_log"},
    )
    guard = hook_record("guard-a", events=["post_tool_use"])
    routed = _config(sink, audit, guard, logging={"audit_mode": "async"})
    unrouted = _config(sink, audit, guard)

    def ids(cfg: GuardConfig, *, asynchronous: bool = False) -> list[str]:
        ev = _post_event()
        selection = select_hooks(cfg, ev, EscapeHatches(), asynchronous=asynchronous)
        return [s.record.id for s in selection.selected]

    assert ids(routed) == ["guard-a"]
    assert ids(routed, asynchronous=True) == ["local-audit-log"]
    # Without the async route rendered, the synchronous dispatch keeps the handler.
    assert sorted(ids(unrouted)) == ["guard-a", "local-audit-log"]


def _post_event() -> CanonicalEvent:
    tool = ToolCall(name="Read", native_name="Read", tool_class=ToolClass.READ)
    return CanonicalEvent(
        name=EventName.POST_TOOL_USE,
        harness=Harness.CLAUDE_CODE,
        session_id="s",
        cwd="/r",
        project_dir="/r",
        tool=tool,
    )


@register_hook_handler(
    "k2_sample_guard",
    events=["pre_tool_use"],
    decisions=["deny", "none"],
    config_schema={"mode": ConfigKey("string", "strictest", ("off", "warn", "block"))},
)
def _sample_guard(ev: CanonicalEvent, ctx: HandlerContext) -> None:
    return None


def test_register_hook_handler_records_its_declaration() -> None:
    declaration = declaration_of(_sample_guard)

    assert declaration is registered_handlers()["k2_sample_guard"]
    assert getattr(_sample_guard, HANDLER_ATTR) is declaration
    assert declaration.events == {PRE}
    assert declaration.decisions == {Decision.DENY, Decision.NONE}
    assert declaration.config_schema["mode"].policy == "strictest"
    assert (declaration.module, declaration.fn) == (__name__, _sample_guard)


@pytest.mark.parametrize("name", ["GuardX", "guard-x", "a:b:c", ""])
def test_handler_names_must_be_snake_case(name: str) -> None:
    with pytest.raises(ValueError, match="snake_case"):
        register_hook_handler(name, events=["stop"], decisions=["none"])


def test_one_name_from_two_modules_is_refused(make_package: PackageFactory) -> None:
    make_package(
        "k2dup",
        init=(
            "from coding_agent_playbook.hook_runtime.dispatch.registry"
            " import register_hook_handler\n"
            "@register_hook_handler('k2_sample_guard', events=['stop'], decisions=['none'])\n"
            "def other(ev, ctx): return None\n"
        ),
    )

    with pytest.raises(ValueError, match="registered by"):
        importlib.import_module("k2dup")


@pytest.mark.parametrize(
    ("key", "value", "accepted"),
    [
        (ConfigKey("integer"), 3, True),
        (ConfigKey("integer"), True, False),
        (ConfigKey("number"), 1.5, True),
        (ConfigKey("list"), ["a"], True),
        (ConfigKey("table"), {"a": 1}, True),
        (ConfigKey("string", order=("warn", "block")), "off", False),
        (ConfigKey("boolean"), 0, False),
        (ConfigKey("regex"), ["^uv run\\b", {"id": "x", "regex": "x_[0-9]+"}], True),
        (ConfigKey("regex"), [], True),
        (ConfigKey("regex"), "^uv run\\b", False),  # a list of patterns, never one bare string
        (ConfigKey("regex"), [{"id": "x"}], False),
        (ConfigKey("regex"), [3], False),
    ],
)
def test_config_key_accepts_its_kind(key: ConfigKey, value: object, accepted: bool) -> None:
    assert key.accepts(value) is accepted


# --- resolution ---------------------------------------------------------------------------


_TWO_MODULES = {
    "k2pkg.alpha": (
        "from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler\n"
        "@register_hook_handler('k2_alpha', events=['pre_tool_use'], decisions=['deny'])\n"
        "def alpha(ev, ctx): return None\n"
    ),
    "k2pkg.beta": (
        "from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler\n"
        "@register_hook_handler('k2_beta', events=['stop'], decisions=['deny'])\n"
        "def beta(ev, ctx): return None\n"
    ),
}


def test_resolve_imports_only_modules_bound_to_the_event(
    tmp_path: Path, make_package: PackageFactory
) -> None:
    make_package("k2pkg")
    for name, source in _TWO_MODULES.items():
        make_package(name, init=source)
    repo = GuardRepo.create(tmp_path)
    alpha = hook_record("alpha-hook", handler={"kind": "builtin", "name": "k2_alpha"})
    beta = hook_record("beta-hook", events=["stop"], handler={"kind": "builtin", "name": "k2_beta"})
    cfg = _config(alpha, beta)
    modules = {"k2_alpha": "k2pkg.alpha", "k2_beta": "k2pkg.beta"}

    fn = resolve_handler(cfg.hooks["alpha-hook"], PRE, _ctx(cfg, repo, builtin_modules=modules))

    assert fn is sys.modules["k2pkg.alpha"].alpha
    assert "k2pkg.beta" not in sys.modules


def test_unknown_builtin_lists_the_known_handlers() -> None:
    with pytest.raises(HandlerResolutionError, match="known handlers: k2_alpha"):
        load_builtin("nope", modules={"k2_alpha": "k2pkg.alpha"})


def test_entry_point_record_imports_target_directly_without_importlib_metadata(
    tmp_path: Path, make_package: PackageFactory
) -> None:
    make_package("acme_k2ep", init="def guard(ev, ctx):\n    return None\n")
    importlib.import_module("acme_k2ep")
    root = str(Path(sys.modules["acme_k2ep"].__file__ or "").parent.parent)
    record = hook_record(
        "acme-guard",
        handler={"kind": "entry_point", "target": "acme_k2ep:guard", "dist": "acme-k2ep==1.0"},
    )
    repo = GuardRepo.create(tmp_path)
    cfg = _config(record, allow_code_from=["acme_k2ep"])

    fn = resolve_handler(cfg.hooks["acme-guard"], PRE, _ctx(cfg, repo))

    assert fn is sys.modules["acme_k2ep"].guard
    code = (
        f"import sys; sys.path.insert(0, {root!r}); "
        "from coding_agent_playbook.hook_runtime.dispatch.registry import _entry_point; "
        "_entry_point('acme_k2ep:guard', frozenset({'acme_k2ep'})); "
        "print('importlib.metadata' in sys.modules)"
    )
    assert run_python_probe(code) == "False"


def test_entry_point_outside_allow_code_from_is_untrusted(tmp_path: Path) -> None:
    record = hook_record(
        "acme-guard",
        handler={"kind": "entry_point", "target": "acme_rules.mod:guard", "dist": None},
    )
    cfg = _config(record, allow_code_from=["other_overlay"])

    result = resolve_handler(cfg.hooks["acme-guard"], PRE, _ctx(cfg, GuardRepo.create(tmp_path)))

    assert result == Untrusted("package 'acme_rules' is not in [hooks] allow_code_from")


# --- external handlers -----------------------------------------------------------------

_SCRIPT_REL = ".coding-agent-playbook/hooks/scripts/ext-sql/check.py"
_PYTHON = "/usr/bin/python3"


def _external_repo(tmp_path: Path) -> tuple[GuardRepo, dict[str, Any], HandlerApproval]:
    repo = GuardRepo.create(tmp_path)
    script = repo.root / _SCRIPT_REL
    script.parent.mkdir(parents=True)
    script.write_text("print('{}')\n", encoding="utf-8")
    sha = hashlib.sha256(script.read_bytes()).hexdigest()
    record = hook_record(
        "ext-sql",
        handler={"kind": "external", "argv": ["python", _SCRIPT_REL, "--strict"]},
        script_sha256=sha,
        source_package="acme_rules",
    )
    approval = HandlerApproval("acme_rules", "python", sha256_of_json(["--strict"]), sha)
    return repo, record, approval


def _external_deps(
    runtime_deps: Callable[..., RuntimeDeps], repo: GuardRepo, trust: FakeTrustStore, stdout: bytes
) -> RuntimeDeps:
    proc = FakeProc(programs={"python": _PYTHON})
    proc.script([_PYTHON], stdout=stdout)
    return runtime_deps(env=repo.env(), proc=proc, trust=trust)


def test_external_handler_needs_trust_and_matching_script_sha(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, record, approval = _external_repo(tmp_path)
    repo.install(record)
    verdict = b'{"decision": "deny", "reason": "PII column in SELECT"}'
    untrusted = _external_deps(runtime_deps, repo, FakeTrustStore(), verdict)
    trusted = _external_deps(runtime_deps, repo, FakeTrustStore({"ext-sql": approval}), verdict)

    skipped = run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), untrusted)
    denied = run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), trusted)

    assert untrusted.proc.calls == []  # type: ignore[attr-defined]
    assert "ext-sql skipped: not trusted" in skipped.stdout
    assert (denied.exit_code, denied.stderr) == (DENY_EXIT, "PII column in SELECT\n")
    (call,) = trusted.proc.calls  # type: ignore[attr-defined]
    assert call.argv == (_PYTHON, str(repo.root / _SCRIPT_REL), "--strict")
    assert call.cwd == str(repo.root)
    stdin = json.loads(call.input or b"")
    assert (stdin["schema"], stdin["event"], stdin["tool"]["name"]) == (
        EVENT_SCHEMA,
        "pre_tool_use",
        "Bash",
    )


def test_edited_script_copy_is_untrusted_even_with_an_approval(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, record, approval = _external_repo(tmp_path)
    repo.install(record)
    (repo.root / _SCRIPT_REL).write_text("import os; os.system('curl evil')\n", encoding="utf-8")
    deps = _external_deps(runtime_deps, repo, FakeTrustStore({"ext-sql": approval}), b"{}")

    wire = run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    assert deps.proc.calls == []  # type: ignore[attr-defined]
    assert "copied script differs from the approved one" in wire.stdout


@pytest.mark.parametrize(
    "stdout",
    [
        b'{"decision": "allow"}',
        b'{"decision": "deny", "updatedInput": {"command": "ls"}}',
        b'{"decision": "none", "permissionDecision": "allow"}',
        b"not json",
        b'["deny"]',
        b'{"decision": "context", "context": "one string"}',
    ],
)
def test_external_output_with_allow_or_updated_input_is_internal_error(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], stdout: bytes
) -> None:
    with pytest.raises(ExternalContractError):
        parse_external_output(stdout, hook_id="ext-sql")
    repo, record, approval = _external_repo(tmp_path)
    repo.install(record)
    deps = _external_deps(runtime_deps, repo, FakeTrustStore({"ext-sql": approval}), stdout)

    wire = run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    assert "Playbook guard ext-sql failed internally" in wire.stdout
    assert [line["decision"] for line in repo.decisions()] == ["degraded"]


def test_external_non_zero_exit_is_an_internal_error(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, record, approval = _external_repo(tmp_path)
    repo.install(record)
    proc = FakeProc(programs={"python": _PYTHON})
    proc.script([_PYTHON], stdout=b'{"decision": "none"}', returncode=1)
    deps = runtime_deps(env=repo.env(), proc=proc, trust=FakeTrustStore({"ext-sql": approval}))

    wire = run_event(PRE, Harness.CLAUDE_CODE, repo.payload(PRE, tool="Bash"), deps)

    assert "failed internally" in wire.stdout


def test_parse_external_output_keeps_the_contract_fields() -> None:
    result = parse_external_output(
        b'{"decision": "context", "context": ["a", "b"], "user_note": "n"}', hook_id="x"
    )

    assert (result.decision, result.context, result.user_note) == (
        Decision.CONTEXT,
        ("a", "b"),
        "n",
    )


# --- resolution errors and the lazy repo ports ---------------------------------------------


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        ({"kind": "entry_point", "target": "no_colon", "dist": None}, "is not 'module:attr'"),
        ({"kind": "entry_point", "target": "json:__version__", "dist": None}, "is not callable"),
        ({"kind": "entry_point", "target": "json.no_such_mod:x", "dist": None}, "cannot import"),
    ],
)
def test_broken_entry_point_targets_are_resolution_errors(
    tmp_path: Path, handler: dict[str, Any], message: str
) -> None:
    cfg = _config(hook_record("ep", handler=handler), allow_code_from=["json", "no_colon"])

    with pytest.raises(HandlerResolutionError, match=message):
        resolve_handler(cfg.hooks["ep"], PRE, _ctx(cfg, GuardRepo.create(tmp_path)))


_MUTATOR = """\
from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler


@register_hook_handler(
    "acme_k7_fixer", events=["post_tool_use"], decisions=["context"], mutates_edited_file=True
)
def fix(ev, ctx):
    return None
"""


def test_mutates_edited_file_is_refused_at_resolution_off_its_allowlist(
    tmp_path: Path, make_package: PackageFactory
) -> None:
    """The runtime backstop of validate's rule (specs/prK-hook-pack.md §E.3)."""
    make_package("acme_k7mut", init=_MUTATOR)
    target = {"kind": "entry_point", "target": "acme_k7mut:fix", "dist": None}
    entry = hook_record("acme-fix", events=["post_tool_use"], handler=target)
    builtin = {"kind": "builtin", "name": "ruff_post_edit"}
    misbound = hook_record("misbound", handler=builtin)
    cfg = _config(entry, misbound, allow_code_from=["acme_k7mut"])
    ctx = _ctx(cfg, GuardRepo.create(tmp_path))

    with pytest.raises(HandlerResolutionError, match="only the engine builtins"):
        resolve_handler(cfg.hooks["acme-fix"], EventName.POST_TOOL_USE, ctx)
    with pytest.raises(HandlerResolutionError, match="allowed on post_tool_use only"):
        resolve_handler(cfg.hooks["misbound"], PRE, ctx)


def test_event_without_a_bound_handler_is_a_resolution_error(tmp_path: Path) -> None:
    cfg = _config(hook_record("guard-a"))

    with pytest.raises(HandlerResolutionError, match="binds no handler to 'stop'"):
        resolve_handler(cfg.hooks["guard-a"], EventName.STOP, _ctx(cfg, GuardRepo.create(tmp_path)))


def test_lazy_git_builds_safe_git_only_when_first_used(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    from coding_agent_playbook.hook_runtime.dispatch.ports import LazyGit
    from coding_agent_playbook.hook_runtime.git.safe_git import SafeGit
    from tests.hook_runtime.fakes import FakeGit

    repo = GuardRepo.create(tmp_path)
    fake = FakeGit(head_tree_id="abc", head_blobs={"a.py": b"x"}, untracked=("n",))
    scripted = LazyGit(repo.repo, runtime_deps(git=fake), state=None, secret_paths=None)
    real = LazyGit(repo.repo, runtime_deps(), state=None, secret_paths=None)

    answers = (
        scripted.head_tree(),
        scripted.cat_head("a.py"),
        scripted.ls_untracked(),
        scripted.diff_added(),
        scripted.fingerprint(),
    )

    assert answers == ("abc", b"x", ("n",), (), None)
    assert [method for method, _ in fake.calls] == [
        "head_tree",
        "cat_head",
        "ls_untracked",
        "diff_added",
        "fingerprint",
    ]
    assert isinstance(real._port(), SafeGit)


def test_open_trust_store_refuses_a_store_inside_the_repo(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    from coding_agent_playbook.hook_runtime.dispatch.ports import open_trust_store
    from coding_agent_playbook.security.trust import TrustStore

    repo = GuardRepo.create(tmp_path)
    outside = runtime_deps(trust=None, home=str(tmp_path / "home"))
    inside = runtime_deps(trust=None, home=str(repo.root))

    assert isinstance(open_trust_store(repo.repo, outside), TrustStore)
    assert open_trust_store(repo.repo, inside) is None
