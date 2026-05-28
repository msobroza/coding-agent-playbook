"""Canonical artifact types: Rule, Prompt, Skill. See SPEC.md §6.6.

The authoring format is markdown + YAML frontmatter (``.md`` / ``.md.j2``);
these dataclasses are the engine's internal representation. The two formats
round-trip: ``Rule.from_dict(rule.to_dict()) == rule``, and a Rule parsed from
markdown re-serializes to an equal Rule.

PR 2 does not render Jinja (that is the renderer, PR 4): ``from_markdown`` sets
``body`` to the raw template body. PR 4 will populate ``body`` with the rendered
output while keeping ``template_body`` as the source.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

_FENCE = "---"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``---\\n<yaml>\\n---\\n<body>`` into a (frontmatter mapping, body)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _FENCE:
        raise ValueError("artifact must start with a '---' frontmatter fence")
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == _FENCE:
            data = yaml.safe_load("".join(lines[1:index])) or {}
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


@dataclass
class RuleFrontmatter:
    id: str
    name: str
    description: str
    scope: Literal["always", "scoped"]
    version: int = 1
    globs: list[str] = field(default_factory=list)
    applies_if: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # YAML parses 'key:' (blank value) as None; the dataclass default does
        # not fire for an explicit None argument. Coerce so the declared field
        # types hold and markdown round-trip stays lossless (SPEC §6.6.3).
        if self.version is None:
            self.version = 1
        if self.globs is None:
            self.globs = []
        if self.applies_if is None:
            self.applies_if = {}
        if self.priority is None:
            self.priority = 50
        if self.tags is None:
            self.tags = []


@dataclass
class Rule:
    frontmatter: RuleFrontmatter
    body: str
    template_body: str
    is_templated: bool
    source_path: Path | None
    source_package: str

    @classmethod
    def from_markdown(cls, path: Path, source_package: str) -> Rule:
        data, body, is_templated = _read_markdown(path)
        return cls(RuleFrontmatter(**data), body, body, is_templated, path, source_package)

    def to_markdown(self) -> str:
        return format_frontmatter(
            _without_empty(dataclasses.asdict(self.frontmatter)), self.template_body
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dataclasses.asdict(self.frontmatter),
            "body": self.body,
            "template_body": self.template_body,
            "is_templated": self.is_templated,
            "source_path": None if self.source_path is None else str(self.source_path),
            "source_package": self.source_package,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        source_path = data["source_path"]
        return cls(
            RuleFrontmatter(**data["frontmatter"]),
            data["body"],
            data["template_body"],
            data["is_templated"],
            None if source_path is None else Path(source_path),
            data["source_package"],
        )


@dataclass
class PromptFrontmatter:
    id: str
    name: str
    description: str
    slash: str
    version: int = 1
    applies_if: dict[str, Any] = field(default_factory=dict)
    input_variables: list[dict[str, Any]] = field(default_factory=list)
    includes_rules: list[str] = field(default_factory=list)
    eval_tasks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # YAML parses 'key:' (blank value) as None; the dataclass default does
        # not fire for an explicit None argument. Coerce so the declared field
        # types hold and markdown round-trip stays lossless (SPEC §6.6.3).
        if self.version is None:
            self.version = 1
        if self.applies_if is None:
            self.applies_if = {}
        if self.input_variables is None:
            self.input_variables = []
        if self.includes_rules is None:
            self.includes_rules = []
        if self.eval_tasks is None:
            self.eval_tasks = []


@dataclass
class Prompt:
    frontmatter: PromptFrontmatter
    body: str
    template_body: str
    is_templated: bool
    source_path: Path | None
    source_package: str

    @classmethod
    def from_markdown(cls, path: Path, source_package: str) -> Prompt:
        data, body, is_templated = _read_markdown(path)
        return cls(PromptFrontmatter(**data), body, body, is_templated, path, source_package)

    def to_markdown(self) -> str:
        return format_frontmatter(
            _without_empty(dataclasses.asdict(self.frontmatter)), self.template_body
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dataclasses.asdict(self.frontmatter),
            "body": self.body,
            "template_body": self.template_body,
            "is_templated": self.is_templated,
            "source_path": None if self.source_path is None else str(self.source_path),
            "source_package": self.source_package,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Prompt:
        source_path = data["source_path"]
        return cls(
            PromptFrontmatter(**data["frontmatter"]),
            data["body"],
            data["template_body"],
            data["is_templated"],
            None if source_path is None else Path(source_path),
            data["source_package"],
        )


@dataclass
class Skill:
    """Claude Code-only artifact (SPEC §6.3). Skill directory loading and the
    degrade-to-prompt conversion land with the adapters (PR 6+)."""

    frontmatter: dict[str, Any]
    body: str
    scripts_dir: Path | None
    references_dir: Path | None
    source_package: str

    def to_prompt(self) -> Prompt:
        raise NotImplementedError(
            "Skill -> Prompt degradation lands with the Continue adapter (PR 6)."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dict(self.frontmatter),
            "body": self.body,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
            "references_dir": None if self.references_dir is None else str(self.references_dir),
            "source_package": self.source_package,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        scripts_dir = data["scripts_dir"]
        references_dir = data["references_dir"]
        return cls(
            dict(data["frontmatter"]),
            data["body"],
            None if scripts_dir is None else Path(scripts_dir),
            None if references_dir is None else Path(references_dir),
            data["source_package"],
        )
