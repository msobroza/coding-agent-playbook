"""Loading ``guard_config.json`` and checking its lockfile digest (specs/prK-lifecycle-hooks.md §D.8).

The runtime reads only JSON on its hot path and trusts the file only when its
sha256 equals the lockfile's ``guard_config.json`` entry. The lockfile is TOML,
so its digest is cached in ``<state>/cfg-digest.json`` and ``tomllib`` is
loaded only when the lockfile's stat changes. Any problem is a ``ConfigFault``
for the failure policy, never an exception.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.hook_schema import HookMatcher
from coding_agent_playbook.hook_policy.resolved import ResolvedHandler, ResolvedHook
from coding_agent_playbook.hook_runtime.config.guard_config import (
    GUARD_CONFIG_REL,
    LOCKFILE_REL,
    ConfigFault,
    GuardConfig,
    load_guard_config,
)
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName, RepoInfo
from coding_agent_playbook.hook_runtime.paths import fold_key
from coding_agent_playbook.hook_runtime.policy import ENGINE_DEADLINE_CAP_MS
from coding_agent_playbook.hook_runtime.shell import ShellConfig
from coding_agent_playbook.hook_runtime.state import StateStore
from coding_agent_playbook.lockfile.model import Lockfile
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.config.lock_digest import TomlLoader


def _resolved_hook() -> ResolvedHook:
    return ResolvedHook(
        id="guard-generated-outputs",
        source_package="coding_agent_playbook",
        events=("pre_tool_use",),
        priority=10,
        matcher={"pre_tool_use": HookMatcher(tools=["edit", "write"], paths=["AGENTS.md", "*.MD"])},
        handlers={
            "pre_tool_use": ResolvedHandler(
                "builtin", name="guard_generated_outputs", config={"a": 1}
            )
        },
        decisions=("deny", "ask"),
        timeout=2.0,
        on_error={"pre_tool_use": "ask"},
        supports=("claude_code", "opencode"),
        mandatory=False,
        script_sha256=None,
    )


def _document(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 1,
        "engine_version": "0.1.0a0",
        "hooks": {"guard-generated-outputs": _resolved_hook().to_json()},
        "deadlines_ms": {"pre_tool_use": 2000},
        "unattended_ask": "warn",
        "logging": {"decisions": True, "audit": False, "audit_mode": ""},
        "shell": {"wrapper_prefixes": ["proxy"], "runner_wrappers": ["uv run"]},
        "path_classes": {"py": ["*.py"], "generated": ["AGENTS.md"]},
        "secret_path_globs": [".env*", "*.pem"],
        "allow_code_from": ["acme_rules"],
        "state_ttl_days": 3,
        "protected": {"output_dirs": [".claude/"]},
    }
    document.update(overrides)
    return document


def _canonical(document: Mapping[str, Any]) -> bytes:
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return (text + "\n").encode("ascii")


def _lockfile_text(sha256: str | None, *, extra: str = "") -> str:
    entry = (
        f'\n[[entries]]\npath = "{GUARD_CONFIG_REL}"\nsha256 = "{sha256}"\nbytes = 10\n'
        'kind = "runtime"\n'
        if sha256 is not None
        else ""
    )
    return (
        'schema_version = 2\nengine_version = "0.1.0a0"\nrendered_at = "2026-10-14T00:00:00Z"\n'
        f'{extra}\n[[entries]]\npath = "AGENTS.md"\nsha256 = "ab"\nbytes = 2\n{entry}'
    )


def _repo(tmp_path: Path) -> RepoInfo:
    root = Path(os.path.realpath(tmp_path))
    (root / ".git").mkdir(exist_ok=True)
    return RepoInfo(
        worktree_root=str(root),
        git_dir=str(root / ".git"),
        common_dir=str(root / ".git"),
        is_linked_worktree=False,
    )


def _install(
    repo: RepoInfo, document: Mapping[str, Any] | bytes, *, lock_sha: str | None = None
) -> bytes:
    """Write ``guard_config.json`` and a lockfile whose entry matches it (or ``lock_sha``)."""
    data = document if isinstance(document, bytes) else _canonical(document)
    path = Path(repo.worktree_root) / GUARD_CONFIG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest() if lock_sha is None else lock_sha
    (Path(repo.worktree_root) / LOCKFILE_REL).write_text(_lockfile_text(sha), encoding="utf-8")
    return data


class SpyToml:
    """A ``TomlLoader`` that counts its calls and parses with the real ``tomllib``."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, data: bytes) -> Mapping[str, Any]:
        self.calls += 1
        return tomllib.loads(data.decode("utf-8"))


def _load(repo: RepoInfo, **kwargs: Any) -> GuardConfig | ConfigFault:
    kwargs.setdefault("platform", "linux")
    kwargs.setdefault("home", "/home/dev")
    return load_guard_config(repo, StateStore.for_repo(repo), **kwargs)


