"""Pick the CI test lane for a change: the skill lane or the full lane (ADR 0009).

A pull request whose changed paths are all skill content runs only the
``catalog``-marked tests (the skill lane); every other change runs the whole
suite (the full lane). The ``test`` jobs run this before their pytest step. It
prints the lane alone on stdout and a one-line reason on stderr, and picks the
full lane in every unclear case: not a pull request, the ``ci:full`` label, no
changed paths, a git error. Stdlib only, so it is cheap and import-safe in CI.

Usage::

    python -m tests.skill_lane --event pull_request --force-full false
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

type Lane = Literal["skill", "full"]
#: ``run_git(repo, args)`` runs ``git *args`` in ``repo``; a non-zero exit is returned, not raised.
type GitRunner = Callable[[Path, Sequence[str]], subprocess.CompletedProcess[str]]

#: The skill-content directories of ADR 0009. The trailing slash keeps a
#: look-alike such as ``tests/core_skills_extra/`` out of the skill lane.
SKILL_LANE_PREFIXES: Final = (
    "catalog/core/skills/",
    "tests/core_skills/",
    "tests/core_skill_pins/",
)
#: The skill-content files of ADR 0009 that live outside those directories.
SKILL_LANE_FILES: Final = frozenset({"catalog/core/ATTRIBUTIONS.md"})

#: HEAD is GitHub's pull-request merge commit and its first parent the base
#: branch (the checkout fetches depth 2). ``--no-renames`` lists both ends of a
#: rename, so moving a file out of the skill content selects the full lane.
_DIFF_ARGS: Final = ("diff", "--name-only", "--no-renames", "HEAD^1", "HEAD")
_GIT_TIMEOUT_S: Final = 30
_REPO_ROOT: Final = Path(__file__).resolve().parents[1]


def in_skill_lane(path: str) -> bool:
    """Say whether one repo-relative changed path is skill content (ADR 0009).

    A name git C-quotes (non-ASCII) starts with ``"``, so it falls to the full lane.

    Example::

        in_skill_lane("catalog/core/skills/python-coding/SKILL.md")  # True
    """
    return path in SKILL_LANE_FILES or path.startswith(SKILL_LANE_PREFIXES)


def lane_for(changed: Sequence[str]) -> tuple[Lane, str]:
    """Pick the lane for a pull request's changed paths, with a one-line reason.

    The skill lane needs at least one path, and every path must be skill content.

    Example::

        lane_for(["catalog/core/ATTRIBUTIONS.md"])  # ("skill", "1 changed path(s), ...")
    """
    if not changed:
        return "full", "no changed paths"
    outside = next((path for path in changed if not in_skill_lane(path)), None)
    if outside is not None:
        return "full", f"{outside} is outside the skill-lane paths"
    return "skill", f"{len(changed)} changed path(s), all skill content"


def run_git_subprocess(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run the real ``git *args`` in ``repo``: the default :data:`GitRunner`.

    Bounded by a timeout; a non-zero exit is returned for the caller to judge.

    Example::

        run_git_subprocess(Path("."), ["rev-parse", "HEAD"]).stdout
    """
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_S,
        check=False,
    )


def changed_paths(repo: Path, run_git: GitRunner = run_git_subprocess) -> list[str] | None:
    """List the paths a pull request changes, or ``None`` when git cannot tell.

    Diffs the merge commit ``HEAD`` against its first parent, the base branch.

    Example::

        changed_paths(Path("."))  # ["catalog/core/skills/x/SKILL.md"] on a skill-only PR
    """
    try:
        completed = run_git(repo, _DIFF_ARGS)
    except (OSError, ValueError, subprocess.SubprocessError):
        # A timeout, no git binary or undecodable output: unclear, so the
        # caller picks the full lane (ADR 0009) instead of failing the job.
        return None
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tests.skill_lane",
        description="Print the CI test lane (skill or full) for this run (ADR 0009).",
    )
    parser.add_argument("--event", required=True, help="the run's github.event_name")
    # A string, not a flag: the workflow passes its label expression's
    # true/false result verbatim.
    parser.add_argument(
        "--force-full",
        choices=("true", "false"),
        default="false",
        help="true when the pull request carries the ci:full label",
    )
    return parser


def _choose_lane(event: str, force_full: bool, repo: Path, run_git: GitRunner) -> tuple[Lane, str]:
    if event != "pull_request":
        return "full", f"event {event} is not pull_request"
    if force_full:
        return "full", "the ci:full label forces it"
    changed = changed_paths(repo, run_git)
    if changed is None:
        return "full", "could not list the changed paths (git diff HEAD^1 HEAD failed)"
    return lane_for(changed)


def main(
    argv: Sequence[str] | None = None,
    *,
    repo: Path | None = None,
    run_git: GitRunner = run_git_subprocess,
) -> int:
    """Print the lane on stdout and ``<lane> lane: <reason>`` on stderr; return 0.

    ``repo`` defaults to the checkout holding this file. Every decision returns
    0, so a lane question never fails the job; only a usage error exits 2.

    Example::

        main(["--event", "pull_request", "--force-full", "false"])  # prints skill or full
    """
    args = _parser().parse_args(argv)
    root = repo if repo is not None else _REPO_ROOT
    lane, reason = _choose_lane(args.event, args.force_full == "true", root, run_git)
    print(lane)
    print(f"{lane} lane: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
