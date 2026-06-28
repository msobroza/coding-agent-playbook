"""``FakeRunner`` — the hermetic, deterministic test driver (PR R1 §1).

The default :class:`~coding_agent_playbook.evals.runner.HarnessRunner` for unit
tests and air-gapped runs: instead of driving a real agent, its
:meth:`_invoke_agent` applies a caller-supplied **mutation** to the scratch tree
and returns a canned :class:`~coding_agent_playbook.evals.runner.AgentRun`. No
network, no CLI, fully reproducible — so the whole runner → scoring pipeline can
be exercised end-to-end with a known agent "edit".

The mutation is a ``Callable[[Path], None]`` invoked with the scratch directory
(the agent's working tree); it writes/edits/deletes files exactly as a real agent
would have. A common pattern is a closure over a ``{relpath: contents}`` dict —
:func:`write_files` builds one. The default mutation is a no-op (the agent
"did nothing"), useful for asserting the baseline scores as expected.

Registered under the ``coding_agent_playbook.runners`` entry-point group as
``fake`` (see ``pyproject.toml``); discover it via that group rather than
instantiating directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.evals.runner import AgentRun, HarnessRunner

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    #: A mutation applied to the scratch tree, standing in for the agent's edits.
    type Mutation = Callable[[Path], None]


def _noop(scratch_dir: Path) -> None:
    """Default mutation: the agent made no changes."""


def write_files(files: dict[str, str]) -> Mutation:
    """Build a mutation that writes each ``{relpath: contents}`` into the tree.

    Parent directories are created as needed. Handy for the common case of a fake
    agent that creates or overwrites a few files (e.g. extracting a helper into an
    existing module, or adding a new test file).
    """

    def _apply(scratch_dir: Path) -> None:
        for rel, contents in files.items():
            target = scratch_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")

    return _apply


class FakeRunner(HarnessRunner):
    """A :class:`HarnessRunner` whose "agent" is a deterministic mutation.

    ``mutation`` is applied to the scratch tree in :meth:`_invoke_agent`;
    ``transcript`` and ``returncode`` are the canned :class:`AgentRun` fields.
    """

    name = "fake"

    def __init__(
        self,
        mutation: Mutation = _noop,
        *,
        transcript: str = "[fake agent run]",
        returncode: int = 0,
    ) -> None:
        self._mutation = mutation
        self._transcript = transcript
        self._returncode = returncode

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """Apply the configured mutation and return the canned run."""
        self._mutation(scratch_dir)
        return AgentRun(transcript=self._transcript, returncode=self._returncode)
