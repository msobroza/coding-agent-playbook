"""ArtifactSource and StateSource ABCs. See SPEC.md §20.2.

The v1 filesystem implementations land in PR 5. Third-party sources register
via the ``coding_agent_playbook.artifact_sources`` and
``coding_agent_playbook.state_sources`` entry points declared in
``pyproject.toml``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

# Both are stdlib-only package modules, so this stays a light import.
from coding_agent_playbook._hook_schema import HookSchemaError
from coding_agent_playbook.hooks_config import PolicyTables, policy_tables

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
        """The committed config alone, never merged with personal local overrides (P6).

        What :meth:`load_policy_tables` reads ``[hooks]``/``[guardrails]`` from
        (its ``extra_tables``), so committed output never depends on a gitignored
        file. Concrete, defaulting to :meth:`load_config`, so a third-party source
        that predates it still instantiates. Rewrites of the committed file go
        through ``commands/_committed_config``, which starts from
        ``FileSystemStateSource.read_committed_config_table``.

        Example::

            hooks_table = state_source.load_primary_config().extra_tables.get("hooks", {})
        """
        return self.load_config()

    def load_local_overrides(self) -> dict[str, Any]:
        """The per-developer table layered over the committed config; ``{}`` here.

        ``FileSystemStateSource`` returns ``.coding-agent-playbook.local.toml``.
        Concrete, so a third-party source that has no such file still instantiates.

        Example::

            >>> state_source.load_local_overrides()  # doctest: +SKIP
            {}
        """
        return {}

    def load_policy_tables(self) -> PolicyTables:
        """The ``[hooks]`` / ``[guardrails]`` tables of the committed config, kept raw.

        Never from the local overrides (specs/prK-lifecycle-hooks.md §B.1):
        committed output must not depend on a gitignored file CI never sees, so
        the local keys are only recorded, for the sync warning and validate (H21).

        Example::

            >>> state_source.load_policy_tables().hooks_config().enabled  # doctest: +SKIP
            True
        """
        return policy_tables(self.load_primary_config().extra_tables, self.load_local_overrides())

    @abstractmethod
    def save_config(self, config: Config) -> None: ...

    @abstractmethod
    def load_lockfile(self) -> Lockfile | None: ...

    @abstractmethod
    def save_lockfile(self, lockfile: Lockfile) -> None: ...
