"""Phase 1 of the review benchmark: run OpenCode on every review sample, per experiment.

Each run materializes the sample's ``setup/`` with the engine's own
:func:`materialize`, drives OpenCode through the engine's ``OpenCodeRunner`` and
saves the prompt, transcript and working tree for phase 2 (``score_runs.py``),
which grades them. Splitting the phases lets the judge be re-run or swapped
without paying for the agent runs again. A finished run is skipped unless
``--force`` is given, so an interrupted batch resumes.

Usage::

    python benchmarks/run_agents.py --workers 3
    python benchmarks/run_agents.py --experiments playbook-v2 --samples review/spot-the-bug
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

from coding_agent_playbook.catalog.roots import catalog_root
from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.run.agent_env import unattended_agent_env
from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner
from coding_agent_playbook.evals.run.harness_runner import AgentRun, materialize
from coding_agent_playbook.evals.run.opencode_output import parse_opencode_output
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRunner
from coding_agent_playbook.release.edition import load_edition
from coding_agent_playbook.release.edition_digests import edition_dir

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
    caller's checkout. ``--pure`` skips external OpenCode plugins. ``--format
    json`` is the engine's own default: its events carry the tool calls too.

    Example::

        opencode_command(_bench.experiment_by_key("opencode-review"), Path("/s"))[-3:]
        # ["--command", "review", "{prompt}"]
    """
    base = [
        _bench.OPENCODE_BIN, "run", "--pure",
        "--dir", str(scratch),
        "--model", _bench.AGENT_MODEL,
        "--format", "json",
    ]  # fmt: skip
    if experiment.playbook_text is None:
        return [*base, "--command", "review", "{prompt}"]
    return [*base, "{prompt}"]


