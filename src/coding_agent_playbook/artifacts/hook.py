"""The Hook artifact: a hook directory and its advisory-rule envelope (SPEC.md §6.6.7)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from coding_agent_playbook.artifacts import hook_schema as schema
from coding_agent_playbook.artifacts.frontmatter import format_frontmatter, split_frontmatter
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter

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
