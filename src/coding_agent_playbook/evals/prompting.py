"""Render an eval sample's prompt the way ``playbook sync`` renders it.

The runner drives an agent with the sample's prompt, so that prompt must be the
one a consumer actually gets: the Jinja context carries the detector facts plus
project metadata. Rendering with a bare environment instead crashed 7 of the 20
shipped samples with ``UndefinedError`` (``rule`` for the review prompts, before
D15 removed that helper, and ``project_name`` for generate-tests) before any
agent ran.

The runner hands the agent the Continue-shaped text: the rendered body plus the
``## Reference rules`` appendix of its ``includes_rules`` (D15, D22), resolved
through a rule registry that holds only the rules whose ``applies_if`` passed.
A Claude Code command would point at skills instead, but the eval scratch repo
has no synced skills a pointer could name.

The facts come from running the detector over the sample's ``setup/`` tree (the
same bytes the runner materializes into the scratch repo), overlaid with the
sample's authored mock facts (``[setup] project_kind`` + extra keys).

The text comes from ``RenderSession.prompt_text`` (``rendering.session``), the
render session sync and ``playbook render`` open too, so the three cannot diverge.

A pinned sample graded on its edition (``release.edition``, #281 ticket 09)
renders closed-world: the prompt and every rule come from the edition alone, so
no engine rule, overlay or ``setup/playbook/rules/`` override reaches the text.

Usage::

    prompt = render_prompt(sample, strict=runner.requires_resolved_prompt)
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any, cast

import yaml
from jinja2 import TemplateError

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.catalog.resolve import OverlayResolver
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.evals.task_registry import sample_layer_root
from coding_agent_playbook.release.edition import EditionError
from coding_agent_playbook.rendering.jinja import TemplateSecurityError
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.release.edition import Edition

#: The engine package: its rules are always in scope, like for a consumer.
_ENGINE_PACKAGE = "coding_agent_playbook"

#: ``source_package`` of a sample authored under a consumer's ``playbook/``.
_REPO_LOCAL = "<repo-local>"

#: ``SampleSetup.project_kind``'s default when unauthored — the detected kind wins.
_UNSET_PROJECT_KIND = "python-unknown"

#: Detector facts shaped ``{name: version}``. Sample TOML mocks them as a list of
#: names (``ml_stack = ["torch"]``); predicates read ``.keys()``, so normalize.
_NAME_MAP_FACTS = ("dependencies", "dev_dependencies", "frameworks", "ml_stack")


#: What rendering a prompt can raise on bad *inputs* rather than engine bugs: a
#: Jinja error (typo'd variable), a mis-shaped mock fact reaching a predicate
#: (``ml_stack = "torch"``, ``python_version = 3.12``), an unreadable or
#: malformed rule file (bad YAML frontmatter, a directory named ``*.md``), or a
#: prompt or included rule that the Jinja sandbox rejects. That last one is the
#: session's :class:`TemplateSecurityError`, a plain ``Exception`` (not a jinja
#: ``TemplateError``), so it must be listed or ``playbook eval --run`` crashes
#: with exit 1, the "sample failed" code, instead of exit 2.
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
    """An eval sample's prompt could not be resolved or rendered.

    Raised by :func:`render_prompt` when ``strict=True`` and the sample's
    ``prompt_id`` resolves to no shipped :class:`Prompt` (a real agent must never
    be driven with the placeholder the hermetic ``FakeRunner`` tolerates), and —
    regardless of ``strict`` — when a resolved prompt fails to render (a typo'd
    variable is an authoring bug, not something to paper over).
    """


def render_prompt(
    sample: EvalSample,
    *,
    strict: bool = False,
    edition: Edition | None = None,
) -> str:
    """Resolve ``sample.prompt_id`` to its :class:`Prompt` and render it like sync.

    Without ``edition`` the sample grades the current text of its layer's prompt
    (ADR 0012). The rendered body and its ``## Reference rules`` appendix are followed by
    ``sample.invocation.prompt_args``. When the prompt cannot be resolved at all
    (e.g. an out-of-tree test sample) ``strict`` decides: ``False`` (the
    ``FakeRunner``, which never reads the text) returns a stable
    ``[prompt:<id>] <args>`` placeholder, ``True`` (a real runner) raises
    :class:`PromptResolutionError`. A resolved prompt that fails to render always
    raises :class:`PromptResolutionError`, naming the sample and prompt.

    ``edition`` renders the edition's frozen prompt and rules instead, closed-world;
    an id the edition lacks always raises :class:`PromptResolutionError`, whatever
    ``strict`` says.

    Example::

        render_prompt(sample, strict=True)  # "You are reviewing…\\n\\nreview src/x.py"
    """
    if edition is not None:
        prompt: Prompt | None = _edition_prompt(sample, edition)
    else:
        prompt = _resolve_prompt(sample)
    if prompt is None:
        return _placeholder(sample, strict=strict)
    rules = list(edition.rules) if edition is not None else None
    body = _render_with_references(sample, prompt, rules)
    args = sample.invocation.prompt_args
    return f"{body}\n\n{args}".rstrip() if args else body


def resolve_sample_prompt(sample: EvalSample, edition: Edition | None = None) -> Prompt | None:
    """The :class:`Prompt` ``sample`` grades (as :func:`render_prompt` finds it).

    ``None`` when the sample's layer has no prompt with its ``prompt_id``. With
    ``edition``, the edition's frozen prompt (:class:`PromptResolutionError` when
    it has none).

    Example::

        resolve_sample_prompt(sample).frontmatter.id  # "review"
    """
    if edition is not None:
        return _edition_prompt(sample, edition)
    return _resolve_prompt(sample)


def _edition_prompt(sample: EvalSample, edition: Edition) -> Prompt:
    """``edition``'s prompt for ``sample``; an id it lacks is a :class:`PromptResolutionError`."""
    try:
        return edition.prompt(sample.prompt_id)
    except EditionError as exc:
        raise PromptResolutionError(
            f"sample {sample.id!r} cannot grade its edition: {exc}"
        ) from exc


