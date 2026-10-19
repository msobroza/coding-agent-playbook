"""skill-nudge: name the skill that covers a file the first time a session edits it (specs/prS-skills-context.md 8.5.3).

Default, ``post_tool_use`` on ``edit``, ``write`` and ``notebook_edit`` (the ml-data
members glob ``**/*.ipynb``, spec 12.2; OpenCode has no notebook tool, so
``playbook check`` labels the hook degraded there). Scoped rules are delivered
as skill references (ADR 0001), so nothing in always-loaded context carries
their text: this hook points the agent at the skill to load. Sync derives
``config["skills"]``, one ``{"id", "globs"}`` row per written skill, from the
member rules' globs (``_guard_config_skills``); no ``CONFIG_SCHEMA`` key exists,
so no layer can set it. Each written path's ``NormalizedPath.key`` is matched
against every row with the same glob grammar every hook uses; a path outside
the repository is skipped (its key is absolute, and ``**/*.py`` would match it).

One line per matching skill, ``Conventions for this file: skill <id>.``, at
most 200 characters. Once per skill per session is combine's job: the result
carries ``dedupe_key``, and combine burns ``ctx:skill-nudge:<sha1(line)[:8]>``
only for a line it shows, so a line a cap cuts shows on the next matching edit.
A stateless store would answer every ``once`` with True and repeat the line on
every edit, so the hook is silent there. A missing or malformed table yields no
line; ``on_error: open``. Imports ``globs``, ``decision`` and ``registry`` only
(the hot path, specs/prK-lifecycle-hooks.md §D.1).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, TypeGuard

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.globs import compile_globs
from coding_agent_playbook.hook_runtime.registry import register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.globs import GlobSet
    from coding_agent_playbook.hook_runtime.registry import ConfigKey, HandlerContext

__all__ = [
    "CONFIG_SCHEMA",
    "SKILL_NUDGE_LINE",
    "SKILL_NUDGE_MAX_CHARS",
    "matching_skills",
    "nudge_line",
    "skill_glob_table",
    "skill_nudge",
]

SKILL_NUDGE_LINE: Final = "Conventions for this file: skill {skill_id}."
SKILL_NUDGE_MAX_CHARS: Final = 200
#: ``skills`` is not a key: sync derives it from the member rules (spec 8.5.2).
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {}
#: Combine's per-session ``once`` namespace; the line text makes the key per skill.
_DEDUPE_KEY: Final = "skill-nudge"


@register_hook_handler(
    "skill_nudge",
    events=["post_tool_use"],
    decisions=["context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def skill_nudge(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """One line per skill whose member-rule globs match a file this edit wrote (D16).

    Silent without a tool call, when the state root is unusable (nothing could
    dedupe the line), or when no written path is in the repository and matches
    a skill. Combine shows each line at most once per session.

    Example::

        >>> skill_nudge(edit_of_src_app_py, ctx).context  # doctest: +SKIP
        ('Conventions for this file: skill python-coding.',)
    """
    if ev.tool is None or not ctx.session.store.usable:
        return None
    keys = [path.key for path in ev.tool.write_paths if path.same_repo]
    lines = tuple(nudge_line(skill_id) for skill_id in matching_skills(ctx, keys))
    if not lines:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT,
        hook_id=ctx.hook.id,
        rule_id="skill_nudge",
        context=lines,
        dedupe_key=_DEDUPE_KEY,
    )


def matching_skills(ctx: HandlerContext, keys: Sequence[str]) -> list[str]:
    """The skill ids, in config order, whose globs match any of ``keys``.

    Example: ``matching_skills(ctx, ["tests/test_app.py"])`` -> ``["python-testing"]``
    for a table of ``python-testing: tests/**/*.py`` alone.
    """
    if not keys:
        return []
    table = skill_glob_table(ctx.config, platform=ctx.platform, home=ctx.home)
    return [skill_id for skill_id, globs in table if any(globs.matches(key) for key in keys)]


def skill_glob_table(
    config: Mapping[str, object], *, platform: str, home: str | None
) -> tuple[tuple[str, GlobSet], ...]:
    """``config["skills"]`` compiled; a malformed row or one whose globs do not compile is skipped.

    Example::

        >>> [row[0] for row in skill_glob_table(
        ...     {"skills": [{"id": "python-testing", "globs": ["tests/**/*.py"]}, {"id": 3}]},
        ...     platform="linux", home=None)]
        ['python-testing']
    """
    rows = config.get("skills")
    if not isinstance(rows, list):
        return ()
    compiled = (_compiled_row(row, platform, home) for row in rows)
    return tuple(row for row in compiled if row is not None)


def nudge_line(skill_id: str) -> str:
    """``Conventions for this file: skill <id>.``, clipped to 200 characters.

    Example::

        >>> nudge_line("python-coding")
        'Conventions for this file: skill python-coding.'
    """
    return SKILL_NUDGE_LINE.format(skill_id=skill_id)[:SKILL_NUDGE_MAX_CHARS]


def _compiled_row(row: object, platform: str, home: str | None) -> tuple[str, GlobSet] | None:
    """One ``{"id": str, "globs": [str, ...]}`` row compiled, else ``None`` (fail-open)."""
    if not isinstance(row, dict):
        return None
    skill_id, globs = row.get("id"), row.get("globs")
    if not isinstance(skill_id, str) or not skill_id or not _is_glob_list(globs):
        return None
    try:
        return skill_id, compile_globs(globs, platform=platform, home=home)
    except re.error:  # a hand-edited class such as ``[z-a]``: skip the row, never fail the edit
        return None


def _is_glob_list(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and bool(value) and all(isinstance(g, str) for g in value)
