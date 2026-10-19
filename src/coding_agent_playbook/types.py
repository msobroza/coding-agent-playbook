"""Canonical artifact types: Rule, Prompt, Skill, Hook. See SPEC.md §6.6.

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

from coding_agent_playbook.artifacts import hook_schema as schema
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError

# Imported at run time: Skill.from_dict rebuilds member references from dicts.
from coding_agent_playbook.artifacts.member_reference import MemberReference

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
    # The ruff codes a rule-linked lint hook reports (specs/prK-lifecycle-hooks.md
    # §A.7): ``{warn: [...], when: [{applies_if, warn}]}``, resolved at sync.
    # ``_without_empty`` drops it when ``{}``, so unlinked rules stay byte-identical.
    lint_codes: dict[str, Any] = field(default_factory=dict)
    # The skill whose references deliver this rule (ADR 0001). Required for a
    # scoped rule, forbidden for an always rule; ``_without_empty`` drops None,
    # so a rule without it keeps byte-identical markdown.
    skill: str | None = None

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
    # Regexes the agent's final message must match while this prompt is active
    # (specs/prK-hook-pack.md §E.2 prompt-output-contract-on-stop); compiled by
    # ``playbook validate``, dropped from markdown when empty.
    output_contract: list[str] = field(default_factory=list)
    # Exactly one of {"read_only": True} or {"globs": [...]} (specs/prK-hook-pack.md
    # §E.3). A dict on purpose: ``_without_empty`` drops ``[]``, so an empty-list
    # "read-only" would round-trip to "unrestricted", and a defaulted bool would
    # add ``read_only: false`` to every prompt's markdown.
    write_scope: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # YAML parses 'key:' (blank value) as None; the dataclass default does
        # not fire for an explicit None argument. Coerce so the declared field
        # types hold and markdown round-trip stays lossless (SPEC §6.6.3).
        # This also normalises None passed from Python code: callers should
        # pass {} or [] for "empty/always", never None.
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
        if self.output_contract is None:
            self.output_contract = []
        if self.write_scope is None:
            self.write_scope = {}


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
    """A skill directory (SPEC §6.3): ``SKILL.md`` + optional ``scripts/`` and
    ``references/``. Written natively (Agent Skills layout) by the
    ``claude_code`` / ``opencode`` / ``shared_skills`` adapters through the shared
    ``SkillWriter``; other adapters degrade it via :meth:`to_prompt`.
    ``member_references`` are the skill's active member rules, rendered (ADR 0001)."""

    frontmatter: dict[str, Any]
    body: str
    scripts_dir: Path | None
    references_dir: Path | None
    source_package: str
    # Set by compose_skills at sync: the active member rules, rendered.
    member_references: tuple[MemberReference, ...] = ()

    def to_prompt(self) -> Prompt:
        """Degrade this Skill to a Prompt.

        ``scripts_dir`` and ``references_dir`` are intentionally *not* carried
        into the Prompt — adapters that natively support skills (e.g.
        :class:`ClaudeCodeAdapter`) handle those side files separately by
        overriding ``write_skill``. For every other adapter the degrade path
        is lossy by design (SPEC §6.3).

        ``Skill.frontmatter`` is an open ``dict[str, Any]`` because the Claude
        Code SKILL.md schema is not strict YAML the way Rule/Prompt frontmatter
        is. We pull canonical fields out with sensible fallbacks so the
        resulting Prompt is always writable.
        """
        identifier = self.frontmatter.get("id", "skill")
        return Prompt(
            frontmatter=PromptFrontmatter(
                id=identifier,
                name=self.frontmatter.get("name", "Skill"),
                description=self.frontmatter.get("description", ""),
                slash=self.frontmatter.get("slash") or identifier,
            ),
            body=self.body,
            template_body=self.body,
            is_templated=False,
            source_path=None,
            source_package=self.source_package,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dict(self.frontmatter),
            "body": self.body,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
            "references_dir": None if self.references_dir is None else str(self.references_dir),
            "source_package": self.source_package,
            "member_references": [member.to_dict() for member in self.member_references],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        scripts_dir = data["scripts_dir"]
        references_dir = data["references_dir"]
        # A dict written before member references existed has no such key.
        members = data.get("member_references", ())
        return cls(
            dict(data["frontmatter"]),
            data["body"],
            None if scripts_dir is None else Path(scripts_dir),
            None if references_dir is None else Path(references_dir),
            data["source_package"],
            tuple(MemberReference.from_dict(member) for member in members),
        )


# --- Hook: the 4th canonical kind (specs/prK-lifecycle-hooks.md §A) -----------
# Its frontmatter class, HookFrontmatter, is defined in artifacts.hook_frontmatter
# (imported at the top of this module).


@dataclass
class Hook:
    """A hook directory (§A.1): ``HOOK.md``/``HOOK.md.j2`` plus an optional ``scripts/``.

    Unlike Skill it keeps ``source_path``: validate, ``render --show-source``
    and script containment (H7) need it.
    """

    frontmatter: HookFrontmatter
    body: str  # post-Jinja advisory prose (== template_body for .md)
    template_body: str
    is_templated: bool  # HOOK.md.j2
    source_path: Path | None  # .../<id>/HOOK.md(.j2); None for non-filesystem sources
    source_package: str  # engine/overlay package name or "<repo-local>"
    scripts_dir: Path | None = None  # <hook dir>/scripts when present

    @property
    def hook_dir(self) -> Path | None:
        """The directory holding ``HOOK.md`` (its name is the hook id), if on disk."""
        return None if self.source_path is None else self.source_path.parent

    @classmethod
    def from_markdown(cls, path: Path, source_package: str) -> Hook:
        """Parse ``path``; a bad fence or bad YAML is a HookSchemaError on ``frontmatter``.

        Example: ``Hook.from_markdown(Path("playbook/hooks/x/HOOK.md"), "<repo-local>")``.
        """
        try:
            data, body = split_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError) as exc:
            raise HookSchemaError(
                str(path), "frontmatter", None, "a '---' fenced YAML mapping", problem=str(exc)
            ) from exc
        scripts = path.parent / "scripts"
        return cls(
            HookFrontmatter.from_mapping(data, where=str(path)),
            body,
            body,
            path.name.endswith(".md.j2"),
            path,
            source_package,
            scripts if scripts.is_dir() else None,
        )

    def to_markdown(self) -> str:
        """Frontmatter (compacted) plus the template body; byte identity is not promised."""
        return format_frontmatter(self.frontmatter.to_mapping(), self.template_body)

    def to_dict(self) -> dict[str, Any]:
        """Lossless dict form: full frontmatter, paths as ``str | None`` (§A.4)."""
        return {
            "frontmatter": dataclasses.asdict(self.frontmatter),
            "body": self.body,
            "template_body": self.template_body,
            "is_templated": self.is_templated,
            "source_path": None if self.source_path is None else str(self.source_path),
            "source_package": self.source_package,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hook:
        """Inverse of to_dict: ``Hook.from_dict(h.to_dict()) == h``."""
        source_path, scripts_dir = data["source_path"], data["scripts_dir"]
        return cls(
            HookFrontmatter.from_mapping(data["frontmatter"], where=source_path or "<dict>"),
            data["body"],
            data["template_body"],
            data["is_templated"],
            None if source_path is None else Path(source_path),
            data["source_package"],
            None if scripts_dir is None else Path(scripts_dir),
        )

    def to_advisory_rule(self) -> Rule | None:
        """The advisory-rule envelope (§A.8), or None when the body is blank.

        The body is this hook's (rendered) body; K3's ``hook_advisory``
        projection adds the enforcement line, and resolve_effective_hooks
        swaps in globs inherited from a linked rule.
        Example: ``hook.to_advisory_rule().frontmatter.id == "guardrail-" + hook.frontmatter.id``.
        """
        if not self.body.strip():
            return None
        fm = self.frontmatter
        globs = list(dict.fromkeys(p for m in fm.matcher.values() for p in m.paths))
        advisory = RuleFrontmatter(
            id=schema.ADVISORY_RULE_PREFIX + fm.id,
            name="Guardrail: " + fm.name,
            description=fm.description,
            scope="scoped" if globs else "always",
            globs=globs,
            applies_if={},  # already gated by the hook's own applies_if
            priority=schema.ADVISORY_RULE_PRIORITY,
        )
        return Rule(advisory, self.body, self.body, False, self.source_path, self.source_package)