def _placeholder(sample: EvalSample, *, strict: bool) -> str:
    """The unresolvable-prompt fallback: a placeholder, or a strict-mode error."""
    if strict:
        raise PromptResolutionError(
            f"prompt {sample.prompt_id!r} for sample {sample.id!r} resolved to no "
            "shipped prompt; a real runner cannot be driven with a placeholder. "
            "Check that the prompts/ directory next to the sample's eval_samples/ "
            "holds the prompt its task directory names."
        )
    return f"[prompt:{sample.prompt_id}] {sample.invocation.prompt_args}".strip()


def _render_with_references(
    sample: EvalSample, prompt: Prompt, rules: list[Rule] | None = None
) -> str:
    """The rendered body plus the ``## Reference rules`` appendix Continue also gets (D15).

    Facts are computed only when the prompt is templated or lists
    ``includes_rules``, so a plain prompt without rules never runs the detector.
    ``rules`` is the closed rule set of an edition; ``None`` resolves the sample's
    layers (:func:`_resolved_rules`).
    Any render error, including a sandbox violation in an included rule or a
    leftover ``{{ rule() }}`` call, raises :class:`PromptResolutionError` naming
    the sample and the prompt.

    Example::

        _render_with_references(sample, prompt)  # "You are reviewing…\\n## Reference rules…"
    """
    if not (prompt.is_templated or prompt.frontmatter.includes_rules):
        return prompt.template_body
    try:
        return _sample_session(sample, prompt, rules).prompt_text(prompt)
    except _RENDER_ERRORS as exc:
        raise PromptResolutionError(
            f"prompt {sample.prompt_id!r} for sample {sample.id!r} failed to render: {exc}"
        ) from exc


def _sample_session(
    sample: EvalSample, prompt: Prompt, rules: list[Rule] | None = None
) -> RenderSession:
    """The sample's render session; it loads the rules only for a prompt that includes some.

    A prompt without ``includes_rules`` gets ``rules=()``, so it never parses a
    rule file and a broken rule under ``setup/playbook/rules/`` cannot fail it
    (RS-D7). ``has_file`` paths resolve inside ``setup/``, the agent's project.
    No skills and no framework are passed (a sample is not a synced repo), so
    ``framework_skill(role)`` renders ``""`` and ``skill_active(name)`` ``False``
    here, unlike in sync; ``tests/evals/test_prompting.py`` pins that.

    Example: ``_sample_session(sample, prompt).prompt_text(prompt)``.
    """
    facts = _sample_facts(sample)
    if not prompt.frontmatter.includes_rules:
        rules = []
    elif rules is None:
        rules = _resolved_rules(sample)
    context = _sample_template_context(sample, facts)
    return RenderSession.open(rules, context, repo_root=sample.setup_dir)


# --------------------------------------------------------------------------- #
# Facts + context
# --------------------------------------------------------------------------- #


