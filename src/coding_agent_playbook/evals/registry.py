"""The runner and judge lookups for an Eval task run (``playbook eval --run``, SPEC §15).

``playbook eval --run`` selects its runner from the ``coding_agent_playbook.runners``
entry-point group and its optional judge from ``coding_agent_playbook.judges``; the
group names are the external contract (L2) and stay verbatim here.
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner


#: Entry-point group runners self-register under (mirrors adapters/sources).
_RUNNERS_GROUP = "coding_agent_playbook.runners"

#: Entry-point group judges register under (``llm`` ships; default: no judge).
_JUDGES_GROUP = "coding_agent_playbook.judges"


def load_runner_class(name: str) -> type[HarnessRunner] | None:
    """Load the runner class registered under ``name`` in the runners group.

    Never instantiates the runner here (the caller does, after the availability
    guard). Returns ``None`` when no entry point matches ``name``.
    """
    for ep in metadata.entry_points(group=_RUNNERS_GROUP):
        if ep.name == name:
            return ep.load()  # type: ignore[no-any-return]
    return None


def available_runner_names() -> list[str]:
    """Sorted names of every runner registered in the entry-point group."""
    return sorted(ep.name for ep in metadata.entry_points(group=_RUNNERS_GROUP))


def load_judge_class(name: str) -> type[Judge] | None:
    """Load the judge class registered under ``name`` in the judges group.

    Never instantiates the judge here (the caller does, after the availability
    guard). Returns ``None`` when no entry point matches ``name``.
    """
    for ep in metadata.entry_points(group=_JUDGES_GROUP):
        if ep.name == name:
            return ep.load()  # type: ignore[no-any-return]
    return None


def available_judge_names() -> list[str]:
    """Sorted names of every judge registered in the entry-point group."""
    return sorted(ep.name for ep in metadata.entry_points(group=_JUDGES_GROUP))
