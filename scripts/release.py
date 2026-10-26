#!/usr/bin/env python3
"""Prepare a release pull request from any worktree, and tag it once merged (#281, ADR 0012).

Run it from any checkout of the engine repository, in an environment with the
engine installed::

    uv run scripts/release.py prepare                  # next version from the commits
    uv run scripts/release.py prepare --version 0.1.0  # the first release, or an override
    uv run scripts/release.py tag                      # by hand, when CI could not tag

``prepare`` fetches ``origin`` with its tags and works in a throwaway detached
worktree at ``origin/main``, so the caller's tree is never touched. There it
re-runs itself (``prepare-checkout``) on that checkout's own engine, which:

1. refuses unless the tag of the current ``[project]`` version exists (otherwise
   that release is merged but not tagged) and no release pull request is open;
   with no release tag at all it is the first release and needs ``--version``;
   an untagged release whose base moved under its pull request is superseded,
   never tagged: ``--version`` releases over it, from the last release tag;
2. takes the next version from commitizen over the Conventional Commits since
   that tag, raised to at least a minor when the graded set's digests changed;
3. writes ``catalog/releases/<version>/manifest.toml`` and ``notes.md``
   (``coding_agent_playbook.release``), sets the version with
   ``cz bump <version> --version-files-only`` (never a tag), commits
   ``chore(release): v<version>`` on ``release/v<version>``, pushes it and opens
   the pull request through ``playbook forge`` (ADR 0003).

Merging that pull request is the release; the ``tag-release`` CI job then tags
it, and ``tag`` does the same checks by hand (``release_tag``: the release
commit, never HEAD; its recorded base; green tests; tags never moved). A failed
run leaves no worktree, no local release branch and no change in the caller's
tree, and a re-run starts over from ``origin/main`` (it overwrites a release
branch a failed run pushed, with a lease). Exit codes: 0 done, 1 refused or
failed, 2 usage.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.release.changes import diff_entries, graded_set_changed
from coding_agent_playbook.release.graded_set import GradedSetError
from coding_agent_playbook.release.manifest import (
    MANIFEST_FILENAME,
    NOTES_FILENAME,
    ManifestError,
    ReleaseManifest,
    read_manifest,
    release_dir,
    render_manifest,
)
from coding_agent_playbook.release.notes import CommitMessage, pull_requests, render_notes
from coding_agent_playbook.release.tagging import TagRefusal
from coding_agent_playbook.release.versions import (
    VersionError,
    check_next_version,
    is_release_tag,
    raises_minor,
    release_tag,
)
from release_tag import superseded, tag_release

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

#: The commitizen this script runs, and the range the playbook-ci job installs.
COMMITIZEN_REQUIREMENT: Final = "commitizen>=4.13,<5"
REMOTE: Final = "origin"
MAIN_BRANCH: Final = "main"
RELEASE_BRANCH_PREFIX: Final = "release/"
FAILED_EXIT: Final = 1
#: commitizen's exit codes for "no bump-worthy commit" and "no commit at all".
CZ_NO_INCREMENT: Final = 21
CZ_NO_COMMITS: Final = 3
#: Bounds every shell-out: git, uv, commitizen and the forge CLI all run unattended.
COMMAND_TIMEOUT_SECONDS: Final = 600
_CATALOG: Final = "catalog"
_PYPROJECT: Final = "pyproject.toml"
_FIELD: Final = "\x1f"
_RECORD: Final = "\x1e"


class ReleaseError(Exception):
    """A refusal or a failed step; the message says what to do."""


@dataclass(frozen=True)
class Completed:
    """What a finished command returned."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    """Runs one command; the tests pass a named fake."""

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
    ) -> Completed: ...


def run_process(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
) -> Completed:
    """Run ``argv`` in ``cwd`` with a timeout; a missing program exits 127."""
    try:
        done = subprocess.run(
            list(argv),
            cwd=cwd,
            env=None if env is None else dict(env),
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return Completed(127, "", f"{argv[0]}: command not found")
    except subprocess.TimeoutExpired:
        return Completed(124, "", f"{argv[0]}: timed out after {COMMAND_TIMEOUT_SECONDS}s")
    return Completed(done.returncode, done.stdout, done.stderr)


@dataclass(frozen=True)
class Tools:
    """git, commitizen and ``playbook forge``, run in ``cwd`` through ``runner``."""

    runner: Runner
    cwd: Path

    def run(self, argv: Sequence[str]) -> Completed:
        return self.runner(argv, cwd=self.cwd)

    def checked(self, argv: Sequence[str]) -> str:
        """Run ``argv``; its stdout, or a :class:`ReleaseError` naming it and its stderr."""
        done = self.run(argv)
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip()
            raise ReleaseError(f"`{' '.join(argv)}` exited {done.returncode}: {detail}")
        return done.stdout

    def git(self, *args: str) -> str:
        return self.checked(["git", *args])

    def cz(self, *args: str) -> Completed:
        return self.run(["uv", "tool", "run", "--from", COMMITIZEN_REQUIREMENT, "cz", *args])

    def forge(self, *args: str) -> str:
        cli = [sys.executable, "-m", "coding_agent_playbook.cli", "forge", "-C", str(self.cwd)]
        return self.checked([*cli, *args])


# --------------------------------------------------------------------------- #
# prepare: the throwaway worktree around prepare-checkout
# --------------------------------------------------------------------------- #


def prepare(
    repo: Path,
    *,
    version: str | None,
    runner: Runner = run_process,
    make_scratch: Callable[[], Path] = lambda: Path(tempfile.mkdtemp(prefix="playbook-release-")),
) -> int:
    """Fetch, check ``origin/main`` out in a scratch worktree and run ``prepare-checkout`` there.

    The worktree is removed whatever happens, so the caller's repository keeps
    no trace of a failed run.
    """
    tools = Tools(runner, repo)
    tools.git("fetch", "--tags", REMOTE)
    base = tools.git("rev-parse", "--verify", f"{REMOTE}/{MAIN_BRANCH}^{{commit}}").strip()
    scratch = make_scratch()
    checkout = scratch / "checkout"
    try:
        tools.git("worktree", "add", "--detach", str(checkout), base)
        done = runner(_checkout_argv(checkout, base, version), cwd=checkout, env=_env(checkout))
    finally:
        tools.run(["git", "worktree", "remove", "--force", str(checkout)])
        tools.run(["git", "worktree", "prune"])
        shutil.rmtree(scratch, ignore_errors=True)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


def _checkout_argv(checkout: Path, base: str, version: str | None) -> list[str]:
    script = checkout / "scripts" / Path(__file__).name
    argv = [sys.executable, str(script), "prepare-checkout", "--base", base]
    return [*argv, "--version", version] if version else argv


def _env(checkout: Path) -> dict[str, str]:
    """The environment with the checkout's ``src`` first, so its own engine runs."""
    paths = [str(checkout / "src"), os.environ.get("PYTHONPATH", "")]
    return {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in paths if path)}


