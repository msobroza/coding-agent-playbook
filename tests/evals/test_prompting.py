"""Tests for eval prompt rendering (``evals/prompting.py``).

An eval sample's prompt must render as ``playbook sync`` renders it for a
consumer: the Jinja context carries the detector facts + project metadata, and
the prompt's ``includes_rules`` arrive as the ``## Reference rules`` appendix
Continue also gets (D15, D22), resolved through a rule registry. Before this
module the runner rendered with a bare environment, so 7 of the 20 shipped
samples crashed with ``UndefinedError`` (``rule`` for review/security-review,
``project_name`` for generate-tests) — even under the hermetic ``FakeRunner``.
"""

from __future__ import annotations

import sys
import textwrap
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.impact import Impact
from coding_agent_playbook.evals.loader import load_eval_sample_from_dir
from coding_agent_playbook.evals.prompting import (
    PromptResolutionError,
    _infer_prompts_dir,
    render_prompt,
)
from coding_agent_playbook.evals.sample import EvalSample, SampleInvocation, SampleSetup
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.catalog

_ENGINE = "coding_agent_playbook"
_SHIPPED_SAMPLES = CORE_ROOT / "eval_samples"
#: A shipped sample of the plain-`.md` `refactor` prompt (no Jinja, four included rules).
_REFACTOR_SAMPLE = "refactor-extract-helper"


def _shipped_sample_dirs() -> list[Path]:
    return sorted(p for p in _SHIPPED_SAMPLES.iterdir() if (p / "sample.toml").is_file())


def _shipped(sample_id: str) -> EvalSample:
    return load_eval_sample_from_dir(_SHIPPED_SAMPLES / sample_id, source_package=_ENGINE)


# --------------------------------------------------------------------------- #
# Every shipped sample renders strictly (regression: 7/20 crashed)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("sample_dir", _shipped_sample_dirs(), ids=lambda p: p.name)
def test_every_shipped_sample_prompt_renders_strictly(sample_dir: Path) -> None:
    """A real runner renders with ``strict=True``; no shipped sample may crash."""
    sample = load_eval_sample_from_dir(sample_dir, source_package=_ENGINE)
    prompt = render_prompt(sample, strict=True)
    assert prompt.strip()
    assert not prompt.startswith(f"[prompt:{sample.prompt_id}]")  # not the placeholder
    if sample.invocation.prompt_args:
        assert prompt.rstrip().endswith(sample.invocation.prompt_args)


@pytest.mark.parametrize("sample_dir", _shipped_sample_dirs(), ids=lambda p: p.name)
def test_shipped_sample_appendices_carry_no_impact_tag(sample_dir: Path) -> None:
    """D46(8): a member rule's ``[IMPACT]`` title tag never reaches an eval appendix."""
    sample = load_eval_sample_from_dir(sample_dir, source_package=_ENGINE)
    prompt = render_prompt(sample, strict=True)
    assert not any(f" [{impact.value}]" in prompt for impact in Impact)


def test_reference_appendix_inlines_the_included_rule() -> None:
    """``includes_rules: [.., python-error-handling]`` appends that rule's header + body once."""
    prompt = render_prompt(_shipped("review-spot-the-bug"), strict=True)
    assert prompt.count("### Error handling") == 1
    assert prompt.index("## Output format") < prompt.index("## Reference rules")


def test_plain_md_prompt_gets_the_reference_appendix() -> None:
    """The shipped ``refactor`` prompt is plain ``.md``: no Jinja, but its rules still arrive."""
    prompt = render_prompt(_shipped(_REFACTOR_SAMPLE), strict=True)
    assert prompt.count("## Reference rules") == 1
    assert "### Typing" in prompt


def test_mocked_ml_stack_list_satisfies_any_ml_stack() -> None:
    """``[setup] ml_stack = ["torch", …]`` gates the ML rule in.

    Sample TOML authors mock facts as a *list* of names while the detector emits a
    ``{name: version}`` dict; ``any_ml_stack`` reads ``.keys()``, so the list must
    be normalized or the predicate crashes.
    """
    prompt = render_prompt(_shipped("security-review-pickle-load"), strict=True)
    assert "### ML serialization & deserialization security" in prompt