# --- faults ----------------------------------------------------------------------------------


def test_missing_guard_config_is_config_fault(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    fault = _load(repo)

    assert isinstance(fault, ConfigFault)
    assert fault.kind == "missing"
    assert GUARD_CONFIG_REL in fault.detail


def test_sha_mismatch_with_lock_entry_is_config_fault(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document(), lock_sha="0" * 64)

    fault = _load(repo)

    assert isinstance(fault, ConfigFault)
    assert fault.kind == "digest_mismatch"


@pytest.mark.parametrize("lockfile", [None, "no-entry", "not-toml"])
def test_missing_lock_entry_is_config_fault(tmp_path: Path, lockfile: str | None) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document())
    lock = Path(repo.worktree_root) / LOCKFILE_REL
    if lockfile is None:
        lock.unlink()
    else:
        lock.write_text(_lockfile_text(None) if lockfile == "no-entry" else "[[[", encoding="utf-8")

    fault = _load(repo)

    assert isinstance(fault, ConfigFault)
    assert fault.kind == "no_lock_entry"


def test_newer_schema_version_is_config_fault(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document(schema_version=2))

    fault = _load(repo)

    assert isinstance(fault, ConfigFault)
    assert fault.kind == "schema_newer"
    assert fault.detail == "engine older than guard_config schema 2"


@pytest.mark.parametrize(
    ("override", "where"),
    [
        ({"hooks": []}, "hooks"),
        ({"schema_version": "1"}, "schema_version"),
        ({"unattended_ask": "maybe"}, "unattended_ask"),
        ({"deadlines_ms": {"pre_tool_use": "2s"}}, "deadlines_ms.pre_tool_use"),
        ({"deadlines_ms": {"PreToolUse": 1}}, "deadlines_ms"),
        ({"secret_path_globs": "*.pem"}, "secret_path_globs"),
        ({"path_classes": {"py": "*.py"}}, "path_classes.py"),
        ({"shell": {"wrapper_prefixes": [1]}}, "shell.wrapper_prefixes"),
        ({"state_ttl_days": 0}, "state_ttl_days"),
        ({"hooks": {"x": {"id": "x"}}}, "hooks.x"),
    ],
)
def test_malformed_config_is_a_fault_naming_the_value(
    tmp_path: Path, override: dict[str, Any], where: str
) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document(**override))

    fault = _load(repo)

    assert isinstance(fault, ConfigFault)
    assert fault.kind == "malformed"
    assert fault.detail.startswith(where)


@pytest.mark.parametrize(
    "data",
    [
        _canonical(_document(secret_path_globs=["[z-a].key"])),
        b"[" * 100_000 + b"]" * 100_000 + b"\n",
    ],
)
def test_invalid_glob_or_deep_nesting_is_a_fault_not_a_crash(tmp_path: Path, data: bytes) -> None:
    repo = _repo(tmp_path)
    _install(repo, data)

    fault = _load(repo)

    assert isinstance(fault, ConfigFault) and fault.kind == "malformed"


def test_non_json_or_oversized_config_is_a_fault(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, b"{not json\n")
    assert isinstance(fault := _load(repo), ConfigFault) and fault.kind == "malformed"

    _install(repo, b" " * (1024 * 1024 + 1))
    assert isinstance(fault := _load(repo), ConfigFault) and fault.kind == "unreadable"


# --- the parsed config ----------------------------------------------------------------------


def test_hook_records_parse_the_resolved_hook_to_json_schema(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data = _install(repo, _document())

    cfg = _load(repo)

    assert isinstance(cfg, GuardConfig)
    assert cfg.sha256 == hashlib.sha256(data).hexdigest()
    (record,) = cfg.hooks.values()
    assert record.id == "guard-generated-outputs"
    assert record.events == (EventName.PRE_TOOL_USE,)
    assert record.decisions == frozenset({Decision.DENY, Decision.ASK})
    assert record.timeout_ms == 2000
    assert record.on_error == {EventName.PRE_TOOL_USE: "ask"}
    assert record.supports == frozenset({"claude_code", "opencode"})
    assert (record.mandatory, record.script_sha256, record.priority) == (False, None, 10)
    handler = record.handlers[EventName.PRE_TOOL_USE]
    assert (handler.kind, handler.name, dict(handler.config)) == (
        "builtin",
        "guard_generated_outputs",
        {"a": 1},
    )
    matcher = record.matcher[EventName.PRE_TOOL_USE]
    assert matcher.tools == ("edit", "write")
    assert matcher.paths.matches("AGENTS.md") and not matcher.paths.matches("x.md")
    assert record.raw == _resolved_hook().to_json()


HOOK = "guard-generated-outputs"


def _with_record(change: Callable[[dict[str, Any]], object]) -> dict[str, Any]:
    record = _resolved_hook().to_json()
    change(record)
    return _document(hooks={HOOK: record})


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (
            {
                "kind": "entry_point",
                "target": "acme.rules:check",
                "dist": "acme==1.0",
                "config": {},
            },
            ("entry_point", None, "acme.rules:check", "acme==1.0", ()),
        ),
        (
            {"kind": "external", "argv": ["python", "scripts/a.py", "--x"], "config": {"k": 2}},
            ("external", None, None, None, ("python", "scripts/a.py", "--x")),
        ),
    ],
)
def test_entry_point_and_external_handlers_parse(
    tmp_path: Path, handler: dict[str, Any], expected: tuple[object, ...]
) -> None:
    repo = _repo(tmp_path)
    _install(repo, _with_record(lambda record: record["handlers"].update(pre_tool_use=handler)))

    cfg = _load(repo)

    assert isinstance(cfg, GuardConfig)
    spec = cfg.hooks[HOOK].handlers[EventName.PRE_TOOL_USE]
    assert (spec.kind, spec.name, spec.target, spec.dist, spec.argv) == expected


