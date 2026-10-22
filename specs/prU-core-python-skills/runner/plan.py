"""prU planner: ticket status, runner arguments per machine, tracker body and worktree cleanup.

Reads the ticket graph from ``tickets.md``, issue numbers from ``ticket-issues.json`` and
the machine split from ``assignment.json``; a ticket is integrated when a commit whose
subject ends with ``(#<issue>)`` is on ``origin/integration/core-python-skills``.
Stdlib only, Python 3.10+. Run from the repository root:

    python3 specs/prU-core-python-skills/runner/plan.py status [--machine B]
    python3 specs/prU-core-python-skills/runner/plan.py args --machine B --parallel 6 \\
        --scratch /abs/scratch --shared-venv /abs/venv > /abs/scratch/args.json
    python3 specs/prU-core-python-skills/runner/plan.py args --full-gate ... > args.json
    python3 specs/prU-core-python-skills/runner/plan.py tracker-body --current now.md > new.md
    python3 specs/prU-core-python-skills/runner/plan.py cleanup [--apply] [--idle-minutes 0]

The spec files are read from origin's integration branch, so a pushed reassignment
applies on both machines at once; --local reads this checkout instead.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SPEC_DIR = "specs/prU-core-python-skills"
BASE = "integration/core-python-skills"
ID = r"(?:L0|C|D|F)-[\w-]+"
GIT_TIMEOUT_S = 120


@dataclass
class Ticket:
    """One ticket of the graph, with its state on origin."""

    id: str
    title: str
    deps: list[str]
    issue: int
    integrated: bool = False
    pushed: bool = False
    machine: str = ""
    blocked_by: list[str] = field(default_factory=list)
    priority: int = 0


def git(*args: str) -> str:
    """Output of one git command; raises with the command and stderr when it fails."""
    done = subprocess.run(
        ["git", *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S, check=False
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def parse_tickets(text: str, issues: dict[str, int]) -> dict[str, Ticket]:
    """Every ticket in tickets.md: '### <id>: <title>' sections and the content table rows."""
    found: dict[str, Ticket] = {}
    head = re.compile(rf"^### ({ID}): (.+)\n\nLane [^\n]*?depends on ([^;\n]*)", re.M)
    for m in head.finditer(text):
        found[m[1]] = Ticket(m[1], m[2].strip(), re.findall(ID, m[3]), issues.get(m[1], 0))
    row = re.compile(rf"^\| ({ID}) \| ([^|]+) \| [^|]* \| ([^|]*) \|$", re.M)
    for m in row.finditer(text):
        found[m[1]] = Ticket(m[1], m[2].strip(), re.findall(ID, m[3]), issues.get(m[1], 0))
    missing = sorted(t.id for t in found.values() if not t.issue)
    unknown = sorted({d for t in found.values() for d in t.deps if d not in found})
    if missing or unknown:
        raise SystemExit(
            f"tickets without an issue number: {missing}; unknown dependencies: {unknown}"
        )
    check_acyclic(found)
    return found


def check_acyclic(tickets: dict[str, Ticket]) -> None:
    """Fail on a dependency cycle: the runner's scheduler would wait on it forever."""
    state: dict[str, int] = {}  # 1 = on the current path, 2 = finished

    def visit(tid: str, path: list[str]) -> None:
        if state.get(tid) == 2:
            return
        if state.get(tid) == 1:
            raise SystemExit(f"dependency cycle: {' -> '.join([*path, tid])}")
        state[tid] = 1
        for dep in tickets[tid].deps:
            visit(dep, [*path, tid])
        state[tid] = 2

    for tid in tickets:
        visit(tid, [])


def lane_of(ticket_id: str) -> str:
    """'C-web-application-03' -> 'web-application'; engine, docs and final tickets are their own lane."""
    if not ticket_id.startswith("C-"):
        return ticket_id
    return re.sub(r"-(\d\d|refs|example)$", "", ticket_id[2:])


def assign(tickets: dict[str, Ticket], assignment: dict) -> None:
    """Set each ticket's machine from assignment.json (explicit ids win over lanes)."""
    for machine, spec in assignment["machines"].items():
        for t in tickets.values():
            if lane_of(t.id) in spec.get("lanes", []):
                t.machine = machine
    for machine, spec in assignment["machines"].items():
        for tid in spec.get("tickets", []):
            tickets[tid].machine = machine
    for tid in assignment.get("orchestrator_only", []):
        tickets[tid].machine = "orchestrator"


def load_state(tickets: dict[str, Ticket], assignment: dict) -> None:
    """Mark integrated and pushed tickets from origin; compute what blocks the rest."""
    subjects = git("log", "--format=%s", f"origin/{BASE}")
    merged = {int(n) for n in re.findall(r"\(#(\d+)\)\s*$", subjects, re.M)}
    heads = git("ls-remote", "origin", "refs/heads/ticket/*")
    pushed = {line.rsplit("/", 1)[-1] for line in heads.splitlines() if line.strip()}
    for t in tickets.values():
        t.integrated = t.issue in merged or t.id in assignment.get("integrated_without_squash", [])
        t.pushed = t.id in pushed and not t.integrated
    for t in tickets.values():
        t.blocked_by = [d for d in t.deps if not tickets[d].integrated]


