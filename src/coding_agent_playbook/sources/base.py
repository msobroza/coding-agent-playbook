"""ArtifactSource and StateSource ABCs. See SPEC.md §20.2.

The v1 filesystem implementations land in PR 5. Third-party sources register
via the ``coding_agent_playbook.artifact_sources`` and
``coding_agent_playbook.state_sources`` entry points declared in
``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook._typing import (
        Config,
        EvalTask,
        Lockfile,
        Prompt,
        Rule,
        Skill,
    )


class ArtifactSource(ABC):
    """Where rules, prompts, skills, and eval tasks come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list[Rule]: ...

    @abstractmethod
    def list_prompts(self) -> list[Prompt]: ...

    @abstractmethod
    def list_skills(self) -> list[Skill]: ...

    @abstractmethod
    def list_eval_tasks(self) -> list[EvalTask]: ...


class StateSource(ABC):
    """Where config and lockfile are read from and written to."""

    name: str

    @abstractmethod
    def load_config(self) -> Config: ...

    def load_primary_config(self) -> Config:
        """The config to modify and save back: the committed file alone.

        ``playbook init`` and ``playbook check --refresh`` load with this
        before :meth:`save_config`, so personal local overrides are never
        written into the committed file (P6). Concrete, defaulting to
        :meth:`load_config`, so a third-party source that predates it still
        instantiates; such a source keeps saving whatever it loads.

        Example::

            config = state_source.load_primary_config()
            config.detector_cache = fresh_cache
            state_source.save_config(config)
        """
        return self.load_config()

    @abstractmethod
    def save_config(self, config: Config) -> None: ...

    @abstractmethod
    def load_lockfile(self) -> Lockfile | None: ...

    @abstractmethod
    def save_lockfile(self, lockfile: Lockfile) -> None: ...
