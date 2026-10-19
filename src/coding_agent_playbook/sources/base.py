"""The ArtifactSource ABC. See SPEC.md §20.2.

The v1 filesystem implementation lands in PR 5. Third-party sources register
via the ``coding_agent_playbook.artifact_sources`` entry point declared in
``pyproject.toml``. The StateSource ABC lives in ``config/files.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

# A stdlib-only package module, so this stays a light import.
from coding_agent_playbook._hook_schema import HookSchemaError

if TYPE_CHECKING:
    from coding_agent_playbook._typing import (
        EvalTask,
        Hook,
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
