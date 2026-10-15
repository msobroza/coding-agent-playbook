"""ArtifactSource and StateSource ABCs. See SPEC.md §20.2.

The v1 filesystem implementations land in PR 5. Third-party sources register
via the ``coding_agent_playbook.artifact_sources`` and
``coding_agent_playbook.state_sources`` entry points declared in
``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

# Imports nothing from the package at runtime, so this stays a light import.
from coding_agent_playbook._hook_schema import HookSchemaError

if TYPE_CHECKING:
    from coding_agent_playbook._typing import (
        Config,
        EvalTask,
        Hook,
        Lockfile,
        Prompt,
        Rule,
        Skill,
    )


class ArtifactSource(ABC):
    """Where rules, prompts, skills, hooks, and eval tasks come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list[Rule]: ...

    @abstractmethod
    def list_prompts(self) -> list[Prompt]: ...

    @abstractmethod
    def list_skills(self) -> list[Skill]: ...

    def list_hooks(self) -> list[Hook]:
        """Every hook this source ships, raising ``HookSchemaError`` on a malformed one.

        Concrete, returning ``[]``, not abstract: a third-party source written
        before hooks existed must still instantiate (prK §A.5).

        Example::

            >>> source.list_hooks()  # doctest: +SKIP
            []
        """
        return []

    def collect_hooks(self) -> tuple[list[Hook], list[HookSchemaError]]:
        """Every well-formed hook plus the errors of malformed ones, never raising.

        What ``playbook validate`` reads, so it can report every malformed hook
        (prK §P P8c). This default can only record the one error a failing
        :meth:`list_hooks` raises; a source that sees each hook overrides it.

        Example::

            >>> hooks, errors = source.collect_hooks()  # doctest: +SKIP
        """
        try:
            return self.list_hooks(), []
        except HookSchemaError as exc:
            return [], [exc]

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
