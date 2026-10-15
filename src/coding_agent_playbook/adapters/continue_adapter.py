"""Continue adapter. See SPEC.md §10.2.

Translates canonical ``Rule``/``Prompt``/``Skill`` artifacts into the directory
layout Continue expects under ``.continue/`` at the repo root:

- Rules go to ``.continue/rules/{priority:02d}-{rule.id}.md`` with the
  ``continue_rule`` per-format transform applied.
- Prompts go to ``.continue/prompts/{prompt.slash}.md`` with the
  ``prompt_continue`` transform applied.
- Skills degrade to prompts via the ABC's default ``write_skill`` path,
  which calls :meth:`Skill.to_prompt`.

Cleanup walks ``.continue/rules`` and ``.continue/prompts`` and removes any
sentinel-tagged file whose absolute path is not in ``written_paths``. Files
without the sentinel header are user-authored and never touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import render_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook._typing import Prompt, Rule
    from coding_agent_playbook.renderer import RuleRegistry


class ContinueAdapter(Adapter):
    """Adapter that writes the ``.continue/`` directory tree.

    Registers under the ``coding_agent_playbook.adapters`` entry-point group as
    ``continue``. The orchestrator (PR 10) discovers and instantiates adapters
    through that group — never construct ``ContinueAdapter`` directly outside
    of tests.

    The optional ``rule_registry`` is plumbed into :func:`render_for` so that
    the ``includes_rules:`` appendix in prompts can be rendered. When the
    orchestrator builds the merged-overlay registry, it passes it here; when
    callers (or tests) omit it, prompts render with no auto-appendix —
    ``includes_rules:`` becomes purely declarative.
    """

    name = "continue"

    output_locations: ClassVar[tuple[str, ...]] = (".continue/rules/", ".continue/prompts/")

    def __init__(self, *, rule_registry: RuleRegistry | None = None) -> None:
        self._rule_registry = rule_registry

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        target = (
            repo_root
            / ".continue"
            / "rules"
            / f"{rule.frontmatter.priority:02d}-{rule.frontmatter.id}.md"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_for(
            rule.source_path or Path("inline"),
            rule.body,
            "continue_rule",
            frontmatter=rule.frontmatter.__dict__,
        )
        target.write_text(rendered, encoding="utf-8")
        return [target]

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".continue" / "prompts" / f"{prompt.frontmatter.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_for(
            prompt.source_path or Path("inline"),
            prompt.body,
            "prompt_continue",
            frontmatter=prompt.frontmatter.__dict__,
            rule_registry=self._rule_registry,
            template_body=prompt.template_body,
        )
        target.write_text(rendered, encoding="utf-8")
        return [target]

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [
            repo_root / ".continue" / "rules",
            repo_root / ".continue" / "prompts",
        ]
