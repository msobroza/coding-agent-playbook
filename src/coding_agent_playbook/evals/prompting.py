"""Render an eval task's prompt the way ``playbook sync`` renders it.

The runner drives an agent with the task's prompt, so that prompt must be the
one a consumer actually gets: the Jinja context carries the detector facts plus
project metadata. Rendering with a bare environment instead crashed 7 of the 20
shipped tasks with ``UndefinedError`` (``rule`` for the review prompts, before
D15 removed that helper, and ``project_name`` for generate-tests) before any
agent ran.

The runner hands the agent the Continue-shaped text: the rendered body plus the
``## Reference rules`` appendix of its ``includes_rules`` (D15, D22), resolved
through a rule registry filtered by each rule's ``applies_if``. A Claude Code
command would point at skills instead, but the eval scratch repo has no synced
skills a pointer could name.

The facts come from running the detector over the task's ``setup/`` tree (the
same bytes the runner materializes into the scratch repo), overlaid with the
task's authored mock facts (``[setup] project_kind`` + extra keys).

Mirrors the prompt half of ``commands/_sync_render.py::render_artifacts``
without touching it; the two should converge on one shared helper.

Usage::

    prompt = render_prompt(task, strict=runner.requires_resolved_prompt)
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any, cast

import yaml
from jinja2 import TemplateError

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.detector import detect, evaluate_predicate
from coding_agent_playbook.orchestrator import OverlayResolver
from coding_agent_playbook.prompt_rule_delivery import includes_rules_appendix
from coding_agent_playbook.renderer import (
    TemplateSecurityError,
    build_environment,
    render_string,
)
from coding_agent_playbook.rule_registry import RuleRegistryImpl
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource
from coding_agent_playbook.types import Prompt

if TYPE_CHECKING:
    from pathlib import Path

    from jinja2 import Environment

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Rule

#: The engine package: its rules are always in scope, like for a consumer.
_ENGINE_PACKAGE = "coding_agent_playbook"

#: ``source_package`` of a task authored under a consumer's ``playbook/``.
_REPO_LOCAL = "<repo-local>"

#: ``TaskSetup.project_kind``'s default when unauthored — the detected kind wins.
_UNSET_PROJECT_KIND = "python-unknown"

#: Detector facts shaped ``{name: version}``. Task TOML mocks them as a list of
#: names (``ml_stack = ["torch"]``); predicates read ``.keys()``, so normalize.
_NAME_MAP_FACTS = ("dependencies", "dev_dependencies", "frameworks", "ml_stack")


#: What rendering a prompt can raise on bad *inputs* rather than engine bugs: a
#: Jinja error (typo'd variable), a mis-shaped mock fact reaching a predicate
#: (``ml_stack = "torch"``, ``python_version = 3.12``), an unreadable or
#: malformed rule file (bad YAML frontmatter, a directory named ``*.md``), or an
#: included rule that the Jinja sandbox rejects. That last one is
#: ``RuleRegistryImpl``'s :class:`TemplateSecurityError`, a plain ``Exception``
#: (not a jinja ``TemplateError``), so it must be listed or ``playbook eval
#: --run`` crashes with exit 1, the "task failed" code, instead of exit 2.
_RENDER_ERRORS = (
    TemplateError,
    TemplateSecurityError,
    ValueError,
    TypeError,
    AttributeError,
    yaml.YAMLError,
    OSError,
)


class PromptResolutionError(RuntimeError):
    """An eval task's prompt could not be resolved or rendered.

    Raised by :func:`render_prompt` when ``strict=True`` and the task's
    ``prompt_id`` resolves to no shipped :class:`Prompt` (a real agent must never
    be driven with the placeholder the hermetic ``FakeRunner`` tolerates), and —
    regardless of ``strict`` — when a resolved prompt fails to render (a typo'd
    variable is an authoring bug, not something to paper over).
    """


def render_prompt(task: EvalTask, *, strict: bool = False) -> str:
    """Resolve ``task.prompt_id`` to its :class:`Prompt` and render it like sync.

    The rendered body and its ``## Reference rules`` appendix are followed by
    ``task.invocation.prompt_args``. When the prompt cannot be resolved at all
    (e.g. an out-of-tree test task) ``strict`` decides: ``False`` (the
    ``FakeRunner``, which never reads the text) returns a stable
    ``[prompt:<id>] <args>`` placeholder, ``True`` (a real runner) raises
    :class:`PromptResolutionError`. A resolved prompt that fails to render always
    raises :class:`PromptResolutionError`, naming the task and prompt.

    Example::

        render_prompt(task, strict=True)  # "You are reviewing…\\n\\nreview src/x.py"
    """
    prompt = _resolve_prompt(task)
    if prompt is None:
        return _placeholder(task, strict=strict)
    body = _render_with_references(task, prompt)
    args = task.invocation.prompt_args
    return f"{body}\n\n{args}".rstrip() if args else body


def _placeholder(task: EvalTask, *, strict: bool) -> str:
    """The unresolvable-prompt fallback: a placeholder, or a strict-mode error."""
    if strict:
        raise PromptResolutionError(
            f"prompt_id {task.prompt_id!r} for task {task.id!r} resolved to no "
            "shipped prompt; a real runner cannot be driven with a placeholder. "
            "Check the task's prompt_id and that the prompts/ directory next to the "
            "task's eval_tasks/ holds that prompt."
        )
    return f"[prompt:{task.prompt_id}] {task.invocation.prompt_args}".strip()


def _render_with_references(task: EvalTask, prompt: Prompt) -> str:
    """The rendered body plus the ``## Reference rules`` appendix Continue also gets (D15).

    Facts are computed only when the prompt is templated or lists
    ``includes_rules``, so a plain prompt without rules never runs the detector.
    Any render error, including a sandbox violation in an included rule or a
    leftover ``{{ rule() }}`` call, raises :class:`PromptResolutionError` naming
    the task and the prompt.

    Example::

        _render_with_references(task, prompt)  # "You are reviewing…\\n## Reference rules…"
    """
    includes_rules = prompt.frontmatter.includes_rules
    if not (prompt.is_templated or includes_rules):
        return prompt.template_body
    try:
        facts = _task_facts(task)
        # The body first, so an error in the prompt's own template is the one
        # reported even when an included rule file is broken too.
        body = _render_body(task, prompt, facts)
        return body + includes_rules_appendix(includes_rules, _LazyRuleRegistry(task, facts))
    except _RENDER_ERRORS as exc:
        raise PromptResolutionError(
            f"prompt {task.prompt_id!r} for task {task.id!r} failed to render: {exc}"
        ) from exc


def _render_body(task: EvalTask, prompt: Prompt, facts: Facts) -> str:
    """Render a templated prompt body with ``facts``; a plain ``.md`` prompt passes through."""
    if not prompt.is_templated:
        return prompt.template_body
    env = _prompt_environment(facts)
    return render_string(prompt.template_body, _render_context(task, facts), env=env)


# --------------------------------------------------------------------------- #
# Facts + context
# --------------------------------------------------------------------------- #


def _setup_dir(task: EvalTask) -> Path:
    return task.source_path.parent / "setup"


def _task_facts(task: EvalTask) -> Facts:
    """Detector facts over ``setup/``, overlaid with the task's mock facts.

    An authored ``[setup] project_kind`` wins over the detected kind; the
    unauthored default does not. Extra mock keys win over detected ones.
    """
    setup_dir = _setup_dir(task)
    facts: dict[str, Any] = dict(detect(setup_dir)) if setup_dir.is_dir() else {}
    if task.setup.project_kind != _UNSET_PROJECT_KIND or "project_kind" not in facts:
        facts["project_kind"] = task.setup.project_kind
    facts.update(task.setup.extra_facts)
    for key in _NAME_MAP_FACTS:
        if isinstance(facts.get(key), list):
            facts[key] = {str(name): "" for name in facts[key]}
    # Mock facts may carry keys beyond the ``Facts`` TypedDict; templates read them.
    return cast("Facts", facts)


def _render_context(task: EvalTask, facts: Facts) -> dict[str, Any]:
    """Facts + project metadata + ``input_variables`` (the invocation wins).

    Mirrors ``commands/_sync_render.py::build_jinja_context``. The project name and
    description come from ``setup/pyproject.toml`` — which the agent can read in
    its working tree anyway — never from the task ``description``, which
    narrates the scenario and would leak it into the prompt.
    """
    project = _setup_project_table(task)
    context: dict[str, Any] = dict(facts)
    context["project_name"] = str(project.get("name") or task.id)
    context["project_description"] = str(project.get("description") or "")
    context["engine_version"] = _engine_version
    context.update(task.invocation.input_variables)
    return context


def _setup_project_table(task: EvalTask) -> dict[str, Any]:
    """``[project]`` of ``setup/pyproject.toml``, or ``{}`` when absent/invalid."""
    pyproject = _setup_dir(task) / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    project = data.get("project")
    return project if isinstance(project, dict) else {}


# --------------------------------------------------------------------------- #
# Environment (rule registry)
# --------------------------------------------------------------------------- #


def _prompt_environment(facts: Facts) -> Environment:
    """The base Jinja env with ``facts`` for ``has_framework``/``has_ml_dep``; no registry."""
    env = build_environment([])
    env.globals["_facts"] = dict(facts)
    return env


class _LazyRuleRegistry:
    """A ``RuleRegistry`` that loads the rules on the first included rule it renders.

    The ``## Reference rules`` appendix is its only consumer, so a prompt
    without ``includes_rules`` never parses a rule file, and a broken rule
    under ``setup/playbook/rules/`` cannot fail it.
    """

    def __init__(self, task: EvalTask, facts: Facts) -> None:
        self._task = task
        self._facts = facts
        self._registry: RuleRegistryImpl | None = None

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        if self._registry is None:
            base_env = build_environment([])
            base_env.globals["_facts"] = dict(self._facts)
            rules = _applicable_rules(self._task, self._facts)
            self._registry = RuleRegistryImpl(rules, self._facts, base_env)
        return self._registry.render_for_inclusion(rule_id, context)


def _applicable_rules(task: EvalTask, facts: Facts) -> list[Rule]:
    """Engine rules (+ the task's overlay package's) whose ``applies_if`` holds.

    Ids are resolved *before* filtering, as sync does: an overlay rule replaces
    the engine rule of the same id even when its own ``applies_if`` is false —
    the rule is then dropped, never silently replaced by the engine body.
    """
    overlays = (
        [] if task.source_package in (_ENGINE_PACKAGE, _REPO_LOCAL) else [task.source_package]
    )
    source = FileSystemArtifactSource(repo_root=_setup_dir(task), overlay_packages=overlays)
    kept: list[Rule] = []
    for rule in OverlayResolver().resolve_rules(source.list_rules(), [], []):
        predicate = rule.frontmatter.applies_if or {}
        if not predicate or evaluate_predicate(predicate, facts, repo_root=_setup_dir(task)):
            kept.append(rule)
    return kept


# --------------------------------------------------------------------------- #
# Prompt lookup
# --------------------------------------------------------------------------- #


def _resolve_prompt(task: EvalTask) -> Prompt | None:
    """Best-effort lookup of the :class:`Prompt` for ``task.prompt_id``.

    Scans the ``prompts/`` directory of the layer the task belongs to (engine,
    bundled plugin, overlay or repo-local; see :func:`_infer_prompts_dir`). This
    deliberately reads the prompt markdown directly rather than through
    ``SyncContext``: resolution must work for the engine's own content, which
    carries no ``.coding-agent-playbook.toml``. Returns ``None`` when the
    prompts directory cannot be located or no prompt matches.
    """
    prompts_dir = _infer_prompts_dir(task.source_path)
    if prompts_dir is None or not prompts_dir.is_dir():
        return None
    for entry in sorted(prompts_dir.iterdir()):
        name = entry.name
        if not entry.is_file() or not (name.endswith(".md") or name.endswith(".md.j2")):
            continue
        try:
            prompt = Prompt.from_markdown(entry, source_package=task.source_package)
        except (OSError, ValueError, KeyError):
            continue
        if prompt.frontmatter.id == task.prompt_id:
            return prompt
    return None


def _infer_prompts_dir(task_toml: Path) -> Path | None:
    """Locate the ``prompts/`` dir of the layer holding the task's ``eval_tasks/``.

    Every layer keeps its kind directories side by side, so a task at
    ``<layer>/eval_tasks/<dir>/task.toml`` has its prompts at
    ``<layer>/prompts``, whatever ``<layer>`` is (``catalog/core``,
    ``<pkg>/resources``, ``playbook``). Returns ``None`` when the task dir's
    parent is not ``eval_tasks`` (e.g. a synthetic test task). The path is not
    resolved, so a symlinked task dir maps to the layer it is reached through.

    Example::

        >>> _infer_prompts_dir(Path("catalog/core/eval_tasks/t/task.toml"))
        PosixPath('catalog/core/prompts')
    """
    if task_toml.parent.parent.name != "eval_tasks":
        return None
    return task_toml.parents[2] / "prompts"


__all__ = ["PromptResolutionError", "render_prompt"]
