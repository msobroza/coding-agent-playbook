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
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.renderer import render_for

if TYPE_CHECKING:
    from coding_agent_playbook._typing import Prompt, Rule


class ContinueAdapter(Adapter):
    """Adapter that writes the ``.continue/`` directory tree.

    Registers under the ``coding_agent_playbook.adapters`` entry-point group as
    ``continue``. The orchestrator (PR 10) discovers and instantiates adapters
    through that group — never construct ``ContinueAdapter`` directly outside
    of tests.
    """

    name = "continue"

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
        raise NotImplementedError("Task 6.3 wires up Continue write_prompt.")
