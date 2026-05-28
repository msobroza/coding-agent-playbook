"""Adapter ABC. See SPEC.md §10.1.

Concrete adapters (Continue, Claude Code, OpenCode, AGENTS.md) land in PRs 6-9.
Third-party adapters register via the ``coding_agent_playbook.adapters`` entry
point declared in ``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook._typing import Prompt, Rule, Skill


class Adapter(ABC):
    """Translate canonical artifacts into a harness's native format."""

    name: str

    @abstractmethod
    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Write a rendered rule to the harness-specific location(s).

        Return the paths actually written. Adapters that route rules through
        another adapter (e.g. OpenCode -> AGENTS.md) return an empty list.
        """

    @abstractmethod
    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a rendered prompt and return the paths written."""

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Degrade a skill to a prompt.

        The default treats a skill as a prompt. Subclasses with native skill
        support override this, as do adapters whose harness reads another
        adapter's output (e.g. OpenCode reads ``.claude/skills/`` natively and
        returns an empty list).
        """
        return self.write_prompt(skill.to_prompt(), repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        """Emit any buffered composite output. Default: nothing.

        Adapters that concatenate artifacts into a single file (e.g. Claude
        Code's ``CLAUDE.md``) override this and return the composed paths.
        """
        return []

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Remove generated files that no longer back a current artifact.

        Returns the deleted paths. Subclasses override only for custom cleanup.
        """
        return self._default_cleanup(written_paths, repo_root)

    def _default_cleanup(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        raise NotImplementedError(
            "Default cleanup lands with PR 6 (Continue adapter). "
            "Override cleanup_stale() to opt out until then."
        )
