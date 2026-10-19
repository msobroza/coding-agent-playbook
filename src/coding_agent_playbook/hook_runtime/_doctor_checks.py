"""The environment checks of ``playbook-hook doctor`` (specs/prK-lifecycle-hooks.md §D.9, §C.2.7).

Each check reads, never writes: a missing state root is reported, not
created (the first hook event creates it). Severity is ``ok``, ``warning``
(worth knowing, but nothing this worktree's hooks need is missing: exit 0),
``degraded`` (hooks run, with a gap: stateless mode, a changed tool, an
unapproved external handler) or ``broken`` (hooks cannot run as synced: no
pin, a pin that cannot import the engine, a ``guard_config.json`` the runtime
refuses). The OpenCode checks live in ``_doctor_opencode``; registration
canaries through the harness argv are not run yet.

A ``wrappers`` row appears only when ``PLAYBOOK_HOOK_WRAPPER_PREFIXES`` is set:
``ok`` lists the prefixes the dispatcher will strip, ``warning`` names an entry
it refuses (it would hide a guarded command) or a value a settings-file
``env`` sets (ignored, like an escape hatch).
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime._ports import open_trust_store
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, load_guard_config
from coding_agent_playbook.hook_runtime.config.pin import (
    INTERPRETER_PIN,
    MACHINE_PINS,
    is_ephemeral,
    parse_machine_pins,
)
from coding_agent_playbook.hook_runtime.escape import (
    WRAPPER_PREFIXES_VAR,
    read_escape_hatches,
    settings_files,
)
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME
from coding_agent_playbook.hook_runtime.wrapper_policy import hidden_program

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.config.guard_config import ConfigFault
    from coding_agent_playbook.hook_runtime.config.pin import MachinePins
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import RepoInfo

__all__ = ["SEVERITY", "Check", "Severity", "environment_checks", "read_regular_file"]

type Severity = Literal["ok", "warning", "degraded", "broken"]
#: Severity -> doctor's exit code: 0 healthy (a warning included), 1 degraded, 2 broken.
SEVERITY: Final = {"ok": 0, "warning": 0, "degraded": 1, "broken": 2}
MIN_PYTHON: Final = (3, 12)
PROBE_TIMEOUT_S: Final = 30.0
_MAX_READ: Final = 1024 * 1024
#: Run by the pinned interpreter exactly as the launcher runs it (``-I``).
PROBE: Final = (
    "import json, sys\n"
    "import coding_agent_playbook.hook_runtime\n"
    "from coding_agent_playbook import __version__\n"
    "print(json.dumps({'version': list(sys.version_info[:2]), "
    "'isolated': sys.flags.isolated, 'engine': __version__}))\n"
)


@dataclass(frozen=True, slots=True)
class Check:
    """One doctor finding: what was checked, how bad, and what to do."""

    name: str
    severity: Severity
    detail: str


def environment_checks(repo: RepoInfo, deps: RuntimeDeps) -> list[Check]:
    """Every environment check of ``repo``'s worktree, in report order.

    Example::

        >>> [c.severity for c in environment_checks(repo, deps)]  # doctest: +SKIP
        ['ok', 'ok', 'ok', 'ok', 'ok']
    """
    state_root = Path(repo.git_dir) / STATE_DIR_NAME
    cfg = load_guard_config(repo, None, platform=deps.platform, home=deps.home)
    return [
        _config_check(cfg),
        _pin_check(state_root, deps, cfg),
        _state_check(state_root),
        _machine_check(state_root),
        _trust_check(repo, deps, cfg),
        *_wrapper_checks(repo, deps),
    ]


def _config_check(cfg: GuardConfig | ConfigFault) -> Check:
    if not isinstance(cfg, GuardConfig):
        return Check("guard_config", "broken", f"{cfg.kind}: {cfg.detail}; run playbook sync")
    detail = f"digest matches the lockfile; schema {cfg.schema_version}, {len(cfg.hooks)} hook(s)"
    return Check("guard_config", "ok", detail)


def _pin_check(state_root: Path, deps: RuntimeDeps, cfg: GuardConfig | ConfigFault) -> Check:
    pin = _first_line(state_root / INTERPRETER_PIN)
    if pin is None:
        return Check("pin", "broken", "no interpreter pin: hooks are inactive; run playbook sync")
    if not (os.path.isfile(pin) and os.access(pin, os.X_OK)):
        return Check("pin", "broken", f"pin {pin!r} is not an executable file; run doctor --repin")
    facts = _probe(pin, deps)
    if isinstance(facts, str):
        return Check("pin", "broken", f"{pin}: {facts}")
    return _pin_facts(pin, facts, cfg)


def _probe(pin: str, deps: RuntimeDeps) -> dict[str, object] | str:
    """The pinned interpreter's version, ``-I`` flag and engine version, or why it failed."""
    try:
        result = deps.proc.run(
            [pin, "-I", "-c", PROBE], timeout=PROBE_TIMEOUT_S, env=dict(deps.env)
        )
    except Exception as exc:  # a timeout or a missing program: the pin is unusable
        return f"cannot run: {type(exc).__name__}"
    if not result.ok:
        return "cannot import coding_agent_playbook.hook_runtime"
    try:
        facts = json.loads(result.stdout.decode("utf-8").strip().splitlines()[-1])
    except (ValueError, IndexError, UnicodeDecodeError):
        return "unexpected probe output"
    return facts if isinstance(facts, dict) else "unexpected probe output"


