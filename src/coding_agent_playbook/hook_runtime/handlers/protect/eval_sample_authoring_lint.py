"""eval-sample-authoring-lint: parse and trial-compile an edited eval sample (specs/prK-hook-pack.md §E.1).

After an Edit or Write of ``**/eval_samples/<id>/sample.toml`` or its
``setup/pyproject.toml`` (the matcher keeps it inert in repos without
``eval_samples/``), it:

1. parses ``sample.toml`` with ``tomllib``; an escape error adds the hint
   ``author regex patterns as TOML literal strings (single quotes); \\s is an
   invalid escape in a basic string``;
2. trial-compiles **that one sample** in-process: ``evals.loader`` then
   ``evals.validator.validate_samples`` (unknown refs, unbound ``expr``
   identifiers, rubric weights, verdicts, ``answer_matches`` regexes, setup
   files and ``prompt_id``), keeping only
   errors anchored at this sample. Prompts come from ``FileSystemArtifactSource``
   (engine, ``overlays_enabled`` from ``protected.resource_roots``, the sample's
   own layer — ``catalog/core/``, ``catalog/plugins/<name>/`` or an overlay
   checkout's ``resources/`` — and repo-local). Errors are context, not a block: a
   sample written before its setup files is normal;
3. on the first clean compile per sample per session, echoes ``playbook eval
   --show <id>`` (a child process: ``commands.eval`` imports jinja2), capped
   at 25 lines, so the model sees how the engine read gate, rubric and verdict.

It never runs ``playbook eval --run`` (real runners, the LLM judge). The
``evals.*`` and ``catalog.source`` (yaml) imports are a §D.1 branch-local
row: only an eval-sample edit loads them. Fails open.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.path_classes import sample_path
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, quote_data
from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout
from coding_agent_playbook.hook_runtime.dispatch.registry import register_hook_handler
from coding_agent_playbook.hook_runtime.handlers.protect._source_changed import (
    DEBOUNCE_S,
    MAX_FAIL_LINES,
    context_result,
    run_playbook,
)

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext

__all__ = ["ESCAPE_HINT", "MAX_SHOW_LINES", "eval_sample_authoring_lint"]

ESCAPE_HINT: Final = (
    "author regex patterns as TOML literal strings (single quotes); "
    "\\s is an invalid escape in a basic string"
)
MAX_SHOW_LINES: Final = 25
#: The sample files whose edit re-lints the sample, below its directory.
_LINTED: Final = frozenset({"sample.toml", "setup/pyproject.toml"})
_REPO_LOCAL: Final = "<repo-local>"
_RESOURCE_ID: Final = re.compile(r"pkg:(?P<package>[\w.]+)/resources")
_LINE_CHARS: Final = 240


@register_hook_handler(
    "eval_sample_authoring_lint",
    events=["post_tool_use"],
    decisions=["context", "none"],
)
def eval_sample_authoring_lint(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Context with the edited sample's parse/compile errors, or its ``--show`` echo once.

    Example::

        >>> eval_sample_authoring_lint(write_of_sample_with_bad_escape, ctx).context[0]
        ... # doctest: +SKIP
        'Eval sample "demo" does not compile; resolve before finishing:\\n"sample.toml: ..."'
    """
    edited = _edited_sample(ev)
    if edited is None or ev.repo is None:
        return None
    sample_dir, rel_dir = edited
    if not ctx.session.debounce(f"{ctx.hook.id}:{rel_dir}", DEBOUNCE_S):
        return None
    root = ev.repo.worktree_root
    sample, problems = _lint(sample_dir, root, ctx.cfg)
    name = sample.id if sample is not None else sample_dir.name
    if problems:
        head = f"Eval sample {quote_data(name)} does not compile; resolve before finishing:"
        lines = [_problem_line(p) for p in problems[:MAX_FAIL_LINES]]
        return context_result(ctx, "\n".join([head, *lines]), "compile")
    if sample is None or not ctx.session.once(f"eval-show:{rel_dir}"):
        return None
    return _show(ctx, root, sample.id)


def _edited_sample(ev: CanonicalEvent) -> tuple[Path, str] | None:
    """``(absolute sample dir, repo-relative sample dir)`` of the first linted sample file written."""
    for path in ev.tool.write_paths if ev.tool is not None else ():
        where = sample_path(path.repo_rel) if path.repo_rel is not None else None
        if where is not None and where.rest in _LINTED:
            return Path(path.path[: -len(where.rest) - 1]), where.sample_dir
    return None


