"""The pack tables of ``guard_config.json``, read through one typed interface (specs/prK-hook-pack.md §E.0.5).

``guard_config.json`` is the contract between sync, which renders it, and the
hook runtime, which reads it. ``guard_config`` parses the runtime keys; every
other top-level key is a pack table, and :class:`GuardTables` owns the reader
side of each one: its name, its shape and its default. A missing or malformed
table reads as its default and never raises, because ``load_guard_config``
already vouched for the bytes; a table with rows is parsed on first use and kept.

The dispatcher loads this module on every event, so it imports only the stdlib:
callers compile the globs it returns and pass in the defaults that live with
their hook (``NOTEBOOK_MAX_BYTES``, ``FIXTURE_GLOBS``, the secret exemptions).
Only a ``stop_gate`` table without a usable budget imports ``stop.stages``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

__all__ = [
    "APPLICABILITY",
    "AUTO_SYNC",
    "DEFAULT_MAX_BLOCKS",
    "EVAL",
    "FACTS",
    "MAX_BLOCKS_RANGE",
    "NETWORK",
    "NOTEBOOKS",
    "PRECOMMIT",
    "PROMPTS",
    "PROTECTED",
    "RUFF",
    "SECRET_GLOB_EXEMPT_TABLE",
    "SECRET_PATH_EXEMPT_TABLE",
    "SECRET_RULES",
    "STOP_GATE",
    "GuardTables",
    "ProtectedTable",
    "RuffTable",
    "SecretPattern",
    "StageRecord",
    "StopGate",
    "VerifyCommand",
]

#: guard_config.json's pack tables (specs/prK-hook-pack.md §E.0.5): one spelling for both sides.
STOP_GATE: Final = "stop_gate"
PROMPTS: Final = "prompts"
NOTEBOOKS: Final = "notebooks"
EVAL: Final = "eval"
PROTECTED: Final = "protected"
PRECOMMIT: Final = "precommit"
AUTO_SYNC: Final = "auto_sync"
FACTS: Final = "facts"
APPLICABILITY: Final = "applicability"
NETWORK: Final = "network"
RUFF: Final = "ruff"
#: The §E.4 secret tables; the suffix keeps two names apart from ``security.patterns``'
#: ``SECRET_PATH_EXEMPT`` and ``SECRET_GLOB_EXEMPT``, the defaults rendered into them.
SECRET_RULES: Final = "secret_rules"
SECRET_PATH_EXEMPT_TABLE: Final = "secret_path_exempt"
SECRET_GLOB_EXEMPT_TABLE: Final = "secret_glob_exempt"
#: ``[hooks.stop-ci-parity-gate] max_blocks`` default and range (§B.1), for the Stop
#: coordinator and subagent-stop-verify alike.
DEFAULT_MAX_BLOCKS: Final = 2
MAX_BLOCKS_RANGE: Final = (1, 8)


@dataclass(frozen=True, slots=True, kw_only=True)
class StageRecord:
    """One well-formed ``stop_gate.stages`` row: a ``str`` name, the rest optional.

    Example::

        >>> GuardTables({"stop_gate": {"stages": [{"name": "lint", "timeout_s": True}]}}
        ...             ).stop_gate().stages[0].timeout_s is None
        True
    """

    name: str
    owner: str | None
    tool: str | None  # a non-empty str, else None
    args: tuple[str, ...] | None  # ``str(arg)`` of a list, else None
    timeout_s: float | None  # an int or float > 0 that is not a bool, else None


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyCommand:
    """One ``stop_gate.verify_commands`` row with a non-empty str ``id`` and a list ``argv``.

    Example: ``VerifyCommand(id="tests", argv=("pytest",))``.
    """

    id: str
    argv: tuple[str, ...]  # ``str(word)`` of each listed word


@dataclass(frozen=True, slots=True, kw_only=True)
class StopGate:
    """``guard_config.stop_gate``, parsed once.

    Example::

        >>> GuardTables({"stop_gate": {"max_blocks": 99}}).stop_gate().max_blocks
        8
    """

    budget_s: float  # positive, else stop.stages.DEFAULT_BUDGET_S
    max_blocks: int  # clamped into MAX_BLOCKS_RANGE, else DEFAULT_MAX_BLOCKS
    stage_rows: tuple[Any, ...]  # the rendered rows verbatim: what an approval hashes
    stages: tuple[StageRecord, ...]
    verify_commands: tuple[VerifyCommand, ...]
    claim_patterns: tuple[str, ...]  # the str items only


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtectedTable:
    """``guard_config.protected``: the hook artifacts, the layer resource roots, the lockfile ids.

    Example: ``tables.protected().resource_roots == ("pkg:coding_agent_playbook/resources",)``.
    """

    hook_artifacts: tuple[str, ...]
    resource_roots: tuple[str, ...]
    artifact_ids: frozenset[str]  # the non-empty ``entries[].artifact_id``


@dataclass(frozen=True, slots=True, kw_only=True)
class RuffTable:
    """``guard_config.ruff``: the project's ruff selection and the safe-fix subset sync derived.

    Example: ``tables.ruff().safe_fix_select == ("I", "UP")`` for a project selecting E, I, UP.
    """

    project_select: tuple[str, ...]
    project_ignore: tuple[str, ...]
    safe_fix_select: tuple[str, ...]
    safe_fix_ignore: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SecretPattern:
    """One ``secret_rules.extra_patterns`` row: an overlay's secret regex, not compiled yet.

    Example: ``SecretPattern(id="acme", regex="ACME-[0-9]{8}", label="Acme token")``.
    """

    id: str
    regex: str
    label: str  # a non-empty str, else the id


class GuardTables(Mapping[str, Any]):
    """The pack tables of a trusted guard_config.json: still a read-only mapping, plus typed reads.

    Each accessor of a table with rows parses it on first use and caches it, and a single
    value is read on each call; a missing or malformed table reads as its default, never
    raises (``load_guard_config`` already vouched for the bytes). The mapping half stays
    for out-of-tree handlers.

    Example::

        >>> GuardTables({"precommit": {"playbook_hook_ids": ["playbook-validate", 3]}}
        ...             ).precommit_hook_ids()
        ('playbook-validate',)
    """

    def __init__(self, raw: Mapping[str, object]) -> None:
        self._raw: Mapping[str, Any] = MappingProxyType(dict(raw))

    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    def __repr__(self) -> str:
        return f"GuardTables({dict(self._raw)!r})"

    def stop_gate(self) -> StopGate:
        """``stop_gate``: the Stop budget, the block budget, the stage rows and the claims.

        Example: ``GatePolicy.from_gate(cfg.tables.stop_gate())``.
        """
        return self._stop_gate

    def prompt_output_contract(self, slash: str) -> tuple[str, ...]:
        """The non-empty str ``output_contract`` patterns of prompt ``slash`` (``()`` without).

        Example: ``cfg.tables.prompt_output_contract("review")[0].startswith("(?im)")``.
        """
        return self._prompt_contracts.get(slash, ())

    def prompts_with_output_contract(self) -> tuple[str, ...]:
        """The slashes whose prompt carries at least one ``output_contract`` pattern.

        Example: ``"review" in cfg.tables.prompts_with_output_contract()``.
        """
        return tuple(slash for slash, contract in self._prompt_contracts.items() if contract)

    def notebook_max_bytes(self, default: int) -> int:
        """``notebooks.max_bytes`` when a positive int (never a bool), else ``default``.

        Example: ``cfg.tables.notebook_max_bytes(NOTEBOOK_MAX_BYTES) == 5 * 1024 * 1024``.
        """
        value = self._table(NOTEBOOKS).get("max_bytes")
        return value if type(value) is int and value > 0 else default

    def eval_fixture_globs(self, default: Sequence[str]) -> tuple[str, ...]:
        """``eval.fixture_globs`` when a list of str (an empty one included), else ``default``.

        Example: ``cfg.tables.eval_fixture_globs(FIXTURE_GLOBS) == ("**/eval_samples/*/setup/**",)``.
        """
        globs = self._table(EVAL).get("fixture_globs")
        if isinstance(globs, list) and all(isinstance(glob, str) for glob in globs):
            return tuple(globs)
        return tuple(default)

    def protected(self) -> ProtectedTable:
        """``protected``'s hook artifacts, resource roots and lockfile artifact ids.

        Example: ``"pkg:coding_agent_playbook/resources" in cfg.tables.protected().resource_roots``.
        """
        return self._protected

    def precommit_hook_ids(self) -> tuple[str, ...]:
        """``precommit.playbook_hook_ids``: its non-empty str items; empty when absent or malformed.

        Example: ``cfg.tables.precommit_hook_ids() == ("playbook-metrics", "playbook-validate")``.
        """
        return _non_empty_str_items(self._table(PRECOMMIT).get("playbook_hook_ids"))

    def auto_sync(self) -> bool:
        """Whether ``[hooks] auto_sync`` is on: ``auto_sync`` is exactly ``true``.

        Example: ``GuardTables({"auto_sync": True}).auto_sync() is True``.
        """
        return self._raw.get(AUTO_SYNC) is True

    def facts(self) -> Mapping[str, object] | None:
        """The ``facts`` table, the decoded JSON object itself; ``None`` when it is not one.

        Example: ``cfg.tables.facts()["package_manager"] == "uv"``.
        """
        facts = self._raw.get(FACTS)
        return facts if isinstance(facts, dict) else None

    def applicability(self) -> tuple[Mapping[str, object], ...]:
        """The ``applicability`` rows that are JSON objects, in rendered order.

        Example: ``cfg.tables.applicability()[0]["kind"] == "rule"``.
        """
        return self._applicability

    def network_mode(self) -> str | None:
        """``network.mode`` when a non-empty str, else ``None``.

        Example: ``GuardTables({"network": {"mode": "enforce"}}).network_mode() == "enforce"``.
        """
        mode = self._table(NETWORK).get("mode")
        return mode if isinstance(mode, str) and mode else None

    def ruff(self) -> RuffTable:
        """``ruff``: the str items of its four selector lists.

        Example: ``cfg.tables.ruff().project_ignore == ("UP007",)``.
        """
        return self._ruff

    def secret_path_exempt(self, default: Sequence[str]) -> tuple[str, ...]:
        """``secret_path_exempt``'s non-empty str items when it is a list, else ``default``.

        Example: ``cfg.tables.secret_path_exempt(SECRET_PATH_EXEMPT)[0] == ".env.example"``.
        """
        value = self._raw.get(SECRET_PATH_EXEMPT_TABLE)
        return _non_empty_str_items(value) if isinstance(value, list) else tuple(default)

    def secret_glob_exempt(
        self, default: Mapping[str, tuple[str, ...]]
    ) -> Mapping[str, tuple[str, ...]]:
        """``secret_glob_exempt`` (glob -> its exemption globs) when a table, else ``default``.

        Example: ``cfg.tables.secret_glob_exempt(SECRET_GLOB_EXEMPT)["*credentials*"][0]``.
        """
        return default if self._glob_exempt is None else self._glob_exempt

    def secret_patterns(self) -> tuple[SecretPattern, ...]:
        """``secret_rules.extra_patterns``: the rows with a str ``id`` and a str ``regex``.

        Example: ``cfg.tables.secret_patterns()[0].label == "Acme token"``.
        """
        return self._secret_patterns

    def _table(self, name: str) -> Mapping[str, object]:
        """Top-level table ``name`` when it is a JSON object, else an empty one."""
        table = self._raw.get(name)
        return table if isinstance(table, dict) else {}

    @cached_property
    def _stop_gate(self) -> StopGate:
        table = self._table(STOP_GATE)
        rows = _json_list(table.get("stages"))
        return StopGate(
            budget_s=_budget(table.get("budget_s")),
            max_blocks=_max_blocks(table.get("max_blocks")),
            stage_rows=tuple(rows),
            stages=tuple(record for row in rows if (record := _stage_record(row)) is not None),
            verify_commands=tuple(
                command
                for row in _json_list(table.get("verify_commands"))
                if (command := _verify_command(row)) is not None
            ),
            claim_patterns=_str_items(table.get("claim_patterns")),
        )

    @cached_property
    def _prompt_contracts(self) -> Mapping[str, tuple[str, ...]]:
        rows = self._table(PROMPTS).items()
        return {
            slash: _non_empty_str_items(row.get("output_contract"))
            for slash, row in rows
            if isinstance(row, dict)
        }

    @cached_property
    def _protected(self) -> ProtectedTable:
        table = self._table(PROTECTED)
        entries = (entry for entry in _json_list(table.get("entries")) if isinstance(entry, dict))
        return ProtectedTable(
            hook_artifacts=_str_items(table.get("hook_artifacts")),
            resource_roots=_str_items(table.get("resource_roots")),
            artifact_ids=frozenset(
                _non_empty_str_items([entry.get("artifact_id") for entry in entries])
            ),
        )

    @cached_property
    def _applicability(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            row for row in _json_list(self._raw.get(APPLICABILITY)) if isinstance(row, dict)
        )

    @cached_property
    def _ruff(self) -> RuffTable:
        table = self._table(RUFF)
        return RuffTable(
            project_select=_str_items(table.get("project_select")),
            project_ignore=_str_items(table.get("project_ignore")),
            safe_fix_select=_str_items(table.get("safe_fix_select")),
            safe_fix_ignore=_str_items(table.get("safe_fix_ignore")),
        )

    @cached_property
    def _glob_exempt(self) -> Mapping[str, tuple[str, ...]] | None:
        table = self._raw.get(SECRET_GLOB_EXEMPT_TABLE)
        if not isinstance(table, dict):
            return None
        return MappingProxyType(
            {
                glob: _non_empty_str_items(globs)
                for glob, globs in table.items()
                if isinstance(glob, str)
            }
        )

    @cached_property
    def _secret_patterns(self) -> tuple[SecretPattern, ...]:
        rows = _json_list(self._table(SECRET_RULES).get("extra_patterns"))
        return tuple(pattern for row in rows if (pattern := _secret_pattern(row)) is not None)


def _json_list(value: object) -> list[Any]:
    """``value`` when it is a JSON list, else an empty one."""
    return value if isinstance(value, list) else []


def _str_items(value: object) -> tuple[str, ...]:
    """The str items of a list (``""`` kept); anything but a list has none."""
    return tuple(item for item in _json_list(value) if isinstance(item, str))


def _non_empty_str_items(value: object) -> tuple[str, ...]:
    """The non-empty str items of a list; anything but a list has none."""
    return tuple(item for item in _str_items(value) if item)


def _budget(value: object) -> float:
    """A positive ``budget_s``, else the default Stop budget (§D.5.2 rule 1)."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        # Imported here: sync always renders a budget, so a dispatch never loads stop/.
        from coding_agent_playbook.hook_runtime.stop.stages import DEFAULT_BUDGET_S

        return DEFAULT_BUDGET_S
    return float(value)


