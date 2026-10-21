"""Run the full pytest suite as numbered chunks whose coverage adds up, then apply CI's threshold.

Why: the suite takes 20+ minutes, over the 10-minute limit of one agent command.
Coverage data stays in ./.coverage at the worktree root, as in CI: exporting
COVERAGE_FILE leaks into the nested pytest runs that some tests start, and they
overwrote the combined data in wave 1. The chunk table lives here so agent
commands carry no globs or shell variables (the worktree guard rejects them).

Usage, from the worktree root, with the worktree's overlay python::

    <python> suite_chunk.py check    # every collected test file is in exactly one chunk
    <python> suite_chunk.py 1        # chunk 1 erases old coverage data; 2..12 append
    <python> suite_chunk.py report   # --fail-under=80 on the combined data, src only
"""

from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path

CHUNKS: dict[int, list[str]] = {
    1: [
        "tests/adapters",
        "tests/agent_harness",
        "tests/architecture",
        "tests/artifacts",
        "tests/catalog",
    ],
    2: ["tests/cli/test_[a-r]*.py"],
    3: ["tests/cli/test_[s-z]*.py"],
    4: ["tests/config", "tests/detector", "tests/evals", "tests/generated_output"],
    5: ["tests/grading", "tests/hooks"],
    6: ["tests/hook_runtime/handlers"],
    7: ["tests/hook_runtime/dispatch", "tests/hook_runtime/harness", "tests/hook_runtime/config"],
    8: [
        "tests/hook_runtime/shell",
        "tests/hook_runtime/judges",
        "tests/hook_runtime/state",
        "tests/hook_runtime/diagnostics",
        "tests/hook_runtime/stop",
        "tests/hook_runtime/git",
        "tests/hook_runtime/test_*.py",
    ],
    9: ["tests/integration"],
    10: [
        "tests/lockfile",
        "tests/metrics_gate",
        "tests/rendering",
        "tests/security",
        "tests/skills",
        "tests/sync",
        "tests/validation",
    ],
    11: ["tests/plugins"],
    12: ["tests/unit"],
}
# pyproject addopts minus the per-chunk report and fail-under ([tool.pytest.ini_options]).
PYTEST_OPTS = [
    "-o",
    "addopts=",
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--cov=coding_agent_playbook",
    "--cov-append",
    "--cov-report=",
    "-q",
    "-p",
    "no:cacheprovider",
]


def expand(patterns: list[str]) -> list[str]:
    """Each pattern's matches, or the pattern itself when it is a plain path."""
    return sorted(
        m for p in patterns for m in (glob.glob(p) if any(c in p for c in "*?[") else [p])
    )


def run_chunk(number: int) -> int:
    """Run one chunk; chunk 1 first erases the coverage data of an earlier run."""
    if number not in CHUNKS:
        raise SystemExit(f"chunk must be 1..{len(CHUNKS)}, check or report, got: {number}")
    if number == 1:
        for stale in Path(".").glob(".coverage*"):
            stale.unlink()
    return subprocess.call([sys.executable, "-m", "pytest", *PYTEST_OPTS, *expand(CHUNKS[number])])


def report() -> int:
    """CI's threshold over the package source only (temp projects some tests measure are skipped)."""
    include = f"--include={Path.cwd() / 'src'}/*"
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            "--fail-under=80",
            "-i",
            include,
            "--skip-covered",
            "--sort=cover",
        ]
    )


def check() -> int:
    """Fail when a collected test file is in no chunk or in several."""
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
            "tests",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    files = sorted({line.split("::", 1)[0] for line in out.splitlines() if "::" in line})
    owned = {n: expand(p) for n, p in CHUNKS.items()}
    owners = {
        f: [n for n, ps in owned.items() if any(f == p or f.startswith(p + "/") for p in ps)]
        for f in files
    }
    bad = {f: o for f, o in owners.items() if len(o) != 1}
    for f, o in bad.items():
        print(f"{f}: in chunks {o or 'none'}; expected exactly one")
    print(f"{len(files)} collected test files, {len(bad)} not in exactly one chunk")
    return 1 if bad or not files else 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit(__doc__)
    mode = argv[1]
    if mode == "check":
        return check()
    if mode == "report":
        return report()
    return run_chunk(int(mode))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