def _lint(sample_dir: Path, root: str, cfg: GuardConfig) -> tuple[EvalSample | None, list[str]]:
    """The sample (when it loads) and every problem anchored at it."""
    toml = sample_dir / "sample.toml"
    problems = _toml_problems(toml)
    if problems:
        return None, problems
    from coding_agent_playbook.evals.loader import load_eval_sample_from_dir  # branch-local

    try:
        sample = load_eval_sample_from_dir(sample_dir, source_package=_label(sample_dir, root))
    except (FileNotFoundError, ValueError) as exc:
        return None, [str(exc).replace(f"{toml}: ", "sample.toml: ")]
    return sample, _compile_problems(sample, _prompts(sample_dir, root, cfg))


def _toml_problems(toml: Path) -> list[str]:
    """Why ``sample.toml`` does not parse (with the escape hint), or ``[]``."""
    import tomllib  # branch-local (§D.1): an eval-sample edit only

    try:
        tomllib.loads(toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return _parse_problems(str(exc))
    except (OSError, UnicodeDecodeError) as exc:
        return [f"sample.toml cannot be read: {type(exc).__name__}"]
    return []


def _compile_problems(sample: EvalSample, prompts: list[Prompt] | None) -> list[str]:
    """The validator's errors anchored at ``sample``; the prompt rules only when prompts loaded."""
    from coding_agent_playbook.evals.validator import validate_samples  # branch-local

    errors = validate_samples([sample], prompts or [])
    anchored = [e.message for e in errors if e.path == sample.source_path]
    if prompts is None:
        return [message for message in anchored if not message.startswith("prompt")]
    return anchored


def _problem_line(problem: str) -> str:
    """A problem quoted as data; the engine's own hint stays plain text."""
    return problem if problem == ESCAPE_HINT else quote_data(clean_text(problem), _LINE_CHARS)


def _parse_problems(message: str) -> list[str]:
    problems = [f"sample.toml: malformed TOML: {message}"]
    if "Unescaped '\\'" in message or "escape" in message.lower():
        problems.append(ESCAPE_HINT)
    return problems


def _label(sample_dir: Path, root: str) -> str:
    """The layer label validate gives the sample: ``<repo-local>`` or its package dir name."""
    layer = sample_dir.parent.parent
    return _REPO_LOCAL if layer == Path(root) / "playbook" else layer.parent.name


def _prompts(sample_dir: Path, root: str, cfg: GuardConfig) -> list[Prompt] | None:
    """Every layer's prompts (later layers win by id in the validator), or ``None`` on failure."""
    from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
    from coding_agent_playbook.catalog.source import FileSystemArtifactSource

    packages = _layer_packages(cfg) or [ENGINE_PACKAGE]
    layer = sample_dir.parent.parent
    extra = () if _label(sample_dir, root) == _REPO_LOCAL else (layer,)
    source = FileSystemArtifactSource(
        repo_root=Path(root),
        engine_package=packages[0],
        overlay_packages=packages[1:],
        extra_resource_roots=extra,
    )
    try:
        return source.list_prompts()
    except Exception:  # a malformed prompt: validate-then-sync reports it; lint the schema only
        return None


def _layer_packages(cfg: GuardConfig) -> list[str]:
    """The engine then the overlays, from ``protected.resource_roots`` (``pkg:<p>/resources``)."""
    found = (_RESOURCE_ID.fullmatch(root) for root in cfg.tables.protected().resource_roots)
    return [match["package"] for match in found if match is not None]


def _show(ctx: HandlerContext, root: str, sample_id: str) -> HandlerResult | None:
    """``playbook eval --show <id>``'s first lines as context; nothing when it cannot run."""
    try:
        shown = run_playbook(ctx, root, ["eval", "--show", sample_id])
    except ProcTimeout:
        return None  # the echo is a convenience: no note, the compile already passed
    if shown is None or not shown.ok:
        return None
    text = shown.stdout.decode("utf-8", errors="replace")
    lines = [
        quote_data(clean_text(line), _LINE_CHARS) for line in text.splitlines() if line.strip()
    ]
    if not lines:
        return None
    head = (
        f"How the engine reads eval sample {quote_data(sample_id)} "
        f"(playbook eval --show, first {MAX_SHOW_LINES} lines):"
    )
    return context_result(ctx, "\n".join([head, *lines[:MAX_SHOW_LINES]]), "show")
