"""The pinned ruff's rule set, probed at sync for ``machine.json`` (specs/prK-hook-pack.md §E.3, OQ-37).

The per-machine half of the §E.3 ruff tables (the committed half is
``_tables_ruff``): :func:`probe_ruff_rules` asks the **pinned** ruff which
candidate codes it knows (``ruff rule --all --output-format json``, or one
``ruff rule <code>`` each when that fails, OQ-37), once per ruff signature
(cached under the git dir), and :func:`ruff_drop_codes` turns the answer into
``machine.json`` ``tools.ruff.drop``. :func:`ruff_candidate_codes` lists what to
ask: every rule code an enabled hook adds. Never at hook time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.hook_runtime.config.pin import tool_signature
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config.pin import Signature
    from coding_agent_playbook.hook_runtime.dispatch.deps import ProcPort
    from coding_agent_playbook.hook_runtime.state.store import StateStore
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = [
    "RuleCache",
    "RuleProbe",
    "probe_ruff_rules",
    "ruff_candidate_codes",
    "ruff_drop_codes",
]

#: ``ruff rule --all`` prints ~1 MB of JSON; generous, it runs once per ruff signature.
PROBE_TIMEOUT_S: Final = 10.0
#: The probe cache beside ``machine.json`` under ``<git_dir>/playbook-hooks``.
RULE_CACHE_DOCUMENT: Final = "ruff-rules.json"

type RuleStatus = Literal["stable", "preview", "unknown"]


def ruff_candidate_codes(hooks: Iterable[ResolvedHook]) -> list[str]:
    """Every rule code an enabled hook asks D1 to add (its builtin's ``lint_codes`` config).

    These are what :func:`probe_ruff_rules` checks against the pinned ruff.

    Example::

        >>> ruff_candidate_codes([])
        []
    """
    codes: set[str] = set()
    for hook in hooks:
        for handler in hook.handlers.values():
            if handler.kind == "builtin":
                codes.update(_listed_codes(handler.config.get("lint_codes")))
    return sorted(codes)


def _listed_codes(value: object) -> list[str]:
    if isinstance(value, dict):
        value = value.get("warn")
    return [c for c in value if isinstance(c, str)] if isinstance(value, list) else []


@dataclass(frozen=True)
class RuleProbe:
    """What a ruff build said about rule codes; ``complete`` when it listed every rule.

    Example::

        >>> RuleProbe(True, {"F401": "stable"}).status("NOPE1")
        'unknown'
    """

    complete: bool
    statuses: Mapping[str, RuleStatus] = field(default_factory=dict)

    def status(self, code: str) -> RuleStatus | None:
        """The code's status; ``None`` when this probe never asked about it."""
        found = self.statuses.get(code)
        if found is None and self.complete:
            return "unknown"
        return found

    def covers(self, codes: Iterable[str]) -> bool:
        """Whether every code in ``codes`` has an answer."""
        return all(self.status(code) is not None for code in codes)


@dataclass(frozen=True)
class RuleCache:
    """The probe of one ruff signature, kept in the per-worktree state root.

    Example: ``RuleCache(state_store(start=str(repo_root)))``.
    """

    store: StateStore

    def load(self, sig: Signature) -> RuleProbe | None:
        """The probe recorded for ``sig``, or ``None`` (none yet, another ruff, unreadable)."""
        try:
            document = self.store.read_json(RULE_CACHE_DOCUMENT)
        except StateUnavailable:
            return None
        codes = document.get("codes")
        if document.get("sig") != list(sig) or not isinstance(codes, dict):
            return None
        statuses = {c: s for c, s in codes.items() if s in ("stable", "preview", "unknown")}
        return RuleProbe(document.get("complete") is True, MappingProxyType(statuses))

    def save(self, sig: Signature, probe: RuleProbe) -> None:
        """Record ``probe`` for ``sig``; a stateless root keeps nothing."""
        document = {"sig": list(sig), "complete": probe.complete, "codes": dict(probe.statuses)}
        try:
            self.store.write_json(RULE_CACHE_DOCUMENT, document)
        except StateUnavailable:
            return


def probe_ruff_rules(
    argv: Sequence[str], codes: Iterable[str], *, proc: ProcPort, cache: RuleCache | None = None
) -> RuleProbe:
    """Ask the ruff at ``argv`` about ``codes``: one ``rule --all``, else one ``rule <code>`` each.

    Runs at sync only, never at hook time; a cached probe of the same ruff
    signature that answers every code spawns nothing.

    Example::

        >>> probe_ruff_rules(["/v/bin/ruff"], ["B006"], proc=SubprocessProc()).status("B006")  # doctest: +SKIP
        'stable'
    """
    wanted = sorted(set(codes))
    sig = tool_signature(argv[0]) if argv else None
    cached = cache.load(sig) if cache is not None and sig is not None else None
    if cached is not None and cached.covers(wanted):
        return cached
    probe = _rule_all(argv, proc) or _per_code(argv, wanted, proc, cached)
    if cache is not None and sig is not None:
        cache.save(sig, probe)
    return probe


def ruff_drop_codes(codes: Iterable[str], probe: RuleProbe) -> list[str]:
    """The codes D1 must leave out: unknown to this ruff, preview-only, or never answered.

    Example::

        >>> ruff_drop_codes(["B006", "DOC201"], RuleProbe(True, {"B006": "stable"}))
        ['DOC201']
    """
    return sorted(code for code in set(codes) if probe.status(code) != "stable")


def _rule_all(argv: Sequence[str], proc: ProcPort) -> RuleProbe | None:
    """``ruff rule --all --output-format json``; ``None`` when this ruff cannot answer it."""
    rows = _json_of(proc, [*argv, "rule", "--all", "--output-format", "json"])
    if not isinstance(rows, list):
        return None
    statuses = {
        row["code"]: _status_of(row)
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("code"), str)
    }
    return RuleProbe(True, MappingProxyType(statuses)) if statuses else None


