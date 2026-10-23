"""``playbook ci``'s ``commit-convention`` step: commitizen over the branch's commits (specs/prK-hook-pack.md §F.4.3, §F.5).

The authoritative twin of commit-message-convention. It reads ``git log
<merge base>..HEAD`` with parents and committer dates, keeps the commits on or
after ``[hooks.commit_convention] cutover_date`` (``hook_runtime.judges.commit_cutover``, the
plan the hook's push scan uses) and runs ``cz`` directly (D-Q2: no
``playbook`` wrapper). One ``--rev-range`` covers exactly the kept commits or
is not used:

- every commit kept: ``cz check --rev-range <merge base>..HEAD``;
- a linear newest tail (no merge): ``cz check --rev-range <oldest kept>^..HEAD``;
- otherwise ``cz check --message <message>`` per kept commit, so a branch
  that merged main never has main's own commits checked.

In squash-merge repositories the PR title becomes the commit subject, so with
``PLAYBOOK_PR_TITLE`` set the step also runs ``cz check --message <title>``:
the title is one argv element read from the environment, never interpolated
into a workflow ``run:`` line (the GitHub Actions script-injection pattern).
A leading GitLab draft marker (``[Draft]``, ``Draft:``, ``(Draft)``, any case)
is stripped first: it is not part of the squash commit's subject
(specs/prF-forge-adapter.md §10.2).
A missing ``cz`` **fails** the step: CI is the twin that must not be skipped.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins.policy import cutover_date_value
from coding_agent_playbook.hook_runtime.judges.commit_cutover import parse_cutover, plan_cz_checks

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.commands.twins.ci import CiStepRunner, StepRun
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort

__all__ = [
    "COMMIT_STEP",
    "PR_TITLE_ENV",
    "CzCommands",
    "cz_commands",
    "run_cz_commands",
    "squash_subject",
]

COMMIT_STEP: Final = "commit-convention"
#: The environment variable a pull-request job sets to the PR title.
PR_TITLE_ENV: Final = "PLAYBOOK_PR_TITLE"
#: The most commits one CI range reads; past it the range starts at the oldest one read.
LOG_LIMIT: Final = 5_000
#: GitLab's draft markers (``Draft:``, ``[Draft]``, ``(Draft)``), matched case-insensitively.
_DRAFT_PREFIX: Final = re.compile(r"^\s*(?:\[draft\]|\(draft\)|draft:)\s*", re.IGNORECASE)
CZ_MISSING: Final = (
    "cz (commitizen) not found on PATH: install the project's dev dependencies (with "
    "commitizen) in this CI job"
)


@dataclass(frozen=True, slots=True)
class CzCommands:
    """The ``cz`` invocations the step runs (argv lists), or why it cannot run.

    Example: ``CzCommands((("/v/bin/cz", "check", "--rev-range", "abc..HEAD"),))``.
    """

    commands: tuple[tuple[str, ...], ...] = ()
    error: str = ""


def cz_commands(
    git: GitPort,
    repo_root: Path,
    merge_base: str,
    *,
    which: Callable[[str], str | None],
    env: Mapping[str, str],
) -> CzCommands:
    """The checks of ``<merge_base>..HEAD`` after the cut-over, plus the PR title when set.

    Raises what ``git`` raises (``GitError``); a bad ``cutover_date`` is an ``error``.

    Example::

        >>> cz_commands(git, root, "abc", which=shutil.which, env=os.environ).commands
        ... # doctest: +SKIP
        (('/v/bin/cz', 'check', '--rev-range', 'abc..HEAD'),)
    """
    try:
        cutover = parse_cutover(cutover_date_value(repo_root))
    except ValueError as exc:
        return CzCommands(error=f"[hooks.commit_convention]: {exc}")
    cz = which("cz")
    if cz is None:
        return CzCommands(error=CZ_MISSING)
    commits = git.commit_log(f"{merge_base}..HEAD", limit=LOG_LIMIT)
    plan = plan_cz_checks(
        commits,
        cutover,
        base=merge_base,
        truncated=len(commits) >= LOG_LIMIT,
        max_messages=LOG_LIMIT,
    )
    commands: list[tuple[str, ...]] = []
    if plan.rev_range is not None:
        commands.append((cz, "check", "--rev-range", plan.rev_range))
    commands.extend((cz, "check", "--message", commit.message) for commit in plan.commits)
    title = env.get(PR_TITLE_ENV, "")
    if title.strip():
        commands.append((cz, "check", "--message", squash_subject(title)))
    return CzCommands(tuple(commands))


def squash_subject(title: str) -> str:
    """``title`` without a leading GitLab draft marker, as the squash commit will read.

    A title that is nothing but the marker stays whole, so ``cz check`` still fails it.

    Example::

        >>> squash_subject("Draft: feat: add the recipe")
        'feat: add the recipe'
    """
    stripped = _DRAFT_PREFIX.sub("", title, count=1)
    return stripped if stripped.strip() else title


def run_cz_commands(
    checks: CzCommands, repo_root: Path, runner: CiStepRunner, timeout_s: float
) -> tuple[tuple[str, ...], StepRun]:
    """Run every check (no fail-fast) and fold them into one step result.

    The recorded argv is the first check's; each check's command line heads its
    output. A timeout ends the step as timed out.

    Example: ``run_cz_commands(checks, root, SubprocessCiStepRunner(), 600.0)[1].exit``.
    """
    from coding_agent_playbook.commands.twins.ci import StepRun

    if checks.error:
        return ("cz",), StepRun(1, f"{checks.error}\n")
    if not checks.commands:
        return (), StepRun(0, "no commit after the cut-over date to check\n")
    outputs: list[str] = []
    exit_code: int | None = 0
    for argv in checks.commands:
        result = runner.run(argv, cwd=repo_root, timeout_s=timeout_s)
        outputs.append(f"$ {shlex.join(argv)}\n{result.output}")
        if result.exit is None:
            return checks.commands[0], StepRun(None, "".join(outputs))
        if result.exit != 0 and exit_code == 0:
            exit_code = result.exit
    return checks.commands[0], StepRun(exit_code, "".join(outputs))