def claude_command(experiment: _bench.Experiment) -> list[str]:
    """The ``claude -p`` arg-list template (``{prompt}`` filled per run).

    Not ``--bare``: in bare mode Claude Code offers the model neither the Task
    (subagent) nor the Skill tool, so the v2 review's first-pass subagent and the
    wrapped ``/code-review`` could never run. Isolation comes instead from an
    empty ``CLAUDE_CONFIG_DIR`` per run (see ``claude_agent_env``), no setting
    sources, no MCP servers and auto-memory off. ``--`` ends the options, so a
    prompt can never be read as a flag.

    Example::

        claude_command(_bench.experiment_by_key("claude-playbook-v2"))[-2:]  # ["--", "{prompt}"]
    """
    return [
        _bench.CLAUDE_BIN, "-p",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--settings", _bench.CLAUDE_ISOLATION_SETTINGS,
        "--model", _bench.CLAUDE_AGENT_MODEL,
        "--no-session-persistence",
        "--permission-mode", "acceptEdits",
        "--allowedTools", _bench.CLAUDE_ALLOWED_TOOLS,
        "--output-format", "stream-json", "--verbose",
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
        #: The main loop's tool calls in the last run, e.g. ``["Read", "Skill:code-review"]``.
        self.tool_calls: list[str] = []

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
        answer, self.tool_calls = parse_stream_json(completed.stdout)
        transcript = completed.stdout if answer is None else answer
        if answer is None or completed.returncode != 0:
            # stderr only explains a failure; on success it holds just a model notice.
            transcript += completed.stderr
        return AgentRun(transcript=transcript, returncode=completed.returncode)


class ToolLoggingOpenCodeRunner(OpenCodeRunner):
    """The engine's ``OpenCodeRunner``, keeping the main session's tool calls as well.

    The engine reads only the text and the token totals from OpenCode's JSON
    events; the benchmark also needs the tool calls, to tell whether a review
    started both of its first passes.
    """

    def __init__(self, *, command: Sequence[str], timeout: float) -> None:
        super().__init__(command=command, timeout=timeout)
        #: The main session's tool calls in the last run, e.g. ``["read", "task:explore"]``.
        self.tool_calls: list[str] = []

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        completed = subprocess.run(
            self._build_command(prompt),
            cwd=scratch_dir,
            env=unattended_agent_env(),
            capture_output=True,
            text=True,
            timeout=self._timeout,
            check=False,
        )
        self.tool_calls = opencode_tool_calls(completed.stdout)
        output = parse_opencode_output(completed.stdout)
        transcript = completed.stdout if output is None else output.text
        return AgentRun(transcript=transcript + completed.stderr, returncode=completed.returncode)


def opencode_tool_calls(stdout: str) -> list[str]:
    """The main session's tool calls in ``opencode run --format json`` output.

    A ``task`` call is named with its subagent type, as :func:`parse_stream_json`
    names Claude Code's. Subagents' own calls are not in this stream.

    Example::

        opencode_tool_calls(out)  # ["read", "task:explore", "task:explore"]
    """
    calls: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = event.get("part") if isinstance(event, dict) else None
        if event.get("type") != "tool_use" or not isinstance(part, dict):
            continue
        state = part.get("state")
        given = state.get("input") if isinstance(state, dict) else None
        calls.append(_call_name({"name": part.get("tool"), "input": given}))
    return calls


def parse_stream_json(stdout: str) -> tuple[str | None, list[str]]:
    """The final answer and the main loop's tool calls from ``claude -p`` stream-JSON output.

    A Skill or Task call is named with its skill or subagent type. Subagents' own
    calls (events with a ``parent_tool_use_id``) are left out.

    Example::

        parse_stream_json(out)  # ("Findings: ...", ["Read", "Skill:code-review", "Task:Plan"])
    """
    answer: str | None = None
    calls: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            answer = event.get("result")
        elif event.get("type") == "assistant" and not event.get("parent_tool_use_id"):
            blocks = event.get("message", {}).get("content", [])
            calls += [_call_name(b) for b in blocks if b.get("type") == "tool_use"]
    return answer, calls


def _call_name(block: dict[str, object]) -> str:
    given = block.get("input")
    inputs = given if isinstance(given, dict) else {}
    detail = inputs.get("skill") or inputs.get("subagent_type")
    return f"{block['name']}:{detail}" if detail else str(block["name"])


#: Tool calls that start a subagent: Claude Code's Agent (Task in older builds), OpenCode's task.
_SUBAGENT_TOOLS = ("Agent", "Task", "task")


def second_pass_ran(experiment: _bench.Experiment, tool_calls: Sequence[str]) -> bool | None:
    """Whether the run started the bug-only pass its prompt asks for; None when none is asked.

    The current review text asks for two first passes: the ``code-review`` skill
    (Claude Code) or a second subagent beside the first. The ``code-review`` prototype asks for the
    skill alone.

    Example::

        second_pass_ran(_bench.experiment_by_key("playbook-v2"), ["task:explore"] * 2)  # True
    """
    if experiment.playbook_text != "head":
        return None
    if "Skill:code-review" in tool_calls:
        return True
    if experiment.first_pass == "code-review":
        return False
    return sum(call.split(":")[0] in _SUBAGENT_TOOLS for call in tool_calls) >= 2


def build_runner(experiment: _bench.Experiment, scratch: Path, timeout: float) -> HarnessRunner:
    """The engine runner that drives ``experiment``'s harness in ``scratch``."""
    if experiment.harness == "claude":
        config_dir = scratch.parent / "claude-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        extra_env = _bench.claude_agent_env(_bench.require_env("OPENROUTER_API_KEY"), config_dir)
        return OpenRouterClaudeRunner(
            command=claude_command(experiment), timeout=timeout, extra_env=extra_env
        )
    return ToolLoggingOpenCodeRunner(command=opencode_command(experiment, scratch), timeout=timeout)


#: v2's first pass (steps 1-2) as the prototype rewrites it: Claude Code's built-in
#: /code-review finds candidates, and v2's own steps 5 onwards verify, rate and
#: write the verdict. Everything else in the prompt is unchanged.
_NATIVE_FIRST_PASS = """1. Before you read the diff or open any file under review, run Claude Code's built-in `/code-review` as the first pass: invoke the Skill tool with the skill `code-review` and, as its arguments, the user's request exactly as written. Run it once, in the foreground, and wait for its findings. Never pass `--fix` or `--comment`: the first pass changes nothing.
2. When its findings arrive, skip steps 3-4 and go to step 5. Treat each finding as a candidate, not a conclusion: it may be wrong, a duplicate or outside the change, and step 5 checks it against the lines it cites. Do not read the diff or the reviewed files yourself, except the lines a finding cites. If the skill cannot be started, or it fails or returns no usable findings, do steps 3-4 yourself.
"""
_FIRST_PASS_START = "1. Before you read the diff or open any file under review"
_FIRST_PASS_END = "3. Collect the stated intent"


def native_first_pass(rendered: str) -> str:
    """``rendered`` (the v2 review prompt) with its first pass run by ``/code-review``.

    Raises :class:`ValueError` when the prompt no longer has the two anchors, so a
    reworded v2 prompt fails loudly instead of silently running the plain v2.

    Example::

        native_first_pass(v2_text).count("/code-review")  # 1
    """
    start, end = rendered.find(_FIRST_PASS_START), rendered.find(_FIRST_PASS_END)
    if start < 0 or end <= start:
        raise ValueError(
            f"v2 prompt lacks the first-pass anchors {_FIRST_PASS_START!r} / {_FIRST_PASS_END!r}"
        )
    return rendered[:start] + _NATIVE_FIRST_PASS + rendered[end:]


def agent_prompt(experiment: _bench.Experiment, sample: EvalSample) -> str:
    """What the agent receives: the request for the built-in reviewer, or the playbook prompt.

    OpenCode's ``/review`` takes the request through ``--command review``;
    Claude Code's ``/code-review`` takes it as the slash command's arguments.
    """
    if not experiment.runnable:
        raise ValueError(f"{experiment.key} is a recorded prototype; the review now ships its pass")
    if experiment.playbook_text == "head":
        rendered = render_prompt(sample, strict=True)
        return native_first_pass(rendered) if experiment.first_pass == "code-review" else rendered
    if experiment.playbook_text is not None:
        edition = load_edition(edition_dir(catalog_root(), experiment.playbook_text))
        return render_prompt(sample, strict=True, edition=edition)
    if experiment.harness == "claude":
        return f"/code-review {sample.invocation.prompt_args}"
    return sample.invocation.prompt_args


def _exclude_caches(scratch: Path) -> None:
    exclude = scratch / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(_CACHE_EXCLUDES) + "\n")


