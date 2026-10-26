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
import dataclasses
from typing import TYPE_CHECKING, Any, Final

import yaml

from coding_agent_playbook.artifacts.retired_keys import retired_key_problem

if TYPE_CHECKING:
    from pathlib import Path

    from _typeshed import DataclassInstance

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


def frontmatter_keys_problem(data: dict[Any, Any], model: type[DataclassInstance]) -> str | None:
    """Why ``data``'s keys cannot build ``model``, or ``None`` when they can.

    Checked before construction: the dataclass would raise a ``TypeError`` that
    names neither the file nor the keys the artifact may set. A retired key
    (``version``, ``eval_samples``) is reported with what replaced it.

    Example::

        >>> frontmatter_keys_problem({"impact": "HIGH"}, RuleFrontmatter)  # doctest: +SKIP
        "unknown frontmatter key 'impact'; allowed keys: id, name, ..."
    """
    fields = dataclasses.fields(model)
    allowed = "allowed keys: " + ", ".join(f.name for f in fields)
    known = {f.name for f in fields}
    unknown = [str(key) for key in data if key not in known]
    retired = [problem for key in unknown if (problem := retired_key_problem(key)) is not None]
    if retired:
        return retired[0]
    if unknown:
        return _keys_message("unknown frontmatter", unknown, allowed)
    required = [f.name for f in fields if _is_required(f)]
    missing = [name for name in required if name not in data]
    if missing:
        return _keys_message("missing required frontmatter", missing, allowed)
    return None


def _keys_message(kind: str, names: list[str], allowed: str) -> str:
    noun = "key" if len(names) == 1 else "keys"
    return f"{kind} {noun} {_quoted(names)}; {allowed}"


def _is_required(field_: dataclasses.Field[Any]) -> bool:
    return field_.default is dataclasses.MISSING and field_.default_factory is dataclasses.MISSING


def _quoted(names: list[str]) -> str:
    return ", ".join(repr(name) for name in names)
