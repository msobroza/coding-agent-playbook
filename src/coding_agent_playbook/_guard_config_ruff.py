"""Sync-time ruff tables of the §E.3 post-edit pipeline (specs/prK-hook-pack.md §E.3, OQ-37).

Two halves, split by the machine-independence lock (§D.8.3):

- ``guard_config.json``'s ``ruff`` table comes **only** from the repo's own
  ruff config (``.ruff.toml`` > ``ruff.toml`` > ``pyproject.toml``'s
  ``[tool.ruff]``, ruff's precedence): the project's explicit ``select`` /
  ``ignore`` and ``safe_fix_select`` = ``{I, UP}`` ∩ that selection, the only
  rules post-edit-ruff-format may fix (no second style source). Ruff's
  *default* selection is left implicit (``default_select``): it changed in
  ruff 0.17, so listing it would make the committed file differ by machine;
- the per-machine half: :func:`probe_ruff_rules` asks the **pinned** ruff
  which candidate codes it knows (``ruff rule --all --output-format json``,
  or one ``ruff rule <code>`` each when that fails, OQ-37), once per ruff
  signature (cached under the git dir), and :func:`ruff_drop_codes` turns the
  answer into ``machine.json`` ``tools.ruff.drop``.

Config inheritance (``extend = "..."``) is not followed: a project that
inherits its selection gets no safe fixes, never wrong ones.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.hook_runtime._ruff import intersect_selectors, selector_matches
from coding_agent_playbook.hook_runtime.config.pin import tool_signature
from coding_agent_playbook.hook_runtime.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.state import StateUnavailable

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.config.pin import Signature
    from coding_agent_playbook.hook_runtime.deps import ProcPort
    from coding_agent_playbook.hook_runtime.state import StateStore
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = [
    "RUFF_CONFIG_FILES",
    "SAFE_FIX_ALLOWLIST",
    "RuffSelection",
    "RuleCache",
    "RuleProbe",
    "probe_ruff_rules",
    "read_project_ruff_selection",
    "ruff_candidate_codes",
    "ruff_drop_codes",
    "ruff_table",
]

#: The rules M1 may ever fix: import sorting and pyupgrade (§E.3).
SAFE_FIX_ALLOWLIST: Final = ("I", "UP")
#: Ruff's own precedence when one directory holds several config files.
RUFF_CONFIG_FILES: Final = (".ruff.toml", "ruff.toml", "pyproject.toml")
#: ``ruff rule --all`` prints ~1 MB of JSON; generous, it runs once per ruff signature.
PROBE_TIMEOUT_S: Final = 10.0
#: The probe cache beside ``machine.json`` under ``<git_dir>/playbook-hooks``.
RULE_CACHE_DOCUMENT: Final = "ruff-rules.json"

type RuleStatus = Literal["stable", "preview", "unknown"]


# --- the project's selection (guard_config.json) -------------------------------------------


@dataclass(frozen=True)
class RuffSelection:
    """The project's explicit ruff selection; ``default_select`` when it sets no ``select``.

    Example: ``RuffSelection(select=("E", "I"), ignore=("E501",), default_select=False)``.
    """

    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    default_select: bool = True


def read_project_ruff_selection(repo_root: Path) -> RuffSelection:
    """The selection of the ruff config ruff itself would read at ``repo_root``.

    A ``pyproject.toml`` without ``[tool.ruff]`` is not a ruff config; an
    unreadable or malformed file counts as no config (ruff's defaults).

    Example::

        >>> read_project_ruff_selection(Path("/no/such/repo"))
        RuffSelection(select=(), ignore=(), default_select=True)
    """
    for name in RUFF_CONFIG_FILES:
        document = _load_toml(repo_root / name)
        table = _ruff_table_of(document, pyproject=name == "pyproject.toml")
        if table is not None:
            return _selection(table)
    return RuffSelection()


def _load_toml(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def _ruff_table_of(document: dict[str, Any] | None, *, pyproject: bool) -> dict[str, Any] | None:
    if document is None or not pyproject:
        return document
    tool = document.get("tool")
    ruff = tool.get("ruff") if isinstance(tool, dict) else None
    return ruff if isinstance(ruff, dict) else None


def _selection(table: dict[str, Any]) -> RuffSelection:
    """``[lint]`` keys first, the deprecated top-level ones as a fallback (ruff's own order)."""
    lint = table.get("lint")
    lint = lint if isinstance(lint, dict) else {}
    select = _strings(lint, "select") if "select" in lint else _strings(table, "select")
    explicit = "select" in lint or "select" in table
    extend = [*_strings(lint, "extend-select"), *_strings(table, "extend-select")]
    ignore = [
        *_strings(lint, "ignore"),
        *_strings(table, "ignore"),
        *_strings(lint, "extend-ignore"),
        *_strings(table, "extend-ignore"),
    ]
    return RuffSelection(
        select=tuple(sorted({*select, *extend})),
        ignore=tuple(sorted(set(ignore))),
        default_select=not explicit,
    )


def _strings(table: Mapping[str, Any], key: str) -> list[str]:
    value = table.get(key)
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def ruff_table(selection: RuffSelection) -> dict[str, Any]:
    """``guard_config.json``'s ``ruff`` table: machine-independent, from the repo alone.

    ``safe_fix_ignore`` re-applies the project's ignores inside the safe-fix
    prefixes, because M1's CLI ``--select`` resets the config's ``ignore``.

    Example::

        >>> ruff_table(RuffSelection(("E", "I", "UP"), ("UP007",), False))["safe_fix_select"]
        ['I', 'UP']
    """
    selected = intersect_selectors(SAFE_FIX_ALLOWLIST, selection.select)
    safe = [s for s in selected if not any(selector_matches(g, s) for g in selection.ignore)]
    safe_ignore = [g for g in selection.ignore if any(selector_matches(s, g) for s in safe)]
    return {
        "default_select": selection.default_select,
        "project_select": list(selection.select),
        "project_ignore": list(selection.ignore),
        "safe_fix_select": safe,
        "safe_fix_ignore": safe_ignore,
    }


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


# --- the pinned ruff's rule set (machine.json) -----------------------------------------------


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