def test_project_name_comes_from_the_setup_pyproject() -> None:
    """``{{ project_name }}`` resolves to the fixture's ``[project].name``."""
    prompt = render_prompt(_shipped("generate-tests-happy-path"), strict=True)
    assert "generate-tests-happy-path-fixture" in prompt


def test_authored_project_kind_is_the_mock_detector_fact() -> None:
    """``[setup].project_kind`` overrides what the detector infers from setup/."""
    prompt = render_prompt(_shipped("generate-tests-happy-path"), strict=True)
    assert "`python-application` project" in prompt


# --------------------------------------------------------------------------- #
# Prompt directory — found by layer, not by a ``resources`` path segment
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "layer_parts",
    [("catalog", "core"), ("pkg", "resources"), ("playbook",)],
    ids=["catalog", "overlay-resources", "repo-local"],
)
def test_infer_prompts_dir_layers(tmp_path: Path, layer_parts: tuple[str, ...]) -> None:
    """``<layer>/eval_samples/<dir>/sample.toml`` finds ``<layer>/prompts`` in every layer.

    The bundled layer (``catalog/core``) has no ``resources`` segment, and a
    repo-local sample never found its prompts before.
    """
    layer = tmp_path.joinpath(*layer_parts)
    sample_toml = layer / "eval_samples" / "t" / "sample.toml"
    assert _infer_prompts_dir(sample_toml) == layer / "prompts"


def test_infer_prompts_dir_non_sample_path(tmp_path: Path) -> None:
    """A sample dir whose parent is not ``eval_samples`` has no prompts layer."""
    assert _infer_prompts_dir(tmp_path / "t" / "sample.toml") is None


def test_infer_prompts_dir_does_not_resolve_symlinks(tmp_path: Path) -> None:
    """A symlinked sample dir maps to the layer it is reached through, not its target's."""
    target = tmp_path / "target_layer" / "eval_samples" / "t"
    target.mkdir(parents=True)
    (target / "sample.toml").write_text("", encoding="utf-8")
    link_layer = tmp_path / "link_layer"
    (link_layer / "eval_samples").mkdir(parents=True)
    (link_layer / "eval_samples" / "t").symlink_to(target, target_is_directory=True)

    sample_toml = link_layer / "eval_samples" / "t" / "sample.toml"
    assert _infer_prompts_dir(sample_toml) == link_layer / "prompts"


def test_strict_unresolved_prompt_hint_points_at_the_layers_prompts_dir(tmp_path: Path) -> None:
    """The strict-mode hint names where the lookup really happens.

    Regression: it said to check "that resources/prompts/ is reachable", but the
    engine's own content has no ``resources/`` since v0.19, and every layer's
    prompts are found next to its ``eval_samples/`` (:func:`_infer_prompts_dir`).
    """
    sample_dir = tmp_path / "catalog" / "core" / "eval_samples" / "orphan-sample"
    (sample_dir / "setup").mkdir(parents=True)
    sample = EvalSample(
        id="orphan-sample",
        prompt_id="no-such-prompt",
        description="A sample whose prompt is not shipped.",
        source_path=sample_dir / "sample.toml",
        source_package=_ENGINE,
        setup=SampleSetup(),
        invocation=SampleInvocation(prompt_args="go"),
    )

    with pytest.raises(PromptResolutionError) as raised:
        render_prompt(sample, strict=True)

    message = str(raised.value)
    assert "resources/prompts" not in message
    assert "the prompts/ directory next to the sample's eval_samples/" in message


# --------------------------------------------------------------------------- #
# Synthetic resources tree — failure modes
# --------------------------------------------------------------------------- #


