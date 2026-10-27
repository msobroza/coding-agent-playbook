"""Shared setup for the review benchmark: experiments, paths, models and env loading.

Every hardcoded identifier the benchmark scripts use lives here, so a model or
path change is a one-line edit. The scripts import this module by path (they run
as ``python benchmarks/<script>.py`` from the repo root).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from coding_agent_playbook.evals.sample import EvalSample

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
BENCH_ROOT: Final = REPO_ROOT / "benchmarks"
RESULTS_ROOT: Final = BENCH_ROOT / "results"
DEFAULT_RUN_NAME: Final = "review-qwen3.6-27b"

#: Where the agents' working trees live: outside the repo on purpose. OpenCode
#: walks up from its directory for AGENTS.md/CLAUDE.md, and this checkout's own
#: rules files would otherwise leak into the eval.
WORK_ROOT: Final = Path(
    os.environ.get("BENCH_WORK_ROOT", Path.home() / ".cache" / "playbook-bench")
)

#: The agent under test: Qwen3.6 27B through OpenRouter, driven by OpenCode or Claude Code.
OPENCODE_BIN: Final = os.environ.get("OPENCODE_BIN", "opencode")
AGENT_MODEL: Final = "openrouter/qwen/qwen3.6-27b"
AGENT_TIMEOUT_S: Final = 900.0

#: Claude Code reaches the same model through OpenRouter's Anthropic-compatible
#: API. Every model alias (subagents, the small background model) maps to it, so
#: no Anthropic model is ever called.
CLAUDE_BIN: Final = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_AGENT_MODEL: Final = "qwen/qwen3.6-27b"
OPENROUTER_ANTHROPIC_BASE_URL: Final = "https://openrouter.ai/api"
#: Tools a reviewer needs: read the tree, run git, Python and the tests. Edits in
#: the scratch tree are allowed (as in OpenCode) and caught by the gate.
CLAUDE_ALLOWED_TOOLS: Final = (
    "Read,Grep,Glob,Task,Skill,"
    "Bash(git:*),Bash(python:*),Bash(python3:*),Bash(pytest:*),Bash(uv:*),Bash(ls:*)"
)

#: The judge: Opus 5.5 at medium effort, through the ``claude`` CLI.
JUDGE_MODEL: Final = "claude-opus-5-5"
JUDGE_EFFORT: Final = "medium"
JUDGE_TIMEOUT_S: Final = 180.0

#: The eval samples under test: every sample of the core ``review`` prompt.
REVIEW_PROMPT_ID: Final = "review"

#: Env for every agent run. NO_COLOR keeps escape codes out of the transcript;
#: OPENCODE_DISABLE_CLAUDE_CODE stops OpenCode 1.x from loading ~/.claude/CLAUDE.md
#: and ~/.claude/skills (the developer's own setup would leak into the eval);
#: PYTHONDONTWRITEBYTECODE keeps __pycache__ out of the captured diff.
AGENT_ENV: Final = {
    "NO_COLOR": "1",
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}

#: Variables a parent Claude Code session exports to its children. Inherited by
#: the judge's ``claude -p``, ANTHROPIC_BASE_URL and the session ids route its
#: requests through the parent app's account instead of the .env key (the API then
#: answered "credit balance is too low" while the key itself worked).
_SESSION_ENV_RE: Final = re.compile(r"^(ANTHROPIC_.*|CLAUDECODE|CLAUDE_.*)$")

#: What the loaded ``.env`` file itself sets, apart from the inherited environment.
_ENV_FILE_VALUES: dict[str, str] = {}

_ANSI_RE: Final = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ENV_LINE_RE: Final = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


@dataclass(frozen=True)
class Experiment:
    """One reviewer setup: a harness and what it reviews with.

    ``playbook_text`` ``None`` gives the harness's built-in reviewer the
    sample's request alone (OpenCode's ``/review``, Claude Code's
    ``/code-review``). Otherwise the agent gets the playbook's rendered
    ``review`` prompt, as ``playbook eval --run`` builds it: a release tag
    such as ``"v0.2.0"`` is that edition, and ``"head"`` is the checkout's
    current text (for a change not released yet).
    """

    key: str
    label: str
    playbook_text: str | None
    harness: str = "opencode"


#: Each harness's built-in reviewer, then the playbook's releases in order.
EXPERIMENTS: Final = (
    Experiment("opencode-review", "OpenCode /review", None),
    Experiment("opencode-playbook-v0.1.0", "OpenCode + playbook v0.1.0", "v0.1.0"),
    Experiment("opencode-playbook-v0.2.0", "OpenCode + playbook v0.2.0", "v0.2.0"),
    Experiment("opencode-playbook-v0.3.0", "OpenCode + playbook v0.3.0", "v0.3.0"),
    Experiment("claude-code-review", "Claude Code /code-review", None, harness="claude"),
    Experiment(
        "claude-playbook-v0.2.0", "Claude Code + playbook v0.2.0", "v0.2.0", harness="claude"
    ),
    Experiment(
        "claude-playbook-v0.3.0", "Claude Code + playbook v0.3.0", "v0.3.0", harness="claude"
    ),
)


def experiment_by_key(key: str) -> Experiment:
    """The :data:`EXPERIMENTS` entry named ``key``.

    Example::

        experiment_by_key("opencode-playbook-v0.1.0").playbook_text  # "v0.1.0"
    """
    for experiment in EXPERIMENTS:
        if experiment.key == key:
            return experiment
    known = ", ".join(e.key for e in EXPERIMENTS)
    raise KeyError(f"unknown experiment {key!r}; expected one of: {known}")


def load_env_file(start: Path = REPO_ROOT) -> Path:
    """Load the nearest ``.env`` at or above ``start`` into ``os.environ``.

    Values already set in the environment win. The worktree lives inside the main
    checkout, so walking up finds the main checkout's ``.env``.

    Example::

        load_env_file()  # Path(".../coding-agent-playbook/.env")
    """
    for folder in (start, *start.parents):
        candidate = folder / ".env"
        if candidate.is_file():
            _apply_env_lines(candidate.read_text(encoding="utf-8").splitlines())
            return candidate
    raise FileNotFoundError(f"no .env file at or above {start}")


def _apply_env_lines(lines: list[str]) -> None:
    for line in lines:
        match = _ENV_LINE_RE.match(line)
        if match is None or line.lstrip().startswith("#"):
            continue
        name, value = match.group(1), match.group(2).strip("'\"")
        _ENV_FILE_VALUES[name] = value
        os.environ.setdefault(name, value)


def env_file_value(name: str) -> str:
    """``name`` as the loaded ``.env`` file sets it, never an inherited value ('' when unset).

    A parent Claude Code session exports its own ``ANTHROPIC_*`` variables, so a
    key the benchmark must not take from the environment is read here instead.

    Example::

        env_file_value("ANTHROPIC_API_KEY")  # "sk-ant-..." or ""
    """
    return _ENV_FILE_VALUES.get(name, "")


def require_env(name: str) -> str:
    """The value of env var ``name``, or a clear error naming it."""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"env var {name} is empty; add it to .env")
    return value


def drop_parent_session_env() -> list[str]:
    """Remove a parent Claude Code session's variables from ``os.environ``; their names.

    Child processes (the agent, the judge) inherit ``os.environ``, so this keeps
    the developer's running session out of them.

    Example::

        drop_parent_session_env()  # ["ANTHROPIC_BASE_URL", "CLAUDECODE", ...]
    """
    names = sorted(name for name in os.environ if _SESSION_ENV_RE.match(name))
    for name in names:
        del os.environ[name]
    return names


#: Settings every Claude Code run gets through ``--settings`` (which still applies
#: when ``--setting-sources ""`` drops the developer's own settings files).
CLAUDE_ISOLATION_SETTINGS: Final = '{"autoMemoryEnabled": false}'


def claude_agent_env(openrouter_key: str, config_dir: Path) -> dict[str, str]:
    """The extra env that points Claude Code at Qwen through OpenRouter.

    Example::

        claude_agent_env("sk-or-...")["ANTHROPIC_BASE_URL"]  # "https://openrouter.ai/api"
    """
    model = CLAUDE_AGENT_MODEL
    return {
        "ANTHROPIC_BASE_URL": OPENROUTER_ANTHROPIC_BASE_URL,
        "ANTHROPIC_API_KEY": openrouter_key,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        # Qwen3.6 27B's real window; Claude Code does not know the model and would
        # otherwise assume 200k and print a notice on every run.
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "262144",
        # An empty config dir per run: no user CLAUDE.md, settings, plugins or hooks.
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    }


def strip_ansi(text: str) -> str:
    """``text`` without terminal escape sequences."""
    return _ANSI_RE.sub("", text)


def review_samples(only: list[str] | None = None) -> list[EvalSample]:
    """The engine's ``review`` eval samples, optionally narrowed to ``only`` ids.

    The task registry owns the walk of ``eval_samples/`` (#302); this asks it for
    the ``review`` task instead of filtering every sample by prompt id.

    Example::

        [s.id for s in review_samples(["review/spot-the-bug"])]
    """
    from coding_agent_playbook.evals.task_registry import TaskRegistry
    from coding_agent_playbook.validation.context import SyncContext

    ctx = SyncContext.from_repo(REPO_ROOT)
    registry = TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)
    samples = list(registry.samples_of(REVIEW_PROMPT_ID))
    if not only:
        return samples
    missing = sorted(set(only) - {s.id for s in samples})
    if missing:
        raise KeyError(f"not review samples: {missing}; have {[s.id for s in samples]}")
    return [s for s in samples if s.id in only]


def run_key(sample_id: str) -> str:
    """The one-level directory name of ``sample_id`` under a run's experiment dir.

    Sample ids are ``<task>/<name>`` since #302; flattening the slash keeps one
    directory per sample, so the runs recorded before #302 (``review-<name>``)
    and new runs share a layout.

    Example::

        run_key("review/spot-the-bug")  # "review-spot-the-bug"
    """
    return sample_id.replace("/", "-")


def run_dir(run_name: str, experiment_key: str, sample_id: str) -> Path:
    """Where one experiment x sample run keeps its results (prompt, transcript, scores)."""
    return RESULTS_ROOT / run_name / experiment_key / run_key(sample_id)


def scratch_dir(run_name: str, experiment_key: str, sample_id: str) -> Path:
    """The agent's working tree for one run, under :data:`WORK_ROOT`."""
    return WORK_ROOT / run_name / experiment_key / run_key(sample_id) / "scratch"
