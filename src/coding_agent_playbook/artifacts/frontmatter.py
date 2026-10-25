"""The markdown + YAML frontmatter authoring format of the artifacts. See SPEC.md §6.6.

Rule, Prompt and Hook are authored as markdown with YAML frontmatter (``.md`` /
``.md.j2``); their dataclasses are the engine's internal representation. The two
formats round-trip: ``Rule.from_dict(rule.to_dict()) == rule``, and a Rule parsed
from markdown re-serializes to an equal Rule.

PR 2 does not render Jinja (that is the renderer, PR 4): ``from_markdown`` sets
``body`` to the raw template body. PR 4 will populate ``body`` with the rendered
output while keeping ``template_body`` as the source.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Final

import yaml

if TYPE_CHECKING:
    from pathlib import Path

_FENCE = "---"
#: ``yaml.CSafeLoader`` exists only when PyYAML is built with libyaml.
_WITH_LIBYAML: Final = yaml.__with_libyaml__


def _load_yaml(chunk: str, *, with_libyaml: bool = _WITH_LIBYAML) -> object:
    """Parse one frontmatter chunk with libyaml when PyYAML has it, else in pure Python.

    The pure-Python SafeLoader was about 25% of a sync run (a sync parses hundreds
    of frontmatters); CSafeLoader is about 5.8x faster and gives the same mapping
    for every shipped frontmatter (tests/catalog/test_frontmatter_loader.py).
    libyaml is more lenient elsewhere (it accepts some tabs SafeLoader rejects),
    so a consumer's file can load on a libyaml build and fail without one. Its
    errors carry no source snippet or caret, so a chunk it rejects is parsed
    again in pure Python, whose error is raised: the same text on every build.
    Both calls name their Loader literally, as the unsafe-deserialization guard
    requires.

    Example::

        _load_yaml("id: x\\n")  # {"id": "x"}
    """
    if with_libyaml:
        with contextlib.suppress(yaml.YAMLError):
            return yaml.load(chunk, Loader=yaml.CSafeLoader)
    return yaml.load(chunk, Loader=yaml.SafeLoader)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``---\\n<yaml>\\n---\\n<body>`` into a (frontmatter mapping, body)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _FENCE:
        raise ValueError("artifact must start with a '---' frontmatter fence")
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == _FENCE:
            data = _load_yaml("".join(lines[1:index])) or {}
            if not isinstance(data, dict):
                raise ValueError("frontmatter must be a YAML mapping")
            return data, "".join(lines[index + 1 :])
    raise ValueError("unterminated frontmatter: missing closing '---'")


def format_frontmatter(data: dict[str, Any], body: str) -> str:
    """Inverse of :func:`split_frontmatter` (YAML whitespace may be normalized)."""
    fenced = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{_FENCE}\n{fenced}\n{_FENCE}\n{body}"


def _without_empty(data: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is an empty list/dict/None, keeping frontmatter lean."""
    return {key: value for key, value in data.items() if value not in ([], {}, None)}


def _read_markdown(path: Path) -> tuple[dict[str, Any], str, bool]:
    data, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return data, body, path.name.endswith(".md.j2")