def _pin_facts(pin: str, facts: dict[str, object], cfg: GuardConfig | ConfigFault) -> Check:
    version = facts.get("version")
    shown = ".".join(str(part) for part in version) if isinstance(version, list) else "?"
    if not isinstance(version, list) or tuple(version) < MIN_PYTHON:
        return Check("pin", "broken", f"{pin} is Python {shown}; the engine needs >= 3.12")
    if facts.get("isolated") != 1:
        return Check("pin", "broken", f"{pin} did not run isolated (-I)")
    engine = facts.get("engine")
    if isinstance(cfg, GuardConfig) and cfg.engine_version and engine != cfg.engine_version:
        detail = f"pinned engine {engine} differs from guard_config's {cfg.engine_version}"
        return Check("pin", "degraded", f"{detail}; run playbook sync")
    if is_ephemeral(pin):
        return Check("pin", "degraded", f"{pin} is ephemeral; run doctor --repin <stable python>")
    return Check("pin", "ok", f"{pin} (Python {shown}, isolated, engine {engine})")


def _state_check(state_root: Path, *, uid: Callable[[], int] = os.getuid) -> Check:
    try:
        info = os.lstat(state_root)
    except FileNotFoundError:
        return Check("state", "degraded", "no state root yet (the first hook event creates it)")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return Check("state", "degraded", "state root is not a real directory: hooks run stateless")
    if info.st_uid != uid():
        return Check("state", "degraded", f"state root is owned by uid {info.st_uid}: stateless")
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077:
        return Check("state", "degraded", f"state root mode is {mode:o}, not 700")
    return Check("state", "ok", f"{state_root} (700, owned by you)")


def _machine_check(state_root: Path) -> Check:
    path = state_root / MACHINE_PINS
    if not path.is_file():
        return Check("machine.json", "degraded", "no tool pins: run playbook sync in this worktree")
    pins = _pins(path)
    if pins is None:
        return Check("machine.json", "degraded", "machine.json is malformed; run playbook sync")
    changed = sorted(name for name, pin in pins.tools.items() if not pin.unchanged())
    if changed:
        detail = f"tool(s) changed since sync: {', '.join(changed)}; their stages are skipped"
        return Check("machine.json", "degraded", detail)
    return Check("machine.json", "ok", f"{len(pins.tools)} tool pin(s) match")


def _trust_check(repo: RepoInfo, deps: RuntimeDeps, cfg: GuardConfig | ConfigFault) -> Check:
    if not isinstance(cfg, GuardConfig):
        return Check("trust", "ok", "no guard_config to check")
    external = sorted(
        record.id
        for record in cfg.hooks.values()
        if any(spec.kind == "external" for spec in record.handlers.values())
    )
    if not external:
        return Check("trust", "ok", "no external handlers")
    store = open_trust_store(repo, deps)
    if store is None:
        return Check("trust", "degraded", "the trust store is unusable; external handlers skip")
    from coding_agent_playbook.hook_runtime._external import approval_of

    missing = [h for h in external if not store.allows_handler(h, approval_of(cfg.hooks[h]))]
    if missing:
        detail = f"not approved on this machine (skipped): {', '.join(missing)}"
        return Check("trust", "degraded", detail)
    return Check("trust", "ok", f"{len(external)} external handler(s) approved")


def _wrapper_checks(repo: RepoInfo, deps: RuntimeDeps) -> list[Check]:
    """``PLAYBOOK_HOOK_WRAPPER_PREFIXES`` read as the dispatcher reads it; no row when unset."""
    value = deps.env.get(WRAPPER_PREFIXES_VAR)
    hatches = read_escape_hatches(
        {} if value is None else {WRAPPER_PREFIXES_VAR: value},
        settings_files=lambda: settings_files(
            repo, project_dir=repo.worktree_root, env=deps.env, home=deps.home
        ),
    )
    if WRAPPER_PREFIXES_VAR in hatches.via_settings_env:
        detail = "is set in a settings file env and is ignored; export it in the shell that "
        return [Check("wrappers", "warning", f"{WRAPPER_PREFIXES_VAR} {detail}launches the agent")]
    kept = ", ".join(repr(prefix) for prefix in hatches.wrapper_prefixes)
    if hatches.rejected_wrappers:
        ignored = ", ".join(
            f"{prefix!r} (it would hide {hidden_program(prefix)!r} from every guard)"
            for prefix in hatches.rejected_wrappers
        )
        detail = f"ignored {ignored}; kept {kept or 'none'}"
        return [Check("wrappers", "warning", f"{WRAPPER_PREFIXES_VAR}: {detail}")]
    if not kept:
        return []
    return [Check("wrappers", "ok", f"{WRAPPER_PREFIXES_VAR} adds wrapper prefixes: {kept}")]


def _first_line(path: Path) -> str | None:
    """The first line of a small regular file (read only, symlinks refused), or ``None``."""
    data = read_regular_file(path)
    lines = data.decode("utf-8", "replace").splitlines() if data else []
    return lines[0].strip() or None if lines else None


def _pins(path: Path) -> MachinePins | None:
    data = read_regular_file(path)
    try:
        document = json.loads(data or b"")
    except ValueError:
        return None
    return parse_machine_pins(document) if isinstance(document, dict) else None


def read_regular_file(path: Path) -> bytes | None:
    """The bytes of a regular file of at most 1 MiB (``path`` itself no symlink), else ``None``.

    Example::

        >>> read_regular_file(Path("/no/such/file")) is None
        True
    """
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_READ:
            return None
        return path.read_bytes()
    except OSError:
        return None
