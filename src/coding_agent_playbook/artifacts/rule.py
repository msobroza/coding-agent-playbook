"""The Rule artifact and its frontmatter (SPEC.md §6.6.2).

Markdown round-trip goes through :mod:`coding_agent_playbook.artifacts.frontmatter`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from coding_agent_playbook.artifacts.frontmatter import (
    _read_markdown,
    _without_empty,
    format_frontmatter,
)


class RuleLoadError(ValueError):
    """A rule file that cannot become a :class:`Rule`; ``str`` is ``<path>: <problem>``.

    Raised for an unknown or missing frontmatter key, a missing ``---`` fence,
    invalid YAML or a non-mapping frontmatter (prU D21). ``playbook validate``
    reports each one as a finding; sync, check and render exit 2 on it. A
    ``ValueError``, like ``HookSchemaError``: the fence errors it replaces were
    one, and callers such as the eval prompt renderer catch ``ValueError``.

    Example::

        >>> str(RuleLoadError(Path("rules/x.md"), "unknown frontmatter key 'impact'"))
        "rules/x.md: unknown frontmatter key 'impact'"
    """

    def __init__(self, path: Path, problem: str) -> None:
        self.path = path
        self.problem = problem
        super().__init__(f"{path}: {problem}")


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
    # The ruff codes a rule-linked lint hook reports (specs/prK-lifecycle-hooks.md
    # §A.7): ``{warn: [...], when: [{applies_if, warn}]}``, resolved at sync.
    # ``_without_empty`` drops it when ``{}``, so unlinked rules stay byte-identical.
    lint_codes: dict[str, Any] = field(default_factory=dict)
    # The skill whose references deliver this rule (ADR 0001). Required for a
    # scoped rule, forbidden for an always rule; ``_without_empty`` drops None,
    # so a rule without it keeps byte-identical markdown.
    skill: str | None = None
    # The section of its skill's rule index this rule files under (prU D21);
    # rendered nowhere yet. ``_without_empty`` drops None, so a rule without it
    # keeps byte-identical markdown.
    section: str | None = None

    def __post_init__(self) -> None:
        # YAML parses 'key:' (blank value) as None; the dataclass default does
        # not fire for an explicit None argument. Coerce so the declared field
        # types hold and markdown round-trip stays lossless (SPEC §6.6.3).
        # This also normalises None passed from Python code: callers should
        # pass {} or [] for "empty/always", never None. A blank ``skill:`` stays
        # None, which reads as absent.
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
        if self.lint_codes is None:
            self.lint_codes = {}


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
        """Load the rule at ``path``, raising :class:`RuleLoadError` when it is malformed.

        Example::

            >>> Rule.from_markdown(Path("playbook/rules/x.md"), "<repo-local>")  # doctest: +SKIP
        """
        try:
            data, body, is_templated = _read_markdown(path)
        except yaml.YAMLError as exc:
            raise RuleLoadError(path, f"invalid YAML frontmatter: {exc}") from exc
        except ValueError as exc:  # a missing fence or a non-mapping frontmatter
            raise RuleLoadError(path, str(exc)) from exc
        problem = _frontmatter_keys_problem(data)
        if problem is not None:
            raise RuleLoadError(path, problem)
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


def _frontmatter_keys_problem(data: dict[Any, Any]) -> str | None:
    """Why ``data``'s keys cannot build a :class:`RuleFrontmatter`, or ``None`` when they can.

    Checked before construction: the dataclass would raise a ``TypeError`` that
    names neither the file nor the keys a rule may set.
    """
    fields = dataclasses.fields(RuleFrontmatter)
    allowed = "allowed keys: " + ", ".join(f.name for f in fields)
    known = {f.name for f in fields}
    unknown = [str(key) for key in data if key not in known]
    if unknown:
        noun = "key" if len(unknown) == 1 else "keys"
        return f"unknown frontmatter {noun} {_quoted(unknown)}; {allowed}"
    required = [f.name for f in fields if _is_required(f)]
    missing = [name for name in required if name not in data]
    if missing:
        noun = "key" if len(missing) == 1 else "keys"
        return f"missing required frontmatter {noun} {_quoted(missing)}; {allowed}"
    return None


def _is_required(field_: dataclasses.Field[Any]) -> bool:
    return field_.default is dataclasses.MISSING and field_.default_factory is dataclasses.MISSING


def _quoted(names: list[str]) -> str:
    return ", ".join(repr(name) for name in names)
