#!/usr/bin/env python3
"""Prepare a release pull request from any worktree, and tag it once merged (#281, ADR 0012).

Run it from any checkout of the engine repository, in an environment with the
engine installed::

    uv run scripts/release.py prepare                  # next version from the commits
    uv run scripts/release.py prepare --version 0.1.0  # the first release, or an override
    uv run scripts/release.py prepare --eval           # plus release metrics (paid runs)
    uv run scripts/release.py tag                      # by hand, when CI could not tag
    uv run scripts/release.py freeze v0.1.0            # an edition and its pins, as a PR
    uv run scripts/release.py unfreeze v0.1.0          # the reverse, as a PR
    uv run scripts/release.py check-editions           # CI: editions equal their tags' blobs

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

With ``--eval`` (``release_eval``), step 3 first records the release metrics of
every ``[evals] release`` target into ``catalog/releases/<version>/metrics/``,
compares each with the previous release's file for the same target and refuses
the pull request on a regression no ``--accept SAMPLE=REASON`` accepted;
``--reuse-metrics DIR`` reuses the files a refused run kept.

Merging that pull request is the release; the ``tag-release`` CI job then tags
it, and ``tag`` does the same checks by hand (``release_tag``: the release
commit, never HEAD; its recorded base; green tests; tags never moved). A failed
run leaves no worktree, no local release branch and no change in the caller's
tree, and a re-run starts over from ``origin/main`` (it overwrites a release
branch a failed run pushed, with a lease). Exit codes: 0 done, 1 refused or
failed, 2 usage.

``freeze vX`` and ``unfreeze vX`` (``release_edition``) run the same way: a
scratch worktree at ``origin/main``, the checkout's own engine
(``freeze-checkout``), one commit on ``freeze/vX`` or ``unfreeze/vX``, pushed
with a lease, and a pull request opened (or the open one reused), so a re-run is
idempotent. ``check-editions`` runs in place, in the CI job with full history.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.prompting import PromptResolutionError
from coding_agent_playbook.evals.release_regression import RegressionCheckError, parse_acceptances
from coding_agent_playbook.release.changes import diff_entries, graded_set_changed
from coding_agent_playbook.release.manifest import (
    MANIFEST_FILENAME,
    NOTES_FILENAME,
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
from release_edition import (
    FREEZE,
    UNFREEZE,
    EditionChange,
    EditionRefusal,
    check_editions,
    edition_branch,
    freeze_change,
    unfreeze_change,
)
from release_eval import (
    EvalRequest,
    ReleaseTargets,
    metrics_body,
    metrics_kept_on_refusal,
    record_release_metrics,
    release_targets,
)
from release_tag import superseded, tag_release
from release_tools import COMMITIZEN_REQUIREMENT as COMMITIZEN_REQUIREMENT
from release_tools import (
    MAIN_BRANCH,
    REMOTE,
    Runner,
    Tools,
    commit_push_open,
    on_branch,
    refuse_foreign_engine,
)
from release_tools import Completed as Completed
from release_tools import ReleaseError as ReleaseError
from release_tools import run_process as run_process

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from release_eval import TargetMetrics

RELEASE_BRANCH_PREFIX: Final = "release/"
FAILED_EXIT: Final = 1
#: Bounds ``prepare-checkout --eval``: every release target's recording, then the PR.
PREPARE_EVAL_TIMEOUT_SECONDS: Final = 24 * 60 * 60
#: commitizen's exit codes for "no bump-worthy commit" and "no commit at all".
CZ_NO_INCREMENT: Final = 21
CZ_NO_COMMITS: Final = 3
_CATALOG: Final = "catalog"
_PYPROJECT: Final = "pyproject.toml"
_FIELD: Final = "\x1f"
_RECORD: Final = "\x1e"


# --------------------------------------------------------------------------- #
# prepare: the throwaway worktree around prepare-checkout
# --------------------------------------------------------------------------- #


def _make_scratch() -> Path:
    return Path(tempfile.mkdtemp(prefix="playbook-release-"))


def prepare(
    repo: Path,
    *,
    version: str | None,
    eval_flags: Sequence[str] = (),
    runner: Runner = run_process,
    make_scratch: Callable[[], Path] = _make_scratch,
) -> int:
    """Fetch, check ``origin/main`` out in a scratch worktree and run ``prepare-checkout`` there.

    ``eval_flags`` (``--eval`` and its options) pass through unchanged. The
    worktree is removed whatever happens, so the caller's repository keeps no
    trace of a failed run.
    """
    extra = [*(["--version", version] if version else []), *eval_flags]
    timeout = PREPARE_EVAL_TIMEOUT_SECONDS if eval_flags else None
    return _in_scratch_checkout(repo, "prepare-checkout", extra, runner, make_scratch, timeout)


def edition_command(
    repo: Path,
    command: str,
    tag: str,
    *,
    runner: Runner = run_process,
    make_scratch: Callable[[], Path] = _make_scratch,
) -> int:
    """``freeze``/``unfreeze`` ``tag``: ``<command>-checkout`` in a scratch worktree, like prepare."""
    return _in_scratch_checkout(repo, f"{command}-checkout", ["--tag", tag], runner, make_scratch)


def _in_scratch_checkout(
    repo: Path,
    inner: str,
    extra: list[str],
    runner: Runner,
    make_scratch: Callable[[], Path],
    timeout: float | None = None,
) -> int:
    """Run ``release.py <inner> --base <origin/main> <extra>`` in a throwaway worktree."""
    tools = Tools(runner, repo)
    tools.git("fetch", "--tags", REMOTE)
    base = tools.git("rev-parse", "--verify", f"{REMOTE}/{MAIN_BRANCH}^{{commit}}").strip()
    scratch = make_scratch()
    checkout = scratch / "checkout"
    try:
        tools.git("worktree", "add", "--detach", str(checkout), base)
        argv = _checkout_argv(checkout, inner, base, extra)
        done = runner(argv, cwd=checkout, env=_env(checkout), timeout=timeout)
    finally:
        tools.run(["git", "worktree", "remove", "--force", str(checkout)])
        tools.run(["git", "worktree", "prune"])
        shutil.rmtree(scratch, ignore_errors=True)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


def _checkout_argv(checkout: Path, inner: str, base: str, extra: list[str]) -> list[str]:
    script = checkout / "scripts" / Path(__file__).name
    return [sys.executable, str(script), inner, "--base", base, *extra]


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
    #: The release targets ``--eval`` records (``None``: no release metrics).
    targets: ReleaseTargets | None = None

    @property
    def branch(self) -> str:
        return f"{RELEASE_BRANCH_PREFIX}{release_tag(self.version)}"

    @property
    def title(self) -> str:
        return f"chore(release): {release_tag(self.version)}"


def prepare_checkout(
    tools: Tools,
    *,
    base: str,
    version: str | None,
    snapshot: Callable[[str], ReleaseManifest],
    evaluation: EvalRequest | None = None,
) -> str:
    """Plan the release in the checkout at ``tools.cwd``, then commit, push and open its PR.

    ``snapshot(base)`` builds the manifest of the checkout's catalog;
    ``evaluation`` (``--eval``) adds the release metrics first. Returns the pull
    request's URL as ``playbook forge`` prints it.
    """
    plan = plan_release(tools, base=base, version=version, snapshot=snapshot)
    if evaluation is not None:
        plan = dataclasses.replace(plan, targets=release_targets(tools.cwd))
    return on_branch(tools, base, plan.branch, lambda: _publish(tools, plan, evaluation))


def edition_checkout(tools: Tools, *, base: str, command: str, tag: str) -> str:
    """``freeze``/``unfreeze`` ``tag`` in the checkout at ``tools.cwd`` and open its PR."""
    _refuse_moved_head(tools, base)
    change_of = freeze_change if command == FREEZE else unfreeze_change
    branch = edition_branch(command, tag)

    def publish() -> str:
        change: EditionChange = change_of(tools, tag)
        with tempfile.TemporaryDirectory(prefix="playbook-edition-") as scratch:
            body = Path(scratch) / "body.md"
            body.write_text(change.body, encoding="utf-8")
            return commit_push_open(tools, branch, change.title, change.paths, body)

    return on_branch(tools, base, branch, publish)


def plan_release(
    tools: Tools, *, base: str, version: str | None, snapshot: Callable[[str], ReleaseManifest]
) -> Plan:
    """Run the preflight and decide the version; nothing is written yet."""
    _refuse_moved_head(tools, base)
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


def _refuse_moved_head(tools: Tools, base: str) -> None:
    head = tools.git("rev-parse", "HEAD").strip()
    if head != base:
        raise ReleaseError(f"the checkout is at {head}, not at the base {base}")


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


def _publish(tools: Tools, plan: Plan, evaluation: EvalRequest | None = None) -> str:
    """Record the release metrics, write the release files, bump, commit, push and open the PR.

    The metrics come first, so they grade the base's catalog before anything changes.
    """
    if plan.targets is None or evaluation is None:
        return _bump_and_open(tools, plan, None)
    metrics = record_release_metrics(
        tools,
        version=plan.version,
        previous=plan.previous,
        base=plan.manifest.base,
        targets=plan.targets,
        request=evaluation,
    )
    # on_branch discards the branch on a refusal: keep the paid recordings out of it.
    with metrics_kept_on_refusal(tools.cwd, plan.version, evaluation):
        return _bump_and_open(tools, plan, metrics)


def _bump_and_open(tools: Tools, plan: Plan, metrics: Sequence[TargetMetrics] | None) -> str:
    """Write the release files, bump the version, commit, push and open the PR."""
    notes = _write_release_files(tools, plan)
    bumped = tools.cz("bump", plan.version, "--version-files-only", "--yes")
    if bumped.returncode != 0:
        raise ReleaseError(
            f"`cz bump {plan.version}` exited {bumped.returncode}: {bumped.stderr.strip()}"
        )
    release_path = notes.parent.relative_to(tools.cwd).as_posix()
    paths = (_PYPROJECT, release_path)
    if metrics is None:
        return commit_push_open(tools, plan.branch, plan.title, paths, notes)
    with tempfile.TemporaryDirectory(prefix="playbook-release-body-") as scratch:
        body = Path(scratch) / "body.md"
        notes_text = notes.read_text(encoding="utf-8")
        body.write_text(f"{notes_text}\n{metrics_body(metrics)}", encoding="utf-8")
        return commit_push_open(tools, plan.branch, plan.title, paths, body)


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
    from coding_agent_playbook.catalog.roots import catalog_root
    from coding_agent_playbook.release.snapshot import build_manifest, shipped_source

    refuse_foreign_engine(checkout, "prepare-checkout")
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
    _add_eval_flags(prep)
    inner = commands.add_parser("prepare-checkout", help=argparse.SUPPRESS)
    inner.add_argument("--base", required=True)
    inner.add_argument("--version")
    _add_eval_flags(inner)
    tag = commands.add_parser("tag", help="tag the merged release commit (CI does it on push)")
    tag.add_argument(
        "--tested-commit",
        metavar="SHA",
        help="the CI tag job's commit, whose tests passed: tag only it, skip the CI lookup",
    )
    for name, what in ((FREEZE, "freeze edition TAG"), (UNFREEZE, "unfreeze edition TAG")):
        commands.add_parser(name, help=f"open a PR to {what}").add_argument("tag", metavar="TAG")
        hidden = commands.add_parser(f"{name}-checkout", help=argparse.SUPPRESS)
        hidden.add_argument("--base", required=True)
        hidden.add_argument("--tag", required=True)
    commands.add_parser("check-editions", help="CI: every edition file equals its tag's blob")
    return parser


def _add_eval_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--eval",
        action="store_true",
        dest="record_metrics",
        help="record the release metrics of every [evals] release target (paid runs) and "
        "refuse the PR on an unaccepted regression",
    )
    parser.add_argument(
        "--accept",
        metavar="SAMPLE=REASON",
        action="append",
        default=[],
        help="--eval: accept SAMPLE's regression, storing REASON in the metrics (repeatable)",
    )
    parser.add_argument(
        "--reuse-metrics",
        metavar="DIR",
        type=Path,
        help="--eval: reuse the metrics files a refused run kept in DIR, recorded on the same base",
    )


def _eval_request(args: argparse.Namespace) -> EvalRequest | None:
    """The ``--eval`` request ``args`` carry; refuses its options without ``--eval``."""
    if not args.record_metrics:
        if args.accept or args.reuse_metrics is not None:
            raise ReleaseError("--accept and --reuse-metrics belong to --eval; pass --eval too")
        return None
    try:
        accepted = parse_acceptances(args.accept)
    except RegressionCheckError as exc:
        raise ReleaseError(str(exc)) from exc
    reuse = None if args.reuse_metrics is None else args.reuse_metrics.resolve()
    return EvalRequest(accepted=accepted, reuse=reuse)


def _eval_flags(request: EvalRequest | None) -> list[str]:
    """``request`` as the flags ``prepare`` passes on to ``prepare-checkout``."""
    if request is None:
        return []
    flags = ["--eval"]
    for sample_id, reason in request.accepted.items():
        flags += ["--accept", f"{sample_id}={reason}"]
    return flags if request.reuse is None else [*flags, "--reuse-metrics", str(request.reuse)]


def main(
    argv: Sequence[str] | None = None,
    *,
    cwd: Path | None = None,
    runner: Runner = run_process,
    snapshot: Callable[[str], ReleaseManifest] | None = None,
    engine_guard: Callable[[Path, str], None] = refuse_foreign_engine,
) -> int:
    """Run ``release.py``; returns the exit code (argparse exits 2 on a usage error).

    ``engine_guard(checkout, command)`` runs before ``freeze-checkout`` and
    ``unfreeze-checkout`` write anything (``prepare-checkout``'s default
    snapshot runs the same guard).
    """
    args = _parser().parse_args(argv)
    here = Path.cwd() if cwd is None else cwd
    try:
        return _dispatch(args, Tools(runner, here), snapshot, engine_guard)
    # ValueError: a bad manifest, digests file, sample or graded set, each naming its file.
    except (ReleaseError, EditionRefusal, TagRefusal, PromptResolutionError, ValueError) as exc:
        print(f"release: {exc}", file=sys.stderr)
        return FAILED_EXIT


def _dispatch(
    args: argparse.Namespace,
    tools: Tools,
    snapshot: Callable[[str], ReleaseManifest] | None,
    engine_guard: Callable[[Path, str], None],
) -> int:
    command: str = args.command
    if command == "prepare":
        flags = _eval_flags(_eval_request(args))
        return prepare(tools.cwd, version=args.version, eval_flags=flags, runner=tools.runner)
    if command in (FREEZE, UNFREEZE):
        return edition_command(tools.cwd, command, args.tag, runner=tools.runner)
    if command == "tag":
        print(f"release: {tag_release(tools, tested_commit=args.tested_commit)}")
        return 0
    if command == "check-editions":
        return _report_editions(check_editions(tools))
    if command == "prepare-checkout":
        build = _default_snapshot(tools.cwd) if snapshot is None else snapshot
        url = prepare_checkout(
            tools,
            base=args.base,
            version=args.version,
            snapshot=build,
            evaluation=_eval_request(args),
        )
    else:
        engine_guard(tools.cwd, command)
        name = command.removesuffix("-checkout")
        url = edition_checkout(tools, base=args.base, command=name, tag=args.tag)
    print(f"release: opened {url}")
    return 0


def _report_editions(problems: list[str]) -> int:
    for problem in problems:
        print(f"release: {problem}", file=sys.stderr)
    if problems:
        return FAILED_EXIT
    print("release: every edition file equals its tag's blob")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
