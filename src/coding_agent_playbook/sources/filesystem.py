"""Filesystem-backed ArtifactSource and StateSource (SPEC §20.3).

These are the v1 implementations. They depend only on stdlib (tomllib,
pathlib, importlib.resources, importlib.metadata) plus pyyaml for the
frontmatter helpers already in types.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.sources.base import ArtifactSource, StateSource

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.config import Config
    from coding_agent_playbook.lockfile import Lockfile
    from coding_agent_playbook.types import Prompt, Rule, Skill

# Placeholder for eval tasks until PR 11 defines the type. Listed by ID only
# for now so that list_eval_tasks() can return an empty list without raising.
EvalTask = Any


class FileSystemArtifactSource(ArtifactSource):
    """Walks importlib.resources for the engine + overlay packages, plus
    <repo>/playbook/ for repo-local artifacts (SPEC §20.3, §11)."""

    name = "filesystem"

    def __init__(
        self,
        *,
        repo_root: Path,
        engine_package: str = "coding_agent_playbook",
        overlay_packages: list[str] | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._engine_package = engine_package
        self._overlay_packages = overlay_packages or []

    def list_rules(self) -> list[Rule]:
        raise NotImplementedError("list_rules lands in Task C.6")

    def list_prompts(self) -> list[Prompt]:
        raise NotImplementedError("list_prompts lands in Task C.7")

    def list_skills(self) -> list[Skill]:
        raise NotImplementedError("list_skills lands in Task C.7")

    def list_eval_tasks(self) -> list[EvalTask]:
        # PR 11 populates this with real EvalTask objects.
        return []


class FileSystemStateSource(StateSource):
    """Reads + writes the three TOML files in the consumer repo:
    .coding-agent-playbook.toml, .coding-agent-playbook.local.toml,
    .coding-agent-playbook.lock (SPEC §7, §14.4, §20.3)."""

    name = "filesystem"

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root

    def load_config(self) -> Config:
        raise NotImplementedError("load_config lands in Task C.4")

    def save_config(self, config: Config) -> None:
        raise NotImplementedError("save_config lands in Task C.4")

    def load_lockfile(self) -> Lockfile | None:
        raise NotImplementedError("load_lockfile lands in Task C.5")

    def save_lockfile(self, lockfile: Lockfile) -> None:
        raise NotImplementedError("save_lockfile lands in Task C.5")