def _synthetic_sample(
    tmp_path: Path,
    prompt_body: str,
    *,
    templated: bool = True,
    pyproject: str | None = None,
    setup: SampleSetup | None = None,
    includes_rules: tuple[str, ...] = (),
) -> EvalSample:
    """Lay down ``<tmp>/pkg/resources/{prompts,eval_samples}`` with one prompt + sample.

    ``includes_rules`` lands in the prompt's frontmatter.
    """
    resources = tmp_path / "pkg" / "resources"
    prompts = resources / "prompts"
    prompts.mkdir(parents=True)
    suffix = ".md.j2" if templated else ".md"
    (prompts / f"synthetic{suffix}").write_text(
        textwrap.dedent(
            """\
            ---
            id: synthetic
            name: Synthetic
            description: A synthetic prompt for tests.
            slash: synthetic
            """
        )
        + _includes_rules_yaml(includes_rules)
        + "---\n"
        + prompt_body,
        encoding="utf-8",
    )
    sample_dir = resources / "eval_samples" / "synthetic-sample"
    (sample_dir / "setup").mkdir(parents=True)
    if pyproject is not None:
        (sample_dir / "setup" / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return EvalSample(
        id="synthetic-sample",
        prompt_id="synthetic",
        description="DO-NOT-LEAK sample description",
        source_path=sample_dir / "sample.toml",
        source_package=_ENGINE,
        setup=setup or SampleSetup(),
        invocation=SampleInvocation(prompt_args="go"),
    )


def _includes_rules_yaml(rule_ids: tuple[str, ...]) -> str:
    """The ``includes_rules:`` frontmatter lines for ``rule_ids`` (``""`` for none)."""
    if not rule_ids:
        return ""
    return "includes_rules:\n" + "".join(f"  - {rule_id}\n" for rule_id in rule_ids)


def test_sample_prompts_see_no_framework_and_no_active_skill(tmp_path: Path) -> None:
    """Eval sessions open without skills or a framework (D74 helpers; L0-19 review).

    A sample's prompt renders against its ``setup/`` tree, not a synced repo, so
    ``framework_skill(role)`` is ``""`` and ``skill_active(name)`` is ``False``.
    """
    sample = _synthetic_sample(
        tmp_path, "[{{ framework_skill('clarify') }}]|{{ skill_active('brainstorming') }}\n"
    )
    assert "[]|False" in render_prompt(sample, strict=True)


def test_render_error_raises_prompt_resolution_error_even_when_not_strict(
    tmp_path: Path,
) -> None:
    """A resolvable prompt that fails to render is an authoring bug, not a placeholder.

    ``strict`` only governs the *unresolvable*-prompt fallback; a typo'd variable
    in a prompt that does resolve must fail loudly for every runner, and must name
    the sample and prompt rather than surfacing a bare Jinja ``UndefinedError``.
    """
    sample = _synthetic_sample(tmp_path, "Hello {{ no_such_variable }}\n")
    with pytest.raises(PromptResolutionError, match=r"synthetic-sample.*no_such_variable"):
        render_prompt(sample, strict=False)


def test_non_templated_prompt_is_passed_through_verbatim(tmp_path: Path) -> None:
    """A plain ``.md`` prompt is not run through Jinja (mirrors ``playbook sync``)."""
    sample = _synthetic_sample(tmp_path, "Literal {{ braces }} stay as written.\n", templated=False)
    assert "Literal {{ braces }} stay as written." in render_prompt(sample, strict=True)


def test_input_variables_and_facts_reach_the_template(tmp_path: Path) -> None:
    """``input_variables`` + mock facts + project metadata are all in the context."""
    sample = _synthetic_sample(
        tmp_path,
        "{{ project_name }}|{{ project_kind }}|{{ target }}|{{ has_ml_dep('torch') }}\n",
        pyproject='[project]\nname = "demo-fixture"\nversion = "9.9.9"\n',
        setup=SampleSetup(project_kind="ml-research", extra_facts={"ml_stack": ["torch"]}),
    )
    sample.invocation.input_variables["target"] = "src/x.py::f"
    assert "demo-fixture|ml-research|src/x.py::f|True" in render_prompt(sample, strict=True)


@pytest.mark.parametrize(
    ("ml_stack", "inlined"),
    [(["torch"], True), (None, False)],
    ids=["ml-project", "non-ml-project"],
)
def test_reference_appendix_honours_the_rule_applies_if(
    tmp_path: Path, ml_stack: list[str] | None, inlined: bool
) -> None:
    """The appendix carries a gated rule only when its ``applies_if`` holds.

    A filtered-out rule renders as ``""`` — the silent-omission contract of
    SPEC §6.2.5, identical to ``playbook sync``.
    """
    extra = {"ml_stack": ml_stack} if ml_stack is not None else {}
    sample = _synthetic_sample(
        tmp_path,
        "Review.\n",
        setup=SampleSetup(extra_facts=extra),
        includes_rules=("ml-serialization-security",),
    )
    prompt = render_prompt(sample, strict=True)
    assert ("### ML serialization & deserialization security" in prompt) is inlined


def test_rule_call_in_a_prompt_raises_prompt_resolution_error(tmp_path: Path) -> None:
    """Regression (D15): the removed ``rule()`` helper is an authoring error (exit 2)."""
    sample = _synthetic_sample(tmp_path, 'Review.\n{{ rule("python-error-handling") }}\n')
    with pytest.raises(PromptResolutionError, match=r"synthetic-sample.*'rule' is undefined"):
        render_prompt(sample, strict=False)


def test_project_name_falls_back_to_the_sample_id_without_a_pyproject(tmp_path: Path) -> None:
    """No ``setup/pyproject.toml`` ⇒ the sample id names the project.

    Never the sample ``description``: that narrates the scenario (often the bug the
    agent is meant to find), so it must not leak into the agent's prompt.
    """
    sample = _synthetic_sample(tmp_path, "{{ project_name }}: {{ project_description }}\n")
    prompt = render_prompt(sample, strict=True)
    assert prompt.startswith("synthetic-sample: ")
    assert "DO-NOT-LEAK" not in prompt


def test_input_variables_win_over_facts_and_project_metadata(tmp_path: Path) -> None:
    """An ``input_variables`` key overrides a same-named fact or project field."""
    sample = _synthetic_sample(
        tmp_path,
        "{{ project_name }}|{{ project_kind }}\n",
        pyproject='[project]\nname = "from-pyproject"\nversion = "9.9.9"\n',
        setup=SampleSetup(project_kind="ml-research"),
    )
    sample.invocation.input_variables.update(project_name="from-invocation", project_kind="cli")
    assert "from-invocation|cli" in render_prompt(sample, strict=True)


@pytest.mark.parametrize(
    "extra_facts",
    [{"ml_stack": "torch"}, {"python_version": 3.12}],
    ids=["ml_stack-as-string", "python_version-as-float"],
)
def test_mis_shaped_mock_facts_raise_prompt_resolution_error(
    tmp_path: Path, extra_facts: dict[str, object]
) -> None:
    """A bad mock fact reaching a rule predicate is an authoring error, not a crash.

    Predicates run when the prompt includes a rule. ``playbook eval --run`` maps
    :class:`PromptResolutionError` to exit 2; a raw ``AttributeError`` /
    ``TypeError`` would surface as a traceback and exit 1 — the code for a
    *failing* report.
    """
    sample = _synthetic_sample(
        tmp_path,
        "Review.\n",
        setup=SampleSetup(extra_facts=extra_facts),
        includes_rules=("python-error-handling",),
    )
    with pytest.raises(PromptResolutionError, match="failed to render"):
        render_prompt(sample, strict=True)


def test_async_prompt_sees_pytest_asyncio_from_main_dependencies() -> None:
    """``pytest-asyncio`` in ``[project].dependencies`` counts as available.

    The generate-tests prompt and the pytest rule used to check only
    ``dev_dependencies``, so this sample's prompt told the agent the plugin was
    missing ("stop and ask first") — working against the sample itself.
    """
    prompt = render_prompt(_shipped("generate-tests-async-code"), strict=True)
    assert "with `pytest-asyncio` available" in prompt
    assert "This project has `pytest-asyncio` installed" in prompt
    assert "does not currently depend on `pytest-asyncio`" not in prompt


# --------------------------------------------------------------------------- #
# Overlay samples — rules resolve by id before applies_if (sync parity)
# --------------------------------------------------------------------------- #

_OVERLAY = "temp_prompting_overlay"


@pytest.fixture
def overlay_package(tmp_path: Path) -> Iterator[Path]:
    """An importable overlay package at ``<tmp>/temp_prompting_overlay``."""
    package = tmp_path / _OVERLAY
    (package / "resources").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield package / "resources"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop(_OVERLAY, None)


def _overlay_rule(resources: Path, rule_id: str, *, name: str, applies_if: str = "") -> None:
    rules = resources / "rules"
    rules.mkdir(exist_ok=True)
    (rules / f"{rule_id}.md").write_text(
        f"---\nid: {rule_id}\nname: {name}\ndescription: d\nscope: always\n"
        f"{applies_if}---\nOverlay body for {rule_id}.\n",
        encoding="utf-8",
    )


def _overlay_sample(resources: Path, prompt_body: str, *, includes_rule: str) -> EvalSample:
    (resources / "prompts").mkdir()
    (resources / "prompts" / "overlay-prompt.md.j2").write_text(
        "---\nid: overlay-prompt\nname: O\ndescription: d\nslash: o\n"
        f"includes_rules:\n  - {includes_rule}\n---\n" + prompt_body,
        encoding="utf-8",
    )
    sample_dir = resources / "eval_samples" / "overlay-sample"
    (sample_dir / "setup").mkdir(parents=True)
    return EvalSample(
        id="overlay-sample",
        prompt_id="overlay-prompt",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package=_OVERLAY,
    )


def test_overlay_sample_can_include_an_overlay_only_rule(overlay_package: Path) -> None:
    _overlay_rule(overlay_package, "bank-house-rule", name="Bank house rule")
    sample = _overlay_sample(overlay_package, "Review.\n", includes_rule="bank-house-rule")
    assert "### Bank house rule" in render_prompt(sample, strict=True)


def test_overlay_override_with_false_applies_if_drops_the_rule(overlay_package: Path) -> None:
    """An overlay override that does not apply removes the rule — as in sync.

    Filtering before resolving ids used to drop the overlay copy and let the
    engine rule it replaces leak back into the prompt.
    """
    _overlay_rule(
        overlay_package,
        "python-error-handling",
        name="Overlay error handling",
        applies_if="applies_if:\n  any_ml_stack: [torch]\n",
    )
    sample = _overlay_sample(
        overlay_package, "Start.\nEnd.\n", includes_rule="python-error-handling"
    )
    prompt = render_prompt(sample, strict=True)
    assert "### Error handling" not in prompt  # the engine body did not leak back
    assert "Overlay body" not in prompt


def test_detected_project_kind_wins_over_the_unauthored_default(tmp_path: Path) -> None:
    """With no authored ``[setup] project_kind`` the detector's kind is used."""
    sample = _synthetic_sample(
        tmp_path,
        "kind={{ project_kind }}\n",
        pyproject='[project]\nname = "x"\nversion = "0.1"\ndependencies = ["fastapi"]\n',
    )
    package = sample.source_path.parent / "setup" / "src" / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    prompt = render_prompt(sample, strict=True)
    assert "kind=python-application" in prompt


def _broken_rule(sample: EvalSample, *, as_directory: bool = False) -> None:
    rules = sample.source_path.parent / "setup" / "playbook" / "rules"
    rules.mkdir(parents=True)
    if as_directory:
        (rules / "bad.md").mkdir()
        return
    (rules / "bad.md").write_text("---\nid: [unclosed\nname: x\n---\nbody\n", encoding="utf-8")


@pytest.mark.parametrize("as_directory", [False, True], ids=["bad-yaml", "directory"])
def test_a_broken_rule_file_fails_only_prompts_that_include_rules(
    tmp_path: Path, as_directory: bool
) -> None:
    """Rules load lazily, on the first rule the appendix renders.

    A prompt that includes no rule must not be broken by an unrelated bad file;
    one that does gets a :class:`PromptResolutionError` (exit 2), never a raw
    ``yaml`` / ``OSError`` traceback (exit 1, a "failing report").
    """
    plain = _synthetic_sample(tmp_path / "plain", "No rules here, {{ project_name }}.\n")
    _broken_rule(plain, as_directory=as_directory)
    assert "No rules here" in render_prompt(plain, strict=True)

    inlining = _synthetic_sample(
        tmp_path / "inlining", "Review.\n", includes_rules=("python-error-handling",)
    )
    _broken_rule(inlining, as_directory=as_directory)
    with pytest.raises(PromptResolutionError, match="failed to render"):
        render_prompt(inlining, strict=True)


def _sandbox_escaping_rule(sample: EvalSample) -> Path:
    """Lay down ``setup/playbook/rules/evil.md.j2`` whose body escapes the Jinja sandbox."""
    rules = sample.source_path.parent / "setup" / "playbook" / "rules"
    rules.mkdir(parents=True)
    rule = rules / "evil.md.j2"
    rule.write_text(
        "---\nid: evil\nname: Evil\ndescription: Escapes the sandbox.\n"
        "scope: always\npriority: 50\n---\n"
        "{{ lipsum.__globals__['os'].__name__ }}\n",
        encoding="utf-8",
    )
    return rule


@pytest.mark.parametrize("strict", [False, True], ids=["fake-runner", "real-runner"])
def test_sandbox_violation_in_included_rule_raises_prompt_resolution_error(
    tmp_path: Path, strict: bool
) -> None:
    """Regression: an included rule tripping the sandbox is a render error.

    ``RuleRegistryImpl`` raises ``rendering.jinja.TemplateSecurityError`` (a plain
    ``Exception``, not a jinja ``TemplateError``), which escaped ``render_prompt``
    as a raw traceback: ``playbook eval --run`` then exited 1 ("sample failed")
    instead of 2. The same escape written in the prompt body was already handled.
    """
    sample = _synthetic_sample(tmp_path, "Review.\n", includes_rules=("evil",))
    _sandbox_escaping_rule(sample)
    with pytest.raises(PromptResolutionError, match=r"synthetic-sample") as excinfo:
        render_prompt(sample, strict=strict)
    assert "evil.md.j2" in str(excinfo.value)
    assert "sandbox" in str(excinfo.value)


def test_sandbox_violation_in_prompt_body_raises_prompt_resolution_error(
    tmp_path: Path,
) -> None:
    """The direct escape (jinja's own ``SecurityError``) takes the same exit path."""
    sample = _synthetic_sample(tmp_path, "{{ lipsum.__globals__['os'].__name__ }}\n")
    with pytest.raises(PromptResolutionError, match=r"synthetic-sample.*__globals__"):
        render_prompt(sample, strict=False)


@pytest.mark.parametrize("with_dockerfile", [False, True])
def test_has_file_rule_gate_resolves_against_the_setup_tree(
    tmp_path: Path, with_dockerfile: bool
) -> None:
    """``has_file`` paths are checked inside ``setup/`` (the project the agent works in),
    never against the eval process's working directory."""
    sample = _synthetic_sample(tmp_path, "Review.\n", includes_rules=("needs-dockerfile",))
    setup = sample.source_path.parent / "setup"
    rules = setup / "playbook" / "rules"
    rules.mkdir(parents=True)
    (rules / "needs-dockerfile.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: needs-dockerfile
            name: Needs Dockerfile
            description: Gated on a Dockerfile.
            scope: always
            applies_if:
              has_file: ["Dockerfile"]
            ---
            DOCKERFILE RULE BODY
            """
        ),
        encoding="utf-8",
    )
    if with_dockerfile:
        (setup / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

    assert ("DOCKERFILE RULE BODY" in render_prompt(sample, strict=True)) is with_dockerfile