def test_on_error_is_clamped_per_event_at_load(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    def bind_stop(record: dict[str, Any]) -> None:
        record["events"].append("stop")
        record["on_error"]["stop"] = "ask"  # stop honours only "open" (§A.2)

    _install(repo, _with_record(bind_stop))

    cfg = _load(repo)

    assert isinstance(cfg, GuardConfig)
    assert dict(cfg.hooks[HOOK].on_error) == {EventName.PRE_TOOL_USE: "ask", EventName.STOP: "open"}


@pytest.mark.parametrize(
    ("change", "where"),
    [
        (lambda r: r.update(id="other"), f"hooks.{HOOK}.id"),
        (lambda r: r.update(decisions=["allow"]), f"hooks.{HOOK}.decisions"),
        (lambda r: r.update(events=["PreToolUse"]), f"hooks.{HOOK}.events"),
        (lambda r: r.update(timeout_ms=0), f"hooks.{HOOK}.timeout_ms"),
        (lambda r: r["handlers"]["pre_tool_use"].update(kind="http"), f"hooks.{HOOK}.handlers"),
        (lambda r: r["handlers"].update(pre_tool_use={"kind": "external", "argv": []}), "hooks."),
        (lambda r: r["on_error"].update(pre_tool_use="maybe"), f"hooks.{HOOK}.on_error"),
        (lambda r: r["matcher"].update(Stop={}), f"hooks.{HOOK}.matcher"),
        (lambda r: r.update(script_sha256=3), f"hooks.{HOOK}.script_sha256"),
    ],
)
def test_malformed_hook_records_are_faults(
    tmp_path: Path, change: Callable[[dict[str, Any]], object], where: str
) -> None:
    repo = _repo(tmp_path)
    _install(repo, _with_record(change))

    fault = _load(repo)

    assert isinstance(fault, ConfigFault) and fault.kind == "malformed"
    assert fault.detail.startswith(where)


def test_runtime_keys_and_pack_tables(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document())

    cfg = _load(repo)

    assert isinstance(cfg, GuardConfig)
    assert cfg.unattended_ask == "warn"
    assert cfg.deadlines_ms[EventName.PRE_TOOL_USE] == 2000
    assert cfg.deadlines_ms[EventName.STOP] == ENGINE_DEADLINE_CAP_MS[EventName.STOP]
    assert cfg.shell == ShellConfig(wrapper_prefixes=("proxy",), runner_wrappers=("uv run",))
    assert (cfg.logging.decisions, cfg.logging.audit) == (True, False)
    assert cfg.path_classes["py"].matches("src/a.py")
    assert cfg.secret_paths.matches("deploy/.env.prod")
    assert cfg.allow_code_from == frozenset({"acme_rules"})
    assert cfg.state_ttl_days == 3
    assert cfg.tables["protected"] == {"output_dirs": [".claude/"]}
    with pytest.raises(TypeError):
        cfg.tables["protected"] = {}  # type: ignore[index]


def test_optional_keys_default_to_the_safe_engine_values(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, {"schema_version": 1, "hooks": {}})

    cfg = _load(repo)

    assert isinstance(cfg, GuardConfig)
    assert cfg.unattended_ask == "deny"
    assert dict(cfg.deadlines_ms) == dict(ENGINE_DEADLINE_CAP_MS)
    assert cfg.secret_paths.patterns == SECRET_PATH_GLOBS
    assert cfg.shell == ShellConfig()
    assert cfg.state_ttl_days == 7
    assert cfg.allow_code_from == frozenset()
    assert not cfg.logging.decisions


def test_pattern_keys_folded_at_load_on_darwin(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document(secret_path_globs=[".ENV*"], path_classes={"docs": ["Docs/**"]}))

    darwin = _load(repo, platform="darwin")
    linux = _load(repo, platform="linux")

    assert isinstance(darwin, GuardConfig) and isinstance(linux, GuardConfig)
    assert darwin.secret_paths.matches(fold_key("x/.env.prod", "darwin"))
    assert darwin.path_classes["docs"].matches(fold_key("DOCS/a.md", "darwin"))
    assert not linux.secret_paths.matches("x/.env.prod")
    matcher = darwin.hooks["guard-generated-outputs"].matcher[EventName.PRE_TOOL_USE]
    assert matcher.paths.matches(fold_key("agents.md", "darwin"))


# --- the digest cache ------------------------------------------------------------------------


def test_lockfile_reparsed_only_when_stat_changes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document())
    spy = SpyToml()

    assert isinstance(_load(repo, load_toml=spy), GuardConfig)
    assert isinstance(_load(repo, load_toml=spy), GuardConfig)
    assert spy.calls == 1  # the second load used <state>/cfg-digest.json
    cache = StateStore.for_repo(repo).read_json("cfg-digest.json")
    assert set(cache) == {"lock_size", "lock_mtime_ns", "lock_ino", "guard_config_sha256"}

    lock = Path(repo.worktree_root) / LOCKFILE_REL
    lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert isinstance(_load(repo, load_toml=spy), GuardConfig)
    assert spy.calls == 2

    assert isinstance(_load(repo, load_toml=spy, refresh_digest=True), GuardConfig)
    assert spy.calls == 3  # session_start refreshes whatever the stat says


