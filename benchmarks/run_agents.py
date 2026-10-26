"""Phase 1 of the review benchmark: run OpenCode on every review sample, per experiment.

Each run materializes the sample's ``setup/`` with the engine's own
:func:`materialize`, drives OpenCode through the engine's ``OpenCodeRunner`` and
saves the prompt, transcript and working tree for phase 2 (``score_runs.py``),
which grades them. Splitting the phases lets the judge be re-run or swapped
without paying for the agent runs again. A finished run is skipped unless
``--force`` is given, so an interrupted batch resumes.

Usage::

    python benchmarks/run_agents.py --workers 3
    python benchmarks/run_agents.py --experiments playbook-v2 --samples review-spot-the-bug
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench

from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.run.agent_env import unattended_agent_env
from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner
from coding_agent_playbook.evals.run.harness_runner import AgentRun, materialize
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRunner

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner
    from coding_agent_playbook.evals.sample import EvalSample

#: Tool caches an agent may create while it inspects the code. Excluded so they
#: never show up in the captured diff (the judge grades the diff when there is one).
_CACHE_EXCLUDES = ("__pycache__/", ".pytest_cache/", ".ruff_cache/", ".mypy_cache/")


def opencode_command(experiment: _bench.Experiment, scratch: Path) -> list[str]:
    """The ``opencode run`` arg-list template for ``experiment`` (``{prompt}`` filled per run).

    ``--dir`` is required: OpenCode 1.19 takes its project directory from the
    inherited ``PWD``, not the process cwd, so without it the agent reviews the
    caller's checkout. ``--pure`` skips external OpenCode plugins.

    Example::

        opencode_command(_bench.experiment_by_key("opencode-review"), Path("/s"))[-3:]
        # ["--command", "review", "{prompt}"]
    """
    base = [
        _bench.OPENCODE_BIN, "run", "--pure",
        "--dir", str(scratch),
        "--model", _bench.AGENT_MODEL,
    ]  # fmt: skip
    if experiment.prompt_set is None:
        return [*base, "--command", "review", "{prompt}"]
    return [*base, "{prompt}"]


def claude_command() -> list[str]:
    """The ``claude -p`` arg-list template (``{prompt}`` filled per run).

    ``--bare`` keeps the developer's hooks, plugins, CLAUDE.md and auto-memory
    out of the run; built-in skills such as ``/code-review`` still resolve.
    ``--`` ends the options, so a prompt can never be read as a flag.

    Example::

        claude_command()[-2:]  # ["--", "{prompt}"]
    """
    return [
        _bench.CLAUDE_BIN, "-p", "--bare",
        "--model", _bench.CLAUDE_AGENT_MODEL,
        "--no-session-persistence",
        "--permission-mode", "acceptEdits",
        "--allowedTools", _bench.CLAUDE_ALLOWED_TOOLS,
        "--output-format", "text",
        "--", "{prompt}",
    ]  # fmt: skip


class OpenRouterClaudeRunner(ClaudeCodeRunner):
    """The engine's ``ClaudeCodeRunner``, with extra env for this run only.

    The extra env points Claude Code at OpenRouter; passing it per run (not
    through ``os.environ``) keeps it out of OpenCode runs in the same batch.
    """

    def __init__(
        self, *, command: Sequence[str], timeout: float, extra_env: Mapping[str, str]
    ) -> None:
        super().__init__(command=command, timeout=timeout)
        self._extra_env = dict(extra_env)

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        completed = subprocess.run(
            self._build_command(prompt),
            cwd=scratch_dir,
            env=unattended_agent_env({**os.environ, **self._extra_env}),
            capture_output=True,
            text=True,
            timeout=self._timeout,
            check=False,
        )
        return AgentRun(
            transcript=completed.stdout + completed.stderr, returncode=completed.returncode
        )


def build_runner(experiment: _bench.Experiment, scratch: Path, timeout: float) -> HarnessRunner:
    """The engine runner that drives ``experiment``'s harness in ``scratch``."""
    if experiment.harness == "claude":
        extra_env = _bench.claude_agent_env(_bench.require_env("OPENROUTER_API_KEY"))
        return OpenRouterClaudeRunner(
            command=claude_command(), timeout=timeout, extra_env=extra_env
        )
    return OpenCodeRunner(command=opencode_command(experiment, scratch), timeout=timeout)


