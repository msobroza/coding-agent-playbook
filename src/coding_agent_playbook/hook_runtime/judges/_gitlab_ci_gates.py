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
- ``playbook-ci-job-loosened``: the ``playbook-ci`` job gains ``allow_failure``
  (other than ``false``), ``when: manual`` or ``when: never`` (Q52).

Items compare without a trailing `` # comment`` and outer quotes, so adding a
reason comment to an item is no removal.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.judges._gate_weakening_files import FileWeakening

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
_TOP_KEY = re.compile(r"""^("[^"]*"|'[^']*'|[^\s#'"\-][^:#]*?)[ \t]*:(?:[ \t]|$)(.*)""")
_SCRIPT_KEY = re.compile(r"^([ \t]+)(?:before_|after_)?script[ \t]*:(.*)$")
_ITEM = re.compile(r"^([ \t]*)-[ \t]+(.*)$")
_INCLUDE_KEY = re.compile(
    r"^[ \t]*(?:-[ \t]+)?(local|template|component|project|remote|file)[ \t]*:[ \t]*(.*)$"
)
_MAPPING = re.compile(r"""^[^\s"'][^:]*:(?:[ \t]|$)""")
_LOOSENING = re.compile(
    r"^[ \t]*(?:-[ \t]+)?(?:allow_failure[ \t]*:(?![ \t]*false\b)|when[ \t]*:[ \t]*[\"']?(?:manual|never)\b)"
)
_COMMENT = re.compile(r"(?:^|[ \t]+)#.*$")
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
            blocks.append(_Block(_unquoted(top[1]), top[2], tuple(lines[start + 1 : end])))
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
    for index, line in enumerate(lines):
        section = _SCRIPT_KEY.match(line)
        if section is not None:
            yield from _section_items(section[2], lines[index + 1 :], len(section[1]))


def _section_items(inline: str, rest: Sequence[str], indent: int) -> list[str]:
    """The items of a ``script:`` key at ``indent``: inline, a block scalar, or ``- `` lines."""
    value = _normalized(inline)
    if value and not _BLOCK_SCALAR.match(value):
        return [value]
    body = list(_section_body(rest, indent))
    if value:  # a block scalar: one script, the whole body
        return [_joined(body)]
    return _dash_items(body)


def _section_body(lines: Iterable[str], indent: int) -> Iterator[str]:
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        depth = len(line) - len(line.lstrip())
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
        found = [_normalized(block.inline), *(_include_entry(line) for line in block.lines)]
        entries.update(entry for entry in found if entry)
    return entries


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


def _loosened(path: str, before: Iterable[_Block], after: Iterable[_Block]) -> list[FileWeakening]:
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


def _weakening(path: str, what: str, name: str) -> FileWeakening:
    noun = {"job": "job", "script": "script item", "include": "include"}[what]
    return FileWeakening(path, f"gitlab-ci-{what}-removed", f"{noun} {name!r} removed", (name,))


def _normalized(text: str) -> str:
    """One line as compared: no list dash, trailing comment or outer quotes."""
    value = _COMMENT.sub("", text.strip())
    item = _ITEM.match(value)
    value = (item[2] if item is not None else value).strip()
    return _unquoted(value)


def _unquoted(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _joined(parts: Iterable[str]) -> str:
    return "\n".join(part for part in parts if part)