def set_priorities(tickets: dict[str, Ticket]) -> None:
    """Priority = how many unfinished tickets wait on a ticket, directly or not.

    The runner starts and integrates the highest first, so the chain that unblocks the
    most work (the other machine's included) never queues behind a leaf ticket.
    """
    children: dict[str, set[str]] = {tid: set() for tid in tickets}
    for t in tickets.values():
        for dep in t.deps:
            children[dep].add(t.id)
    below: dict[str, set[str]] = {}

    def descendants(tid: str) -> set[str]:
        if tid not in below:
            below[tid] = set().union(*({c} | descendants(c) for c in children[tid]))
        return below[tid]

    for t in tickets.values():
        t.priority = sum(1 for d in descendants(t.id) if not tickets[d].integrated)


def read_spec(rel: str, local: bool) -> str:
    """A prU spec file from origin's integration branch (or this checkout with --local).

    Reading origin means a reassignment pushed by either machine applies at once,
    without pulling.
    """
    if local:
        return (REPO_ROOT / SPEC_DIR / rel).read_text(encoding="utf-8")
    return git("show", f"origin/{BASE}:{SPEC_DIR}/{rel}")


def load(args: argparse.Namespace) -> tuple[dict[str, Ticket], dict, dict]:
    git("fetch", "-q", "origin", BASE)
    meta = json.loads(read_spec("runner/ticket-issues.json", args.local))
    assignment = json.loads(read_spec("runner/assignment.json", args.local))
    tickets = parse_tickets(read_spec("tickets.md", args.local), meta["issues"])
    assign(tickets, assignment)
    load_state(tickets, assignment)
    set_priorities(tickets)
    return tickets, assignment, meta


def cmd_status(args: argparse.Namespace) -> int:
    tickets, _, _ = load(args)
    rows = [t for t in tickets.values() if not args.machine or t.machine == args.machine]
    for state, pick in (
        ("integrated", lambda t: t.integrated),
        ("ready", lambda t: not t.integrated and not t.blocked_by),
        ("waiting", lambda t: not t.integrated and t.blocked_by),
    ):
        group = [t for t in rows if pick(t)]
        print(f"{state} ({len(group)}):")
        for t in sorted(group, key=lambda t: t.id):
            extra = f" waits for {', '.join(t.blocked_by)}" if state == "waiting" else ""
            flag = " [branch pushed]" if t.pushed else ""
            head = f"  {t.id:28} #{t.issue:<4} machine {t.machine or '-'} priority {t.priority:<3}"
            print(f"{head}{flag}{extra}")
    return 0


def find_skill(skills_dir: str | None, name: str) -> tuple[str, str]:
    """(text, path) of the installed mattpocock-skills engineering skill ``name``."""
    if skills_dir:
        path = Path(skills_dir) / name / "SKILL.md"
    else:
        root = Path.home() / ".claude/plugins/cache/mattpocock/mattpocock-skills"
        versions = sorted(root.glob("*/skills/engineering"), key=lambda p: _version(p.parts[-3]))
        if not versions:
            raise SystemExit(f"mattpocock-skills is not installed under {root}; pass --skills-dir")
        path = versions[-1] / name / "SKILL.md"
    if not path.is_file():
        raise SystemExit(f"skill file not found: {path}")
    return path.read_text(encoding="utf-8"), str(path)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text))


def body_without_frontmatter(text: str) -> str:
    """The skill body after its '---' frontmatter block, stripped."""
    parts = text.split("---\n", 2)
    return parts[2].strip() if text.startswith("---\n") and len(parts) == 3 else text.strip()