def _drop_venvs(*trees: Path) -> None:
    """Delete the ``uv sync`` venvs of a finished run: tens of MB each, unused by scoring.

    Scoring a review sample reads the tree and the git diff only (no tests run);
    a sample whose ``[metrics]`` runs tests needs ``--keep-venvs``.
    """
    for tree in trees:
        shutil.rmtree(tree / ".venv", ignore_errors=True)


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
        "main_loop_tools": getattr(runner, "tool_calls", None),
        "second_pass_ran": second_pass_ran(experiment, getattr(runner, "tool_calls", [])),
    }
    (out / "agent.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    if not args.keep_venvs:
        _drop_venvs(scratch, baseline.setup_snapshot)
    status = "TIMEOUT" if timed_out else f"rc={run.returncode}"
    return f"done  {experiment.key:16} {sample.id:42} {status} {duration:6.0f}s"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-name", default=_bench.DEFAULT_RUN_NAME)
    parser.add_argument(
        "--experiments", nargs="*", default=[e.key for e in _bench.EXPERIMENTS if e.runnable]
    )
    parser.add_argument("--samples", nargs="*", default=None, help="sample ids (default: all)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=_bench.AGENT_TIMEOUT_S)
    parser.add_argument("--force", action="store_true", help="re-run finished runs")
    parser.add_argument(
        "--keep-venvs",
        action="store_true",
        help="keep each run's .venv (needed only by samples whose metrics run tests)",
    )
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
