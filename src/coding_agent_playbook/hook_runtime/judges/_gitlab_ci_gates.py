"""gate_weakening's GitLab CI rule: jobs, script items and includes that a change drops (specs/prF-forge-adapter.md §10.3).

Patterns only: the hook runtime never imports YAML (Q54), so a CI file is read
line by line. Its column-0 keys open top-level blocks; a key that is not a
global keyword and not hidden (``.name``) is a job. The rule compares the file
before and after the change, as multisets, so a job, ``script:`` /
``before_script:`` / ``after_script:`` item or ``include:`` entry only counts
as removed when it is not re-added anywhere in the same file (a move is fine):

- ``gitlab-ci-job-removed``: a job is gone (its own items are not reported again);
- ``gitlab-ci-script-removed``: a script item is gone;
- ``gitlab-ci-include-removed``: a ``local`` / ``template`` / ``component`` /
  ``project`` / ``remote`` / ``file`` entry, or a plain string entry, is gone;
- ``playbook-ci-job-loosened``: an existing ``playbook-ci`` job gains
  ``allow_failure`` (other than false), ``when: manual``, ``when: never`` or
  ``when: on_failure`` (Q52; ``on_failure`` skips it whenever the pipeline passes).

Items compare without a trailing `` # comment`` (outside quotes) and outer
quotes, and a flow list ``[a, b]`` as its items, so adding a reason comment or
reformatting a list is no removal. Known limits of line patterns: a job written
on one line (``lint: {script: [ruff]}``) shows no items, and a ``playbook-ci``
job made optional through ``extends:`` or a YAML anchor is not seen.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.judges._gate_weakening_files import FileWeakening
from coding_agent_playbook.hook_runtime.judges._yaml_lines import unquoted, without_comment

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

__all__ = ["PLAYBOOK_CI_JOB", "gitlab_ci_weakenings"]

#: The job the README recipe names; making it optional switches the gate off (Q52).
PLAYBOOK_CI_JOB: Final = "playbook-ci"
#: Top-level keys that are not jobs: the global keywords, the header's ``spec``,
#: and the deprecated globals GitLab still reads as defaults (docs: CI/CD YAML syntax).
_NOT_JOBS: Final = frozenset(
    {"default", "include", "stages", "variables", "workflow", "spec"}
    | {"image", "services", "cache", "before_script", "after_script"}
)
#: Top-level blocks that hold no script: every non-job key but ``default`` and the scripts.
_NO_SCRIPTS: Final = _NOT_JOBS - {"default", "before_script", "after_script"}
_TOP_SCRIPTS: Final = frozenset({"before_script", "after_script"})
_INCLUDE: Final = "include"
#: A column-0 key ends at the first ``:`` followed by a blank, so ``test:unit:`` is one key.
_TOP_KEY = re.compile(r"""^("[^"]*"|'[^']*'|[^\s#'"\-][^#]*?)[ \t]*:(?:[ \t]|$)(.*)""")
_SCRIPT_KEY = re.compile(r"^([ \t]+)(?:before_|after_)?script[ \t]*:(.*)$")
_ITEM = re.compile(r"^([ \t]*)-[ \t]+(.*)$")
_INCLUDE_KEY = re.compile(
    r"^[ \t]*(?:-[ \t]+)?(local|template|component|project|remote|file)[ \t]*:[ \t]*(.*)$"
)
_MAPPING = re.compile(r"""^[^\s"'][^:]*:(?:[ \t]|$)""")
#: Include sub-keys whose nested lines are conditions or values, never entries.
_INCLUDE_NESTED = re.compile(r"^[ \t]*(?:-[ \t]+)?(?:rules|inputs)[ \t]*:")
#: YAML 1.1, which GitLab reads, also spells false ``False``, ``no`` or ``off``.
_LOOSENING = re.compile(
    r"^[ \t]*(?:-[ \t]+)?(?:allow_failure[ \t]*:(?![ \t]*(?i:false|no|off)\b)"
    r"|when[ \t]*:[ \t]*[\"']?(?:manual|never|on_failure)\b)"
)
_BLOCK_SCALAR = re.compile(r"^[|>][+-]?[0-9]?$")


@dataclass(frozen=True, slots=True)
class _Block:
    """One top-level key (unquoted) and the lines up to the next one."""

    key: str
    inline: str
    lines: tuple[str, ...]

    @property
    def is_job(self) -> bool:
        return self.key not in _NOT_JOBS and not self.key.startswith((".", "<<"))


def gitlab_ci_weakenings(path: str, before: str | None, after: str | None) -> list[FileWeakening]:
    """The jobs, script items and includes ``path`` loses, and a loosened ``playbook-ci`` job.

    ``before`` ``None`` is a new file (nothing to lose); ``after`` ``None`` a deleted one.

    Example::

        >>> [w.detail for w in gitlab_ci_weakenings(".gitlab-ci.yml", "lint:\\n  script: [ruff]\\n", "")]
        ["job 'lint' removed"]
    """
    if before is None:
        return []
    old, new = _blocks(before), _blocks(after or "")
    gone_jobs = _gone(_jobs(old), _jobs(new))
    kept_old = [block for block in old if block.key not in gone_jobs]
    found = [_weakening(path, "job", name) for name in gone_jobs]
    found += [_weakening(path, "script", item) for item in _gone(_scripts(kept_old), _scripts(new))]
    found += [_weakening(path, "include", entry) for entry in _gone(_includes(old), _includes(new))]
    return found + _loosened(path, kept_old, new)


# --- blocks --------------------------------------------------------------------------------------


def _blocks(text: str) -> list[_Block]:
    """Each column-0 key with its lines; another column-0 line (``---``) ends a block."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if _opens_block(line)]
    blocks: list[_Block] = []
    for start, end in pairwise([*starts, len(lines)]):
        top = _TOP_KEY.match(lines[start])
        if top is not None:
            blocks.append(_Block(unquoted(top[1]), top[2], tuple(lines[start + 1 : end])))
    return blocks


def _opens_block(line: str) -> bool:
    return bool(line) and not line[0].isspace() and not line.startswith("#")


def _jobs(blocks: Iterable[_Block]) -> Counter[str]:
    return Counter(block.key for block in blocks if block.is_job)


def _gone(before: Counter[str], after: Counter[str]) -> list[str]:
    return sorted((before - after).keys())


# --- script items --------------------------------------------------------------------------------


def _scripts(blocks: Iterable[_Block]) -> Counter[str]:
    """Every ``script``-family item, in any block but the non-script global keywords."""
    items: Counter[str] = Counter()
    for block in blocks:
        if block.key in _TOP_SCRIPTS:  # a deprecated global default script
            items.update(_section_items(block.inline, block.lines, -1))
        elif block.key not in _NO_SCRIPTS:
            items.update(_block_scripts(block.lines))
    return items


def _block_scripts(lines: Sequence[str]) -> Iterator[str]:
    """The script sections that are direct keys of the block (not ``variables: script:``)."""
    child = min((_indent(line) for line in lines if _content(line)), default=-1)
    for index, line in enumerate(lines):
        section = _SCRIPT_KEY.match(line)
        if section is not None and len(section[1]) == child:
            yield from _section_items(section[2], lines[index + 1 :], child)


def _section_items(inline: str, rest: Sequence[str], indent: int) -> list[str]:
    """The items of a ``script:`` key at ``indent``: inline, a block scalar, or ``- `` lines."""
    value = _normalized(inline)
    if value.startswith("[") and value.endswith("]"):
        return [unquoted(item.strip()) for item in value[1:-1].split(",") if item.strip()]
    if value and not _BLOCK_SCALAR.match(value):
        return [value]
    body = list(_section_body(rest, indent))
    if value:  # a block scalar: one script, the whole body
        return [_joined(body)]
    return _dash_items(body)


def _section_body(lines: Iterable[str], indent: int) -> Iterator[str]:
    for line in lines:
        if not _content(line):
            continue
        depth = _indent(line)
        if depth < indent or (depth == indent and _ITEM.match(line) is None):
            return
        yield line


def _dash_items(body: Sequence[str]) -> list[str]:
    """``- item`` lines at the first item's indent; deeper lines continue the item above."""
    items: list[list[str]] = []
    dash_indent = -1
    for line in body:
        item = _ITEM.match(line)
        if item is not None and (dash_indent < 0 or len(item[1]) == dash_indent):
            dash_indent = len(item[1])
            head = _normalized(item[2])
            items.append([] if _BLOCK_SCALAR.match(head) else [head])
        elif items:
            items[-1].append(_normalized(line))
    return [_joined(parts) for parts in items if any(parts)]


# --- includes ------------------------------------------------------------------------------------


def _includes(blocks: Iterable[_Block]) -> Counter[str]:
    entries: Counter[str] = Counter()
    for block in blocks:
        if block.key != _INCLUDE:
            continue
        lines = _outside_nested(block.lines)
        found = [_normalized(block.inline), *(_include_entry(line) for line in lines)]
        entries.update(entry for entry in found if entry)
    return entries


def _outside_nested(lines: Iterable[str]) -> Iterator[str]:
    """The include lines that are not under an entry's ``rules:`` or ``inputs:``."""
    nested_at = -1
    for line in lines:
        depth = _indent(line)
        if nested_at >= 0 and (depth > nested_at or (depth == nested_at and _ITEM.match(line))):
            continue
        nested_at = depth if _INCLUDE_NESTED.match(line) else -1
        yield line


def _include_entry(line: str) -> str:
    """``local: x`` (or another include kind), a plain ``- x`` string entry, else ``""``."""
    keyed = _INCLUDE_KEY.match(line)
    if keyed is not None:
        value = _normalized(keyed[2])
        return f"{keyed[1]}: {value}" if value else ""
    item = _ITEM.match(line)
    if item is None or _MAPPING.match(item[2]):
        return ""
    return _normalized(item[2])


# --- playbook-ci -----------------------------------------------------------------------------------


def _loosened(path: str, before: Sequence[_Block], after: Iterable[_Block]) -> list[FileWeakening]:
    if not any(block.key == PLAYBOOK_CI_JOB for block in before):
        return []  # a new job starts however it starts; only an existing gate can loosen
    gained = _loosening_marks(after) - _loosening_marks(before)
    return [
        FileWeakening(
            path,
            "playbook-ci-job-loosened",
            f"job {PLAYBOOK_CI_JOB!r} gains {mark}",
            (PLAYBOOK_CI_JOB, mark),
        )
        for mark in sorted(gained)
    ]


def _loosening_marks(blocks: Iterable[_Block]) -> Counter[str]:
    lines = (line for block in blocks if block.key == PLAYBOOK_CI_JOB for line in block.lines)
    return Counter(_normalized(line) for line in lines if _LOOSENING.match(line))


# --- shared ----------------------------------------------------------------------------------------


#: What each ``gitlab-ci-<what>-removed`` rule calls its removed thing.
_REMOVED_NOUNS: Final = MappingProxyType(
    {"job": "job", "script": "script item", "include": "include"}
)


def _weakening(path: str, what: str, name: str) -> FileWeakening:
    noun = _REMOVED_NOUNS[what]
    return FileWeakening(path, f"gitlab-ci-{what}-removed", f"{noun} {name!r} removed", (name,))


def _normalized(text: str) -> str:
    """One line as compared: no list dash, trailing comment or outer quotes."""
    value = without_comment(text.strip())
    item = _ITEM.match(value)
    value = (item[2] if item is not None else value).strip()
    return unquoted(value)


def _content(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _joined(parts: Iterable[str]) -> str:
    return "\n".join(part for part in parts if part)