# --------------------------------------------------------------------------- #
# prepare-checkout: everything that happens inside the scratch checkout
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Plan:
    """What a release run decided before it writes anything."""

    previous: str | None
    version: str
    manifest: ReleaseManifest
    previous_manifest: ReleaseManifest | None

    @property
    def branch(self) -> str:
        return f"{RELEASE_BRANCH_PREFIX}{release_tag(self.version)}"

    @property
    def title(self) -> str:
        return f"chore(release): {release_tag(self.version)}"


def prepare_checkout(
    tools: Tools, *, base: str, version: str | None, snapshot: Callable[[str], ReleaseManifest]
) -> str:
    """Plan the release in the checkout at ``tools.cwd``, then commit, push and open its PR.

    ``snapshot(base)`` builds the manifest of the checkout's catalog. Returns the
    pull request's URL as ``playbook forge`` prints it.
    """
    plan = plan_release(tools, base=base, version=version, snapshot=snapshot)
    tools.git("switch", "--force-create", plan.branch)
    try:
        return _publish(tools, plan)
    finally:
        tools.run(["git", "switch", "--detach", "--discard-changes", base])
        tools.run(["git", "branch", "--delete", "--force", plan.branch])


def plan_release(
    tools: Tools, *, base: str, version: str | None, snapshot: Callable[[str], ReleaseManifest]
) -> Plan:
    """Run the preflight and decide the version; nothing is written yet."""
    head = tools.git("rev-parse", "HEAD").strip()
    if head != base:
        raise ReleaseError(f"the checkout is at {head}, not at the base {base}")
    current = _project_version(tools.cwd)
    previous = _previous_release(tools, current, base, version)
    _refuse_open_release_pull(tools)
    previous_manifest = None if previous is None else _manifest_of(tools.cwd, previous)
    manifest = snapshot(base)
    graded_changed = graded_set_changed(previous_manifest, manifest)
    chosen = _choose_version(tools, current, previous, version, graded_changed)
    _refuse_existing_tag(tools, chosen)
    return Plan(
        previous=previous,
        version=chosen,
        manifest=dataclasses.replace(manifest, version=chosen),
        previous_manifest=previous_manifest,
    )