def test_a_poisoned_cache_entry_for_another_stat_is_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document())
    store = StateStore.for_repo(repo)
    store.write_json(
        "cfg-digest.json",
        {"lock_size": 1, "lock_mtime_ns": 1, "lock_ino": 1, "guard_config_sha256": "0" * 64},
    )

    assert isinstance(_load(repo), GuardConfig)


def test_stateless_store_parses_the_lockfile_every_time(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document())
    spy = SpyToml()
    stateless = StateStore(Path(repo.git_dir) / "playbook-hooks", uid=os.getuid() + 1)

    for _ in range(2):
        cfg = load_guard_config(repo, stateless, platform="linux", home=None, load_toml=spy)
        assert isinstance(cfg, GuardConfig)
    assert spy.calls == 2


@pytest.mark.parametrize(
    "document",
    [
        {"entries": [{"path": GUARD_CONFIG_REL, "sha256": "aa", "bytes": 1, "kind": "runtime"}]},
        {"entries": [{"path": "AGENTS.md", "sha256": "bb", "bytes": 1}]},
        {"entries": []},
        {},
        {
            "entries": [
                {"path": "AGENTS.md", "sha256": "bb", "bytes": 1},
                {"path": GUARD_CONFIG_REL, "sha256": "cc", "bytes": 1, "kind": "runtime"},
                {"path": GUARD_CONFIG_REL, "sha256": "dd", "bytes": 1, "kind": "runtime"},
            ]
        },
    ],
)
def test_lock_entry_lookup_matches_lockfile_module(document: dict[str, Any]) -> None:
    from coding_agent_playbook.hook_runtime.config.lock_digest import lock_entry_sha256

    header = {"schema_version": 2, "engine_version": "0.1.0a0", "rendered_at": "t"}
    entry = Lockfile.from_dict({**header, **document}).find(GUARD_CONFIG_REL)

    assert lock_entry_sha256(document, GUARD_CONFIG_REL) == (entry.sha256 if entry else None)


@pytest.mark.parametrize(
    "document",
    [
        {"entries": "oops"},
        {"entries": ["x"]},
        {"entries": [{"path": GUARD_CONFIG_REL, "sha256": 3}]},
    ],
)
def test_malformed_lock_entries_give_no_digest(document: dict[str, Any]) -> None:
    from coding_agent_playbook.hook_runtime.config.lock_digest import lock_entry_sha256

    assert lock_entry_sha256(document, GUARD_CONFIG_REL) is None


def test_config_module_never_imports_tomllib_or_the_lockfile_module() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hook_runtime.config.guard_config")

    assert "tomllib" not in loaded
    assert engine_module("coding_agent_playbook.lockfile") not in loaded
    hook_policy = engine_module("coding_agent_playbook.hook_policy")
    assert not [m for m in loaded if m.startswith(hook_policy)]


def test_toml_loader_protocol_accepts_the_spy() -> None:
    loader: TomlLoader = SpyToml()
    assert loader(b"a = 1\n") == {"a": 1}


def test_config_loads_without_a_state_store(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _install(repo, _document())

    assert isinstance(load_guard_config(repo, None, platform="linux", home=None), GuardConfig)
