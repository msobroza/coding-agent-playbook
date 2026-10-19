"""commitizen as commit-message-convention runs it (specs/prK-hook-pack.md §F.4.1, §F.4.2).

- :func:`cz_runner`: the worktree's ``machine.json`` ``cz`` pin (sync resolves
  the project venv's ``cz`` first, else ``PATH``), or why there is none;
- :class:`CzRunner`: ``cz check --message`` / ``--rev-range`` through
  ``ctx.proc`` with a 3 s timeout (never past the event deadline), in the
  repository root so cz finds ``[tool.commitizen]`` itself. A timeout or a
  vanished program fails open with a note;
- :func:`deny_reason`: cz's rejection as model-facing text: control
  characters stripped, at most three of cz's lines, cz's unquoted echo of the
  message replaced by the subject quoted as data (at most 100 characters), and
  never a pointer at the convention's config or ``cutover_date``, which would
  teach a bypass;
- :func:`push_ranges`: the ``(tracking ref, source)`` ranges a ``git push``
  publishes, from local refs only: an explicit ``src:dst`` refspec, else the
  upstream, else ``<remote>/<current branch>``. A ref git does not know
  (never fetched) is left out: CI checks it.

A private module: it registers no handler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.proc import ProcTimeout

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.cutover import CzPlan
    from coding_agent_playbook.hook_runtime.deps import Clock, ProcPort
    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.git import GitPort
    from coding_agent_playbook.hook_runtime.gitargv import GitInvocation
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = [
    "CZ_TIMEOUT_S",
    "REWRITE_HINT",
    "CzRunner",
    "cz_runner",
    "deny_reason",
    "missing_note",
    "push_ranges",
]

CZ_TIMEOUT_S: Final = 3.0
REWRITE_HINT: Final = "Rewrite the message to this repo's commit convention and retry."
SUBJECT_CHARS: Final = 100
CZ_LINES: Final = 3
_LINE_CHARS: Final = 160
#: Time left for the dispatcher to answer after the last cz call.
_MARGIN_S: Final = 0.25
#: cz echoes the message unquoted: ``commit "<sha>": "<subject>"``; it is re-quoted as data.
_ECHO: Final = re.compile(r'commit "(?P<sha>[0-9a-f]{0,40})"(?::\s*"(?P<subject>.*)")?')
#: Lines that would point at the convention's config or the cut-over (a bypass recipe).
_TEACHES: Final = re.compile(r"tool\.commitizen|\.cz\.(?:toml|json|yaml)|cutover|pyproject", re.I)
_NO_PUSH_RANGE: Final = frozenset({"--all", "--mirror", "--tags", "--delete", "d", "--prune"})

type PinProblem = Literal["missing", "changed"]


def cz_runner(ctx: HandlerContext, repo: RepoInfo) -> CzRunner | PinProblem:
    """The pinned ``cz`` of ``repo``'s worktree, or why it cannot run.

    Example: ``cz_runner(ctx, ev.repo)`` is ``"missing"`` before a sync pinned cz.
    """
    from coding_agent_playbook.hook_runtime.config.pin import read_machine_pins

    pins = read_machine_pins(git_dir=repo.git_dir)
    pin = None if pins is None else pins.tool("cz")
    if pin is None:
        return "missing"
    if not pin.unchanged():
        return "changed"
    return CzRunner(
        argv=pin.argv, proc=ctx.proc, cwd=repo.worktree_root, clock=ctx.clock, deadline=ctx.deadline
    )


def missing_note(ctx: HandlerContext, problem: PinProblem) -> str | None:
    """One user note per session when cz cannot run; the check is then skipped (fail open).

    Example: ``missing_note(ctx, "missing")`` names the install and the re-sync.
    """
    if not ctx.session.once(f"commit-convention:cz-{problem}"):
        return None
    why = "is not pinned for this worktree" if problem == "missing" else "changed since sync"
    return (
        f"commit-message-convention: cz {why}, so commit messages are not checked; "
        "ask the user to install commitizen and run playbook sync."
    )


@dataclass
class CzRunner:
    """``cz check`` through the dispatch's ``ProcPort``; ``notes`` collect fail-open reasons.

    Example::

        >>> CzRunner(("/v/bin/cz",), proc, "/repo", clock, deadline).message("feat: x")
        ... # doctest: +SKIP
    """

    argv: tuple[str, ...]
    proc: ProcPort
    cwd: str
    clock: Clock
    deadline: float
    notes: list[str] = field(default_factory=list)

    def message(self, message: str, *, sha: str = "") -> str | None:
        """The deny reason when cz rejects ``message``, else ``None``."""
        output = self._run(["check", "--message", message])
        return None if output is None else deny_reason(output, message, sha=sha)

    def rev_range(self, rev_range: str) -> str | None:
        """The deny reason when cz rejects any commit of ``rev_range``, else ``None``."""
        output = self._run(["check", "--rev-range", rev_range])
        return None if output is None else deny_reason(output, None)

    def plan(self, plan: CzPlan) -> str | None:
        """Run ``plan``'s checks; the first rejection's reason, else ``None``."""
        if plan.note:
            self.notes.append(f"commit-message-convention: {plan.note}")
        if plan.rev_range is not None:
            return self.rev_range(plan.rev_range)
        for commit in plan.commits:
            reason = self.message(commit.message, sha=commit.sha)
            if reason is not None:
                return reason
        return None

    def _run(self, args: Sequence[str]) -> bytes | None:
        """cz's output when it rejected, ``None`` when it accepted or could not run."""
        timeout = min(CZ_TIMEOUT_S, self.deadline - self.clock.monotonic() - _MARGIN_S)
        if timeout <= 0:
            self.notes.append("commit-message-convention: no time left for cz; not checked")
            return None
        try:
            done = self.proc.run([*self.argv, *args], timeout=timeout, cwd=self.cwd)
        except (ProcTimeout, OSError) as exc:
            self.notes.append(f"commit-message-convention: cz did not answer ({exc}); not checked")
            return None
        return None if done.returncode == 0 else done.stdout + done.stderr


