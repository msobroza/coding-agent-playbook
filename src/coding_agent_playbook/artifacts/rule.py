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
    frontmatter_keys_problem,
)


class RuleLoadError(ValueError):
    """A rule file that cannot become a :class:`Rule`; ``str`` is ``<path>: <problem>``.

    Raised for an unknown, retired (``version``, #281) or missing frontmatter
    key, a missing ``---`` fence, invalid YAML or a non-mapping frontmatter
    (prU D21). ``playbook validate``
    reports each one as a finding; sync, check and render exit 2 on it. A
    ``ValueError``, like ``HookSchemaError``: the fence errors it replaces were
    one, and callers such as the eval prompt renderer catch ``ValueError``. So
    does ``evals/validator.py``'s ``_validate_schema``: a malformed rule file
    reached while compiling an eval sample is reported against that sample.

    Example::

        >>> str(RuleLoadError(Path("rules/x.md"), "unknown frontmatter key 'impact'"))
        "rules/x.md: unknown frontmatter key 'impact'"
    """

    def __init__(self, path: Path, problem: str) -> None:
        self.path = path
        self.problem = problem
        super().__init__(f"{path}: {problem}")


#: A rule's ``scope``: loaded every session, or on demand (a skill's member or a reference).
RuleScope = Literal["always", "scoped"]


@dataclass
class RuleFrontmatter:
    id: str
    name: str
    description: str
    scope: RuleScope
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
    # its impact tags the rendered title (D32). ``_without_empty`` drops None,
    # so a rule without it keeps byte-identical markdown.
    section: str | None = None

    def __post_init__(self) -> None:
        # YAML parses 'key:' (blank value) as None; the dataclass default does
        # not fire for an explicit None argument. Coerce so the declared field
        # types hold and markdown round-trip stays lossless (SPEC §6.6.3).
        # This also normalises None passed from Python code: callers should
        # pass {} or [] for "empty/always", never None. A blank ``skill:`` stays
        # None, which reads as absent.
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
    # The skill whose ``skills/<skill>/rules/`` holds the source file (prU D5,
    # ADR 0005), or None for a ``<layer>/rules/`` file. Membership by location:
    # the loader copies it into ``frontmatter.skill`` when the file sets none,
    # so every consumer of ``skill`` sees in-skill rules as members unchanged.
    home_skill: str | None = None
    # True when ``frontmatter.skill`` was filled from ``home_skill`` because the
    # file sets no ``skill:``, so ``to_markdown`` drops only that injected value
    # and keeps a ``skill:`` the author wrote, even a redundant one.
    skill_from_location: bool = False

    @classmethod
    def from_markdown(
        cls, path: Path, source_package: str, *, home_skill: str | None = None
    ) -> Rule:
        """Load the rule at ``path``, raising :class:`RuleLoadError` when it is malformed.

        ``home_skill`` is the id of the skill whose ``rules/`` directory holds
        ``path``; it fills ``frontmatter.skill`` when the file leaves it out (an
        explicit ``skill:`` is kept as written, for validation to judge).

        Example::

            >>> Rule.from_markdown(Path("playbook/rules/x.md"), "<repo-local>")  # doctest: +SKIP
            >>> Rule.from_markdown(path, "<repo-local>", home_skill="s").frontmatter.skill  # doctest: +SKIP
            's'
        """
        try:
            data, body, is_templated = _read_markdown(path)
        except yaml.YAMLError as exc:
            raise RuleLoadError(path, f"invalid YAML frontmatter: {exc}") from exc
        except ValueError as exc:  # a missing fence or a non-mapping frontmatter
            raise RuleLoadError(path, str(exc)) from exc
        problem = frontmatter_keys_problem(data, RuleFrontmatter)
        if problem is not None:
            raise RuleLoadError(path, problem)
        injected = home_skill is not None and data.get("skill") is None
        if injected:
            data = {**data, "skill": home_skill}
        return cls(
            RuleFrontmatter(**data),
            body,
            body,
            is_templated,
            path,
            source_package,
            home_skill,
            injected,
        )

    def to_markdown(self) -> str:
        """The rule as a markdown file, without a ``skill`` the loader injected.

        The location carries that membership, so writing it back would add a
        ``skill:`` line the author never wrote (prU D5); an authored ``skill:``
        is written as it was.

        Example: ``rule.to_markdown().startswith("---\n")`` -> ``True``.
        """
        data = dataclasses.asdict(self.frontmatter)
        if self.skill_from_location:
            data["skill"] = None
        return format_frontmatter(_without_empty(data), self.template_body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dataclasses.asdict(self.frontmatter),
            "body": self.body,
            "template_body": self.template_body,
            "is_templated": self.is_templated,
            "source_path": None if self.source_path is None else str(self.source_path),
            "source_package": self.source_package,
            "home_skill": self.home_skill,
            "skill_from_location": self.skill_from_location,
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
            data.get("home_skill"),
            data.get("skill_from_location", False),
        )