def _refuse_existing_tag(tools: Tools, version: str) -> None:
    tag = release_tag(version)
    if tools.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"]).returncode == 0:
        raise ReleaseError(f"tag {tag} already exists: pick another --version")


def _project_version(checkout: Path) -> str:
    project = tomllib.loads((checkout / _PYPROJECT).read_text(encoding="utf-8"))["project"]
    return str(project["version"])


def _previous_release(tools: Tools, current: str, base: str, version: str | None) -> str | None:
    """The version of the last release, or ``None`` for the first; refuses an untagged one.

    An untagged ``current`` whose release commit lost its base (main moved under
    its pull request, ``release_tag.superseded``) is never tagged: with an explicit
    ``version`` the release goes over it, from the last release tag.
    """
    tags = tools.git("tag", "--list", "v*").split()
    tag = release_tag(current)
    if tag in tags:
        if tools.run(["git", "merge-base", "--is-ancestor", tag, base]).returncode != 0:
            raise ReleaseError(f"tag {tag} is not an ancestor of {REMOTE}/{MAIN_BRANCH} ({base})")
        return current
    if not any(is_release_tag(name) for name in tags):
        return None
    reason = superseded(tools, current, base)
    if reason is None:
        raise ReleaseError(
            f"release {tag} is merged but not tagged: tag it first, then re-run prepare "
            f"(the version in {_PYPROJECT} is {current} and no tag {tag} exists)"
        )
    if version is None:
        # cz finds no tag for the current version and would count every commit since
        # the start of history, so the version over a superseded release is explicit.
        raise ReleaseError(
            f"release {tag} is superseded ({reason}): pass --version, higher than {current}, "
            "for the release over it"
        )
    return _last_release(tools, base)


def _last_release(tools: Tools, base: str) -> str:
    """The version of the newest final release tag merged into ``base``."""
    merged = tools.git("tag", "--list", "v*", "--merged", base, "--sort=-v:refname").split()
    final = next((name for name in merged if is_release_tag(name)), None)
    if final is None:
        raise ReleaseError(
            f"no final release tag is an ancestor of {REMOTE}/{MAIN_BRANCH} ({base})"
        )
    return final.removeprefix("v")


def _refuse_open_release_pull(tools: Tools) -> None:
    pulls = json.loads(tools.forge("pr", "list", "--state", "open") or "[]")
    for pull in pulls:
        head = str(pull.get("head", ""))
        if head.startswith(RELEASE_BRANCH_PREFIX):
            raise ReleaseError(
                f"release pull request #{pull.get('number')} ({head}) is still open: "
                "merge or close it before preparing another release"
            )


def _manifest_of(checkout: Path, version: str) -> ReleaseManifest:
    path = release_dir(checkout / _CATALOG, version) / MANIFEST_FILENAME
    if not path.is_file():
        raise ReleaseError(f"release {version} has no manifest at {path}")
    return read_manifest(path)


def _choose_version(
    tools: Tools, current: str, previous: str | None, version: str | None, graded_changed: bool
) -> str:
    try:
        if version is not None:
            return check_next_version(current, version)
        if previous is None:
            raise ReleaseError(
                f"no release tag exists yet: pass --version for the first release ({current} now)"
            )
        return check_next_version(current, _next_version(tools, current, graded_changed))
    except VersionError as exc:
        raise ReleaseError(str(exc)) from exc


def _next_version(tools: Tools, current: str, graded_changed: bool) -> str:
    """commitizen's next version, raised to a minor when the graded set changed."""
    proposed = _cz_next(tools)
    if graded_changed and (proposed is None or not raises_minor(current, proposed)):
        proposed = _cz_next(tools, "--increment", "MINOR")
    if proposed is None:
        raise ReleaseError(
            f"nothing to release: no feat, fix or breaking commit since {release_tag(current)} "
            "and the graded set is unchanged"
        )
    return proposed


def _cz_next(tools: Tools, *extra: str) -> str | None:
    done = tools.cz("bump", "--get-next", "--yes", *extra)
    if done.returncode in (CZ_NO_INCREMENT, CZ_NO_COMMITS):
        return None
    if done.returncode != 0:
        raise ReleaseError(f"`cz bump --get-next` exited {done.returncode}: {done.stderr.strip()}")
    lines = done.stdout.split()
    if not lines:
        raise ReleaseError("`cz bump --get-next` printed no version")
    return lines[-1]