def cmd_args(args: argparse.Namespace) -> int:
    tickets, _, meta = load(args)
    if args.full_gate:
        chosen: list[Ticket] = []
    elif args.only:
        chosen = [tickets[i] for i in args.only.split(",")]
    else:
        chosen = [t for t in tickets.values() if t.machine == args.machine and not t.integrated]
    integrate_only = set(filter(None, (args.integrate_only or "").split(",")))
    unpushed = sorted(i for i in integrate_only if not tickets[i].pushed)
    if unpushed:
        raise SystemExit(f"--integrate-only needs a pushed ticket branch; none for: {unpushed}")
    implement, implement_path = find_skill(args.skills_dir, "implement")
    review, review_path = find_skill(args.skills_dir, "code-review")
    out = {
        "machine": args.machine or "-",
        "repo": meta["repo"],
        "base": BASE,
        "parallel": args.parallel,
        "fullGate": args.full_gate,
        "paths": {
            "orchestratorCheckout": str(Path.cwd()),
            "scratch": args.scratch,
            "sharedVenv": args.shared_venv,
            "tools": "specs/prU-core-python-skills/runner/tools",
        },
        "skills": {
            "implement": body_without_frontmatter(implement),
            "codeReview": review,
            "sources": [implement_path, review_path],
        },
        "done": sorted(t.id for t in tickets.values() if t.integrated),
        "tickets": [
            {
                "id": t.id,
                "issue": t.issue,
                "title": t.title,
                "deps": t.deps,
                "existingBranch": t.pushed,
                "priority": t.priority,
                **({"startAt": "integrate"} if t.id in integrate_only else {}),
            }
            for t in sorted(chosen, key=lambda t: t.id)
        ],
    }
    json.dump(out, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


def cmd_tracker_body(args: argparse.Namespace) -> int:
    """The current tracker body with every integrated ticket ticked (idempotent)."""
    tickets, _, _ = load(args)
    body = Path(args.current).read_text(encoding="utf-8")
    for t in tickets.values():
        if t.integrated:
            body = re.sub(rf"^- \[ \] #{t.issue} ", f"- [x] #{t.issue} ", body, flags=re.M)
    sys.stdout.write(body)
    return 0


def keep_reason(path: str, head: str, idle_s: float) -> str | None:
    """Why a workflow worktree must stay, or None when removing it loses nothing."""
    gitdir = Path(git("-C", path, "rev-parse", "--absolute-git-dir").strip())
    marks = [gitdir / f for f in ("HEAD", "index") if (gitdir / f).exists()]
    if marks and time.time() - max(m.stat().st_mtime for m in marks) < idle_s:
        return "used recently: an agent may still be working there"
    if not head or not git("branch", "-r", "--contains", head).strip():
        return "HEAD not on origin"
    changed = [line[3:] for line in git("-C", path, "status", "--porcelain").splitlines()]
    unsaved = [f for f in changed if not pushed_somewhere(path, f)]
    return f"uncommitted changes not on origin: {', '.join(unsaved[:3])}" if unsaved else None


def pushed_somewhere(path: str, rel: str) -> bool:
    """Whether the worktree's copy of ``rel`` equals that file in a commit on an origin branch.

    A worktree whose branch moved (another agent pushed from elsewhere) shows the older
    commit's files as changes; that content is already on origin, so nothing is lost.
    """
    file = Path(path) / rel
    if not file.is_file():
        return False
    blob = git("-C", path, "hash-object", str(file)).strip()
    history = git("-C", path, "log", "--remotes=origin", "--format=%H", "-n", "200", "--", rel)
    for commit in history.split():
        shown = subprocess.run(
            ["git", "-C", path, "rev-parse", f"{commit}:{rel}"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
        if shown.stdout.strip() == blob:
            return True
    return False


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Remove workflow worktrees that are idle and hold nothing unpushed; dry run unless --apply.

    Run it when no runner is active on this machine: an agent's fresh worktree is clean.
    """
    git("fetch", "-q", "origin")
    for block in git("worktree", "list", "--porcelain").split("\n\n"):
        fields = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        path, head = fields.get("worktree", ""), fields.get("HEAD", "")
        if "/.claude/worktrees/wf_" not in path:
            continue
        reason = keep_reason(path, head, args.idle_minutes * 60)
        print(f"keep   {path} ({reason})" if reason else f"remove {path}")
        if args.apply and not reason:
            git("worktree", "remove", "--force", path)
    if args.apply:
        git("worktree", "prune")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--local", action="store_true", help="read the spec files from this checkout, not origin"
    )
    status = sub.add_parser("status", parents=[shared])
    status.add_argument("--machine")
    gen = sub.add_parser("args", parents=[shared])
    gen.add_argument("--machine", default="")
    gen.add_argument("--only", help="comma-separated ticket ids instead of the machine's share")
    gen.add_argument("--parallel", type=int, default=3)
    gen.add_argument("--scratch", required=True, help="absolute scratch dir outside the checkout")
    gen.add_argument("--shared-venv", required=True, help="absolute path of the shared venv")
    gen.add_argument("--skills-dir", help="dir holding implement/ and code-review/ SKILL.md")
    gen.add_argument("--full-gate", action="store_true", help="no tickets: run the full suite")
    gen.add_argument(
        "--integrate-only",
        help="comma-separated ids whose pushed branch was already reviewed and fixed: integrate it",
    )
    tracker = sub.add_parser("tracker-body", parents=[shared])
    tracker.add_argument("--current", required=True)
    clean = sub.add_parser("cleanup")
    clean.add_argument("--apply", action="store_true")
    clean.add_argument("--idle-minutes", type=float, default=60, help="0 right after a run ends")
    args = parser.parse_args(argv[1:])
    handlers = {"status": cmd_status, "args": cmd_args, "tracker-body": cmd_tracker_body}
    return {**handlers, "cleanup": cmd_cleanup}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