def _sample_facts(sample: EvalSample) -> Facts:
    """Detector facts over ``setup/``, overlaid with the sample's mock facts.

    An authored ``[setup] project_kind`` wins over the detected kind; the
    unauthored default does not. Extra mock keys win over detected ones.
    """
    setup_dir = sample.setup_dir
    facts: dict[str, Any] = dict(detect(setup_dir)) if setup_dir.is_dir() else {}
    if sample.setup.project_kind != _UNSET_PROJECT_KIND or "project_kind" not in facts:
        facts["project_kind"] = sample.setup.project_kind
    facts.update(sample.setup.extra_facts)
    for key in _NAME_MAP_FACTS:
        if isinstance(facts.get(key), list):
            facts[key] = {str(name): "" for name in facts[key]}
    # Mock facts may carry keys beyond the ``Facts`` TypedDict; templates read them.
    return cast("Facts", facts)


def _sample_template_context(sample: EvalSample, facts: Facts) -> TemplateContext:
    """``facts``, the setup project, the installed version and the invocation's variables.

    The project name and description come from ``setup/pyproject.toml`` — which
    the agent can read in its working tree anyway — never from the sample
    ``description``, which narrates the scenario and would leak it into the
    prompt. The invocation's ``input_variables`` win over everything (RS-D6).
    """
    project = _setup_project_table(sample)
    return TemplateContext(
        facts=facts,
        project_name=str(project.get("name") or sample.id),
        project_description=str(project.get("description") or ""),
        engine_version=_engine_version,
        overrides=sample.invocation.input_variables,
    )


def _setup_project_table(sample: EvalSample) -> dict[str, Any]:
    """``[project]`` of ``setup/pyproject.toml``, or ``{}`` when absent/invalid."""
    pyproject = sample.setup_dir / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    project = data.get("project")
    return project if isinstance(project, dict) else {}


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


def _resolved_rules(sample: EvalSample) -> list[Rule]:
    """Engine rules, the sample's overlay package's and ``setup/playbook/rules/``, ids resolved.

    Ids are resolved *before* the session filters by ``applies_if``, as sync
    does: an overlay rule replaces the engine rule of the same id even when its
    own ``applies_if`` is false — the rule is then dropped, never silently
    replaced by the engine body.
    """
    overlays = (
        [] if sample.source_package in (_ENGINE_PACKAGE, _REPO_LOCAL) else [sample.source_package]
    )
    source = FileSystemArtifactSource(repo_root=sample.setup_dir, overlay_packages=overlays)
    return OverlayResolver().resolve_rules(source.list_rules(), [], [])


# --------------------------------------------------------------------------- #
# Prompt lookup
# --------------------------------------------------------------------------- #


def _resolve_prompt(sample: EvalSample) -> Prompt | None:
    """Best-effort lookup of the :class:`Prompt` for ``sample.prompt_id``.

    Scans the ``prompts/`` directory of the layer the sample belongs to (engine,
    bundled plugin, overlay or repo-local; see :func:`_infer_prompts_dir`). This
    deliberately reads the prompt markdown directly rather than through
    ``SyncContext``: resolution must work for the engine's own content, which
    carries no ``.coding-agent-playbook.toml``. Returns ``None`` when the
    prompts directory cannot be located or no prompt matches.
    """
    prompts_dir = _infer_prompts_dir(sample.source_path)
    if prompts_dir is None:
        return None
    return _prompt_in_dir(prompts_dir, sample)


def _prompt_in_dir(prompts_dir: Path, sample: EvalSample) -> Prompt | None:
    """The prompt file directly in ``prompts_dir`` whose id is ``sample.prompt_id``, if any."""
    if not prompts_dir.is_dir():
        return None
    for entry in sorted(prompts_dir.iterdir()):
        name = entry.name
        if not entry.is_file() or not (name.endswith(".md") or name.endswith(".md.j2")):
            continue
        try:
            prompt = Prompt.from_markdown(entry, source_package=sample.source_package)
        except (OSError, ValueError, KeyError):
            continue
        if prompt.frontmatter.id == sample.prompt_id:
            return prompt
    return None


def _infer_prompts_dir(sample_toml: Path) -> Path | None:
    """Locate the ``prompts/`` dir of the layer holding the sample's ``eval_samples/``.

    Every layer keeps its kind directories side by side, so a sample at
    ``<layer>/eval_samples/<prompt>/<name>/sample.toml`` has its prompts at
    ``<layer>/prompts``, whatever ``<layer>`` is (``catalog/core``,
    ``<pkg>/resources``, ``playbook``). Returns ``None`` when the sample is not
    in a task directory of an ``eval_samples/`` (e.g. a synthetic test sample);
    the task registry's :func:`sample_layer_root` knows the layout.

    Example::

        >>> _infer_prompts_dir(Path("catalog/core/eval_samples/review/t/sample.toml"))
        PosixPath('catalog/core/prompts')
    """
    layer = sample_layer_root(sample_toml)
    return None if layer is None else layer / "prompts"


__all__ = ["PromptResolutionError", "render_prompt", "resolve_sample_prompt"]