def _publish(tools: Tools, plan: Plan) -> str:
    """Write the release files, bump, commit, push and open the pull request."""
    notes = _write_release_files(tools, plan)
    bumped = tools.cz("bump", plan.version, "--version-files-only", "--yes")
    if bumped.returncode != 0:
        raise ReleaseError(
            f"`cz bump {plan.version}` exited {bumped.returncode}: {bumped.stderr.strip()}"
        )
    release_path = notes.parent.relative_to(tools.cwd).as_posix()
    tools.git("add", "--", _PYPROJECT, release_path)
    tools.git("commit", "--quiet", "--message", plan.title)
    leftover = tools.git("status", "--porcelain").strip()
    if leftover:
        raise ReleaseError(f"the release commit left changes behind:\n{leftover}")
    tools.git("push", "--force-with-lease", REMOTE, f"HEAD:refs/heads/{plan.branch}")
    url = tools.forge(
        "pr", "create", "--base", MAIN_BRANCH, "--title", plan.title, "--body-file", str(notes)
    )
    return url.strip()


def _write_release_files(tools: Tools, plan: Plan) -> Path:
    """Write the manifest and the notes; returns the notes' path."""
    target = release_dir(tools.cwd / _CATALOG, plan.version)
    target.mkdir(parents=True, exist_ok=True)
    (target / MANIFEST_FILENAME).write_text(render_manifest(plan.manifest), encoding="utf-8")
    changes = (
        None
        if plan.previous_manifest is None
        else diff_entries(plan.previous_manifest.artifacts, plan.manifest.artifacts)
    )
    pulls = pull_requests(_commits(tools, plan))
    notes_text = render_notes(plan.version, previous=plan.previous, changes=changes, pulls=pulls)
    notes = target / NOTES_FILENAME
    notes.write_text(notes_text, encoding="utf-8")
    return notes


def _commits(tools: Tools, plan: Plan) -> list[CommitMessage]:
    """The first-parent commits since the previous release tag (all history for the first)."""
    span = (
        plan.manifest.base
        if plan.previous is None
        else f"{release_tag(plan.previous)}..{plan.manifest.base}"
    )
    log = tools.git("log", "--first-parent", f"--format=%s{_FIELD}%b{_RECORD}", span)
    commits = []
    for record in log.split(_RECORD):
        subject, _, body = record.strip("\n").partition(_FIELD)
        if subject:
            commits.append(CommitMessage(subject, body))
    return commits


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _default_snapshot(checkout: Path) -> Callable[[str], ReleaseManifest]:
    """The manifest builder of the checkout's own engine; refuses any other engine."""
    import coding_agent_playbook
    from coding_agent_playbook.catalog.roots import catalog_root
    from coding_agent_playbook.release.snapshot import build_manifest, shipped_source

    engine = Path(coding_agent_playbook.__file__).resolve()
    if not engine.is_relative_to((checkout / "src").resolve()):
        raise ReleaseError(f"prepare-checkout imported the engine from {engine}, not {checkout}")
    catalog = catalog_root()

    def snapshot(base: str) -> ReleaseManifest:
        source = shipped_source(checkout, catalog)
        return build_manifest(source, catalog, version="0", base=base)

    return snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="open the next release pull request")
    prep.add_argument("--version", help="the version to release (required for the first)")
    inner = commands.add_parser("prepare-checkout", help=argparse.SUPPRESS)
    inner.add_argument("--base", required=True)
    inner.add_argument("--version")
    tag = commands.add_parser("tag", help="tag the merged release commit (CI does it on push)")
    tag.add_argument(
        "--tested-commit",
        metavar="SHA",
        help="the CI tag job's commit, whose tests passed: tag only it, skip the CI lookup",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    cwd: Path | None = None,
    runner: Runner = run_process,
    snapshot: Callable[[str], ReleaseManifest] | None = None,
) -> int:
    """Run ``release.py``; returns the exit code (argparse exits 2 on a usage error)."""
    args = _parser().parse_args(argv)
    here = Path.cwd() if cwd is None else cwd
    try:
        if args.command == "prepare":
            return prepare(here, version=args.version, runner=runner)
        if args.command == "tag":
            print(f"release: {tag_release(Tools(runner, here), tested_commit=args.tested_commit)}")
            return 0
        build = _default_snapshot(here) if snapshot is None else snapshot
        url = prepare_checkout(
            Tools(runner, here), base=args.base, version=args.version, snapshot=build
        )
    except (ReleaseError, ManifestError, GradedSetError, TagRefusal) as exc:
        print(f"release: {exc}", file=sys.stderr)
        return FAILED_EXIT
    print(f"release: opened {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