def _per_code(
    argv: Sequence[str], wanted: Sequence[str], proc: ProcPort, base: RuleProbe | None
) -> RuleProbe:
    """OQ-37's fallback: one ``ruff rule <code>`` per code no earlier probe answered."""
    statuses: dict[str, RuleStatus] = dict(base.statuses) if base is not None else {}
    for code in wanted:
        if code not in statuses and (status := _rule_one(argv, code, proc)) is not None:
            statuses[code] = status
    return RuleProbe(False, MappingProxyType(statuses))


def _rule_one(argv: Sequence[str], code: str, proc: ProcPort) -> RuleStatus | None:
    """A known code exits 0 (JSON or, on an old ruff, markdown); an unknown one exits 2."""
    try:
        done = proc.run([*argv, "rule", code, "--output-format", "json"], timeout=PROBE_TIMEOUT_S)
    except (ProcTimeout, OSError):
        return None  # no answer: dropped this time, asked again at the next sync
    if not done.ok:
        return "unknown"
    try:
        row = json.loads(done.stdout)
    except ValueError:
        return "stable"
    return _status_of(row) if isinstance(row, dict) else "stable"


def _json_of(proc: ProcPort, argv: Sequence[str]) -> object:
    try:
        done = proc.run(argv, timeout=PROBE_TIMEOUT_S)
    except (ProcTimeout, OSError):
        return None
    if not done.ok:
        return None
    try:
        return json.loads(done.stdout)
    except ValueError:
        return None


def _status_of(row: Mapping[str, Any]) -> RuleStatus:
    """``status`` is ``{"Stable"|"Preview"|"Removed": {...}}`` (0.17) or absent (older ruff)."""
    status = row.get("status")
    name = next(iter(status), "") if isinstance(status, dict) else str(status or "")
    if name == "Removed":
        return "unknown"
    if row.get("preview") is True or name == "Preview":
        return "preview"
    return "stable"