def agent_prompt(experiment: _bench.Experiment, sample: EvalSample) -> str:
    """What the agent receives: the request for the built-in reviewer, or the playbook prompt.

    OpenCode's ``/review`` takes the request through ``--command review``;
    Claude Code's ``/code-review`` takes it as the slash command's arguments.
    """
    if experiment.prompt_set is not None:
        return render_prompt(sample, strict=True, prompt_set=experiment.prompt_set)
    if experiment.harness == "claude":
        return f"/code-review {sample.invocation.prompt_args}"
    return sample.invocation.prompt_args


def _exclude_caches(scratch: Path) -> None:
    exclude = scratch / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(_CACHE_EXCLUDES) + "\n")


def _decode(stream: bytes | str | None) -> str:
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode("utf-8", errors="replace")


def _invoke(runner: HarnessRunner, prompt: str, scratch: Path) -> tuple[AgentRun, bool]:
    """Run the agent once; ``(run, timed_out)``. A timeout keeps the partial output."""
    try:
        # The engine's own invocation (unattended env, arg-list, cwd=scratch).
        return runner._invoke_agent(prompt, scratch), False
    except subprocess.TimeoutExpired as exc:
        partial = _decode(exc.stdout) + _decode(exc.stderr)
        return AgentRun(transcript=partial, returncode=-1), True


def run_one(experiment: _bench.Experiment, sample: EvalSample, args: argparse.Namespace) -> str:
    """Run one experiment x sample and save its files; a one-line status."""
    out = _bench.run_dir(args.run_name, experiment.key, sample.id)
    if (out / "agent.json").is_file() and not args.force:
        return f"skip  {experiment.key:16} {sample.id}"
    scratch = _bench.scratch_dir(args.run_name, experiment.key, sample.id)
    for stale in (out, scratch.parent):
        if stale.exists():
            shutil.rmtree(stale)
    out.mkdir(parents=True)
    baseline = materialize(sample, scratch)
    _exclude_caches(scratch)
    prompt = agent_prompt(experiment, sample)
    runner = build_runner(experiment, scratch, args.timeout)
    started = monotonic()
    run, timed_out = _invoke(runner, prompt, scratch)
    duration = monotonic() - started
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    (out / "transcript.txt").write_text(_bench.strip_ansi(run.transcript), encoding="utf-8")
    meta = {
        "experiment": experiment.key,
        "sample_id": sample.id,
        "harness": experiment.harness,
        "model": _bench.CLAUDE_AGENT_MODEL
        if experiment.harness == "claude"
        else _bench.AGENT_MODEL,
        "command": list(runner._command),
        "returncode": run.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 1),
        "baseline_commit": baseline.commit,
        "scratch": str(scratch),
        "setup_snapshot": str(baseline.setup_snapshot),
    }
    (out / "agent.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    status = "TIMEOUT" if timed_out else f"rc={run.returncode}"
    return f"done  {experiment.key:16} {sample.id:42} {status} {duration:6.0f}s"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-name", default=_bench.DEFAULT_RUN_NAME)
    parser.add_argument("--experiments", nargs="*", default=[e.key for e in _bench.EXPERIMENTS])
    parser.add_argument("--samples", nargs="*", default=None, help="sample ids (default: all)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=_bench.AGENT_TIMEOUT_S)
    parser.add_argument("--force", action="store_true", help="re-run finished runs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    env_file = _bench.load_env_file()
    _bench.require_env("OPENROUTER_API_KEY")
    experiments = [_bench.experiment_by_key(k) for k in args.experiments]
    binaries = {"opencode": _bench.OPENCODE_BIN, "claude": _bench.CLAUDE_BIN}
    for harness in {e.harness for e in experiments}:
        if shutil.which(binaries[harness]) is None:
            raise RuntimeError(f"{binaries[harness]!r} is not on PATH (needed for {harness} runs)")
    _bench.drop_parent_session_env()
    os.environ.update(_bench.AGENT_ENV)
    samples = _bench.review_samples(args.samples)
    jobs = [(e, s) for e in experiments for s in samples]
    print(f"env: {env_file}  model: {_bench.AGENT_MODEL}  runs: {len(jobs)}", flush=True)
    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, e, s, args): (e, s) for e, s in jobs}
        for future in as_completed(futures):
            experiment, sample = futures[future]
            try:
                print(future.result(), flush=True)
            except Exception as exc:
                failures += 1
                print(f"FAIL  {experiment.key:16} {sample.id}: {exc!r}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