def deny_reason(output: bytes, message: str | None, *, sha: str = "") -> str:
    """cz's rejection in at most four lines (the reason cap), sanitized for the model.

    Three come from cz: its echo of the rejected commit becomes the first, with
    the subject quoted as data (``message``'s first line, else the echoed one),
    then cz's own lines, then :data:`REWRITE_HINT`.

    Example::

        >>> deny_reason(b"commit validation: failed!\\n", "Add thing.").splitlines()[:2]
        ['cz check rejected the commit message "Add thing."', 'cz: commit validation: failed!']
    """
    lines: list[str] = []
    named, subject = sha[:12], None if message is None else message.split("\n", 1)[0]
    for raw in output.decode("utf-8", errors="replace").splitlines():
        line = " ".join(clean_text(raw).split())
        echo = _ECHO.match(line)
        if echo is not None:
            named = named or echo["sha"][:12]
            subject = subject if subject is not None else echo["subject"]
        elif line and not _TEACHES.search(line):
            lines.append(clip(f"cz: {line}", _LINE_CHARS))
    which = f"commit {named}" if named else "the commit message"
    head = f"cz check rejected {which}"
    if subject is not None:
        head += f" {quote_data(subject, SUBJECT_CHARS)}"
    return "\n".join([head, *lines[: CZ_LINES - 1], REWRITE_HINT])


def push_ranges(git: GitInvocation, port: GitPort) -> list[tuple[str, str]]:
    """``(tracking ref, source)`` per range the push publishes; known local refs only.

    Example: ``push_ranges(parse_git(seg("git push")), git) == [("refs/remotes/origin/x", "HEAD")]``.
    """
    from coding_agent_playbook.hook_runtime._git_options import git_args

    parsed = git_args(git.args, "push")
    if parsed.has(*_NO_PUSH_RANGE):
        return []  # whole-repo or deleting pushes: the CI twin checks those
    remote = parsed.positionals[0] if parsed.positionals else None
    refspecs = parsed.positionals[1:]
    if refspecs:
        found = [_refspec_range(remote, spec, port) for spec in refspecs]
        ranges = [pair for pair in found if pair is not None]
    else:
        base = port.upstream() or _branch_ref(remote, port)
        ranges = [] if base is None else [(base, "HEAD")]
    return [(base, src) for base, src in ranges if port.rev_commit(base) is not None]


def _refspec_range(remote: str | None, spec: str, port: GitPort) -> tuple[str, str] | None:
    """``(refs/remotes/<remote>/<dst>, src)`` for one refspec; ``None`` for a delete."""
    src, colon, dst = spec.lstrip("+").partition(":")
    if not src or (colon and not dst):
        return None
    if not colon:
        dst = src if src != "HEAD" else (port.symbolic_ref("HEAD") or "")
    dst = dst.removeprefix("refs/heads/")
    return (f"refs/remotes/{remote or 'origin'}/{dst}", src) if dst else None


def _branch_ref(remote: str | None, port: GitPort) -> str | None:
    branch = port.symbolic_ref("HEAD")
    return None if branch is None else f"refs/remotes/{remote or 'origin'}/{branch}"