def _max_blocks(value: object) -> int:
    """An int ``max_blocks`` (never a bool) clamped into its range, else the default."""
    if type(value) is not int:
        return DEFAULT_MAX_BLOCKS
    low, high = MAX_BLOCKS_RANGE
    return min(high, max(low, value))


def _positive_seconds(value: object) -> float | None:
    """An int or float above zero (never a bool) as seconds, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not value > 0:
        return None
    return float(value)


def _stage_record(row: object) -> StageRecord | None:
    if not isinstance(row, dict) or not isinstance(name := row.get("name"), str):
        return None
    owner, tool, args = row.get("owner"), row.get("tool"), row.get("args")
    return StageRecord(
        name=name,
        owner=owner if isinstance(owner, str) else None,
        tool=tool if isinstance(tool, str) and tool else None,
        args=tuple(str(arg) for arg in args) if isinstance(args, list) else None,
        timeout_s=_positive_seconds(row.get("timeout_s")),
    )


def _verify_command(row: object) -> VerifyCommand | None:
    if not isinstance(row, dict):
        return None
    verify_id, argv = row.get("id"), row.get("argv")
    if not isinstance(verify_id, str) or not verify_id or not isinstance(argv, list):
        return None
    return VerifyCommand(id=verify_id, argv=tuple(str(word) for word in argv))


def _secret_pattern(row: object) -> SecretPattern | None:
    if not isinstance(row, dict):
        return None
    pattern_id, regex, label = row.get("id"), row.get("regex"), row.get("label")
    if not isinstance(pattern_id, str) or not isinstance(regex, str):
        return None
    return SecretPattern(
        id=pattern_id, regex=regex, label=label if isinstance(label, str) and label else pattern_id
    )
