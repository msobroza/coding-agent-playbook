"""sensitive-data-read-guard: keep raw data and notebook outputs unread (prK-hook-pack.md §E.5).

An overlay-tier mechanism: the engine ships it inert (``tier: overlay``,
``mode: off``, no globs) and a regulated overlay activates it with its data
globs. ``pre_tool_use`` on Read, Grep, Glob and NotebookEdit (a boundary) and
on the Bash readers of ``_data_reads`` (a speed bump: the sandbox ``denyRead``
binds only when managed settings enforce it). Path-based only: it never reads
CSV or parquet content.

- ``allow_globs`` (fixtures, synthetic data, tests) exempt a path first.
- A ``deny_globs`` match (``data/raw/**``, ``*.parquet``...) -> ask.
- A ``*.csv`` larger than ``csv_max_sample_bytes`` (one ``stat``) -> ask.
- A notebook read (not a NotebookEdit: editing a cell shows no outputs):
  ``stat`` first; over ``guard_config.notebooks.max_bytes`` -> ask without
  parsing; else ask when any code cell keeps outputs (they may embed rows).
- ``mode: enforce`` turns every ask into a deny.

The paths are ``PathPolicy`` keys, as for secrets-path-guard: case-folded on
darwin/win32, judged by the resolved path and, for a symlink, by its
spelling too. A hard link outside the globs is judged by its own name: the
secret guard's inode index covers secrets only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.event import ToolClass
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers._shared.targets import shell_target
from coding_agent_playbook.hook_runtime.handlers.safety._data_reads import (
    is_pattern,
    read_candidates,
)
from coding_agent_playbook.hook_runtime.handlers.safety._secret_policy import spelled
from coding_agent_playbook.hook_runtime.judges.notebook_check import (
    NOTEBOOK_MAX_BYTES,
    NotebookLimits,
    Oversized,
    check_cells,
    read_notebook,
)
from coding_agent_playbook.security.files import user_home
from coding_agent_playbook.security.paths import PathPolicy

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

__all__ = ["CONFIG_SCHEMA", "DEFAULT_CSV_MAX_SAMPLE_BYTES", "MODES", "sensitive_read_guard"]

#: Weakest first: the ``strictest`` order of ``mode``.
MODES: Final = ("off", "ask", "enforce")
DEFAULT_CSV_MAX_SAMPLE_BYTES: Final = 64 * 1024
#: Deny globs are a deny table (``extend``); the exemptions and the size threshold
#: loosen the guard (``relax``: ignored from the consumer when the hook is mandatory).
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "mode": ConfigKey("string", "strictest", MODES),
    "deny_globs": ConfigKey("list", "extend"),
    "allow_globs": ConfigKey("list", "relax"),
    "csv_max_sample_bytes": ConfigKey("integer", "relax"),
}
_SEARCH_GLOB_KEYS: Final[Mapping[str, str]] = {"Glob": "pattern", "Grep": "glob"}
_NO_SCOPED_EXEMPTIONS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({})
_NOTEBOOK_RULES: Final = frozenset({"notebook_size", "notebook_outputs"})
#: A stand-in child name: a search root is raw data when what it reads below is.
_CHILD: Final = "_"
_MIB: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Hit:
    """One judged read: its rule id, the name the agent used, and the first reason line."""

    rule: str
    shown: str
    line: str


@dataclass(frozen=True, slots=True)
class _DataPolicy:
    """The overlay's globs and size thresholds, applied to one event's paths."""

    deny: PathPolicy
    allow: PathPolicy
    csv_cap: int
    notebook_cap: int
    home: str
    platform: str

    @classmethod
    def of(cls, ctx: HandlerContext, config: HookConfig) -> _DataPolicy:
        allow = config.strings("allow_globs", blanks="drop_empty")
        deny = config.strings("deny_globs", blanks="drop_empty")
        exempt = _NO_SCOPED_EXEMPTIONS
        return cls(
            deny=PathPolicy(deny=deny, allow=allow, glob_exempt=exempt, mode="ask"),
            allow=PathPolicy(deny=allow, allow=(), glob_exempt=exempt, mode="ask"),
            csv_cap=config.integer("csv_max_sample_bytes", DEFAULT_CSV_MAX_SAMPLE_BYTES, minimum=1),
            notebook_cap=ctx.cfg.tables.notebook_max_bytes(NOTEBOOK_MAX_BYTES),
            home=ctx.home or user_home(),
            platform=ctx.platform,
        )

    def pattern_hit(self, pattern: str, *, shown: str | None = None) -> _Hit | None:
        """A glob the agent passed (Glob ``pattern``, ``cat data/raw/*.csv``) naming raw data."""
        if not self.deny.matches(pattern, home=self.home, platform=self.platform):
            return None
        return _Hit("raw_data", shown or pattern, _raw_line(shown or pattern))

    def path_hit(
        self, path: NormalizedPath, *, notebooks: bool, directory: bool = False
    ) -> _Hit | None:
        """The verdict on one normalized path, or ``None`` when it may be read.

        ``directory``: a search root, judged as well by a child it would read
        (``data/raw`` is under ``data/raw/**``, which spares the directory itself).
        """
        names = [path.key, spelled(path)] if path.is_symlink else [path.key]
        if directory:
            names += [f"{name.rstrip('/')}/{_CHILD}" for name in names]
        shown = spelled(path)
        if any(self.deny.matches(n, home=self.home, platform=self.platform) for n in names):
            return _Hit("raw_data", shown, _raw_line(shown))
        if not path.exists or self.allow.matches(path.key, home=self.home, platform=self.platform):
            return None
        suffix = os.path.splitext(path.key.lower())[1]
        if suffix == ".csv":
            return self._csv_hit(path, shown)
        if suffix == ".ipynb" and notebooks:
            return self._notebook_hit(path, shown)
        return None

    def _csv_hit(self, path: NormalizedPath, shown: str) -> _Hit | None:
        try:
            size = os.stat(path.realpath).st_size
        except OSError:
            return None
        if size <= self.csv_cap:
            return None
        line = (
            f"{quote_data(shown)} is a {size}-byte CSV, over the {self.csv_cap}-byte sample "
            "limit: it may hold customer records."
        )
        return _Hit("csv_size", shown, line)

    def _notebook_hit(self, path: NormalizedPath, shown: str) -> _Hit | None:
        found = read_notebook(path.realpath, NotebookLimits(max_bytes=self.notebook_cap))
        if isinstance(found, Oversized):
            line = (
                f"{quote_data(shown)} is over {_size(self.notebook_cap)} and was not parsed: "
                "its outputs may embed customer rows."
            )
            return _Hit("notebook_size", shown, line)
        if found is None or not check_cells(found, None):
            return None
        line = f"{quote_data(shown)} keeps cell outputs, which may embed customer rows."
        return _Hit("notebook_outputs", shown, line)


@register_hook_handler(
    "sensitive_read_guard",
    events=["pre_tool_use"],
    decisions=["ask", "deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def sensitive_read_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Ask (deny in enforce mode) before raw data or notebook outputs are read; inert when off.

    Example::

        >>> sensitive_read_guard(read_of("data/raw/customers.csv"), ctx).decision
        ... # doctest: +SKIP
        <Decision.ASK: 'ask'>
    """
    config = HookConfig(ctx.config, CONFIG_SCHEMA)
    mode = config.choice("mode", "off")
    tool = ev.tool
    if mode not in MODES[1:] or tool is None:
        return None
    policy = _DataPolicy.of(ctx, config)
    hits = _shell_hits(ev, ctx, policy) if tool.tool_class is ToolClass.SHELL else None
    found = next(hits if hits is not None else _file_hits(tool, policy), None)
    if found is None:
        return None
    enforce = mode == "enforce"
    return HandlerResult(
        decision=Decision.DENY if enforce else Decision.ASK,
        hook_id=ctx.hook.id,
        rule_id=found.rule,
        reason=_reason(found, enforce=enforce),
    )


def _file_hits(tool: ToolCall, policy: _DataPolicy) -> Iterator[_Hit]:
    notebooks = tool.tool_class is not ToolClass.NOTEBOOK_EDIT
    search = tool.tool_class is ToolClass.SEARCH
    for path in tool.paths:
        hit = policy.path_hit(path, notebooks=notebooks, directory=search)
        if hit is not None:
            yield hit
    key = _SEARCH_GLOB_KEYS.get(tool.name)
    pattern = None if key is None else tool.raw_input.get(key)
    if isinstance(pattern, str) and pattern:
        hit = policy.pattern_hit(pattern)
        if hit is not None:
            yield hit


def _shell_hits(ev: CanonicalEvent, ctx: HandlerContext, policy: _DataPolicy) -> Iterator[_Hit]:
    """Each reader word of every segment that names raw data (an existing file, or a glob)."""
    command = ev.tool.command if ev.tool is not None else None
    for segment in () if command is None else command.segments:
        for word in read_candidates(segment):
            path = shell_target(word, segment, ev, ctx)  # a glob too: its key follows ``cd``
            if is_pattern(word):
                hit = policy.pattern_hit(path.key, shown=word)
            else:
                hit = policy.path_hit(path, notebooks=True) if path.exists else None
            if hit is not None:
                yield hit


def _reason(hit: _Hit, *, enforce: bool) -> str:
    if hit.rule in _NOTEBOOK_RULES:
        advice = "Read it with outputs stripped"
    else:
        advice = "Work from a fixture or synthetic sample instead"
    if enforce:
        return f"Blocked: {hit.line}\n{advice}."
    return f"{hit.line}\n{advice}, or confirm with the user."


def _raw_line(shown: str) -> str:
    return f"{quote_data(shown)} is raw data under this repository's data policy."


def _size(count: int) -> str:
    return f"{count // _MIB} MiB" if count >= _MIB and count % _MIB == 0 else f"{count} bytes"
