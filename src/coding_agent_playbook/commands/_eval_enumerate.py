"""The read-only modes of ``playbook eval``: ``--list``, ``--show`` and the bare id (SPEC §12.8)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.roots import is_bundled_layer

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.evals.sample import EvalSample

#: Default runner when ``--runner`` is omitted (the one thin real runner).
_DEFAULT_RUNNER = "claude_code"


_RUN_HINT_TEMPLATE = (
    "Add --run to execute this sample against an agent and grade it:\n"
    "  playbook eval {sample_id} --run --runner fake    # hermetic no-op agent, no CLI\n"
    "  playbook eval {sample_id} --run                  # default runner: {default_runner}\n"
    "  playbook eval {sample_id} --run --judge llm      # also score the [rubric] layer\n"
    "Inspect it with `playbook eval --show {sample_id}`; coverage: `playbook eval --list`.\n"
    "To run it by hand, copy setup/ to a scratch repo and invoke /{slash}."
)


def _print_list(prompts: list[Prompt], samples: list[EvalSample]) -> int:
    """Tree-shape coverage report per SPEC §12.8.

    Layout (one prompt per block):

        === Eval samples ===
        <prompt-id> (<source>)
          ├── <sample-id>        ✓ sample defined
          │   └── N rubric criteria, M programmatic checks
          └── ...

        Total: P prompts, T eval samples, U prompts without samples
    """
    samples_by_id: dict[str, EvalSample] = {t.id: t for t in samples}
    samples_by_prompt: dict[str, list[EvalSample]] = {}
    for sample in samples:
        samples_by_prompt.setdefault(sample.prompt_id, []).append(sample)

    lines: list[str] = ["=== Eval samples ==="]
    rendered_any_prompt = False
    prompts_without_samples = 0
    for prompt in prompts:
        rendered_any_prompt = True
        prompt_id = prompt.frontmatter.id
        # Order samples by the prompt's eval_samples: frontmatter (the
        # authoring-order users expect). Samples present on-disk but missing
        # from the frontmatter still get rendered, in alphabetical order,
        # so authoring drift is visible.
        declared_order = prompt.frontmatter.eval_samples or []
        ordered: list[EvalSample] = []
        seen: set[str] = set()
        for declared_id in declared_order:
            candidate = samples_by_id.get(declared_id)
            if candidate is not None and candidate.prompt_id == prompt_id:
                ordered.append(candidate)
                seen.add(declared_id)
        for leftover in sorted(samples_by_prompt.get(prompt_id, []), key=lambda t: t.id):
            if leftover.id not in seen:
                ordered.append(leftover)
        prompt_samples = ordered
        source = _short_source(prompt.source_package)
        lines.append(f"{prompt_id} ({source})")
        if not prompt_samples:
            lines.append("  └── (no eval samples declared)         ⚠ consider adding samples")
            prompts_without_samples += 1
            continue
        for index, sample in enumerate(prompt_samples):
            is_last = index == len(prompt_samples) - 1
            connector = "└──" if is_last else "├──"
            sub_connector = "    " if is_last else "│   "
            id_padded = f"{sample.id:<36}"
            lines.append(f"  {connector} {id_padded}✓ sample defined")
            criteria_count = _count_rubric_criteria(sample)
            checks_count = _count_gate_checks(sample)
            lines.append(
                f"  {sub_connector}└── {criteria_count} rubric criteria, {checks_count} gate checks"
            )

    # Blank separator between the per-prompt blocks and the Total: line
    # is part of the SPEC §12.8 layout. On an empty repo (zero prompts
    # rendered), omit it so the header is immediately followed by the
    # Total without a stray blank line — keeps ``playbook eval --list`` clean
    # on a fresh project that hasn't authored prompts yet.
    if rendered_any_prompt:
        lines.append("")
    # Pluralize each count so single-item totals don't read "1 prompts"
    # (SPEC §12.8 example covers both singular and plural shapes). The
    # "prompts without samples" suffix has to be spelled out because the
    # head noun ("prompt") is not at the tail — naively appending "s" to
    # "prompt without samples" would emit "prompt without sampless".
    pwt_label = (
        "prompt without samples" if prompts_without_samples == 1 else "prompts without samples"
    )
    lines.append(
        f"Total: {_plural(len(prompts), 'prompt')}, "
        f"{_plural(len(samples), 'eval sample')}, "
        f"{prompts_without_samples} {pwt_label}"
    )
    print("\n".join(lines))
    return 0


def _plural(n: int, word: str) -> str:
    """Render ``n word`` with the English ``+s`` suffix when ``n != 1``.

    Used by ``playbook eval --list`` so the ``Total:`` line reads ``1 prompt``
    instead of ``1 prompts``. Only works for words whose plural is formed
    by appending ``s`` to the supplied lemma — compound subjects whose head
    noun is not at the tail (e.g. ``"prompt without samples"``) must be
    handled at the call site.
    """
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _print_show(sample_id: str, samples: list[EvalSample], prompts: list[Prompt]) -> int:
    """Detailed sample dump per SPEC §12.8."""
    sample = next((t for t in samples if t.id == sample_id), None)
    if sample is None:
        print(f"error: no eval sample with id {sample_id!r}", file=sys.stderr)
        return 1

    lines: list[str] = []
    lines.append(f"Sample: {sample.id}")
    lines.append(f"Source: {_display_source_path(sample)}")
    lines.append(f"Prompt under test: {sample.prompt_id}")
    lines.append(f"Description: {sample.description}")
    lines.append("Setup:")
    # ``project_kind`` is the lone mock-detector fact carried by [setup] (the
    # other facts — python version, deps — live in setup/pyproject.toml since
    # C11). Any extras (e.g. ``ml_stack``) print alongside it.
    fact_bits = [f"project_kind={sample.setup.project_kind}"]
    for key, value in sorted(sample.setup.extra_facts.items()):
        fact_bits.append(f"{key}={value!r}")
    lines.append(f"  Mock facts: {', '.join(fact_bits)}")
    files_list = ", ".join(str(p) for p in sample.setup.files) or "(none)"
    lines.append(f"  Files ({len(sample.setup.files)}): {files_list}")
    lines.append("Invocation:")
    # The slash name is the prompt's own slash (which the schema allows to
    # differ from the prompt id — e.g. id="generate-tests" + slash="gen-tests").
    # Falling back to the prompt_id when the prompt is missing keeps --show
    # useful in mid-authoring states where the prompt hasn't been written yet,
    # but for any resolved prompt we honour its declared slash.
    prompt = next((p for p in prompts if p.frontmatter.id == sample.prompt_id), None)
    slash = prompt.frontmatter.slash if prompt is not None else sample.prompt_id
    lines.append(f"  Prompt: /{slash}")
    lines.append(f'  Args: "{sample.invocation.prompt_args}"')
    if sample.invocation.input_variables:
        bindings = ", ".join(f"{k}={v}" for k, v in sample.invocation.input_variables.items())
        lines.append(f"  Variables: {bindings}")

    if sample.gate is None:
        lines.append("Gate: (none)")
    else:
        gate_checks = _gate_check_descriptions(sample)
        expr = sample.gate.expr or " and ".join(sample.gate.bind) or "(empty)"
        lines.append(f"Gate (deterministic, {len(gate_checks)} checks, expr: {expr}):")
        for desc in gate_checks:
            lines.append(f"  - {desc}")

    if sample.rubric is None:
        lines.append("Rubric: (none)")
    else:
        criteria = _rubric_criteria_with_weights(sample)
        lines.append(f"Rubric (manual / LLM-judge, {len(criteria)} criteria):")
        for weight, criterion in criteria:
            prefix = "" if weight is None else f"{weight}: "
            lines.append(f"  - {prefix}{criterion}")

    lines.append(f"Verdict: {sample.verdict}")

    print("\n".join(lines))
    return 0


def _print_run_hint(sample_id: str, samples: list[EvalSample], prompts: list[Prompt]) -> int:
    """Bare ``playbook eval <id>`` — verify the sample exists, then print how to run it.

    Exit 0. Unknown sample ids exit 1 so typos surface.
    """
    sample = next((t for t in samples if t.id == sample_id), None)
    if sample is None:
        print(f"error: no eval sample with id {sample_id!r}", file=sys.stderr)
        return 1
    # If the prompt is loadable, use its slash; otherwise fall back to the
    # prompt id so the message is still useful in mid-authoring states.
    slash = sample.prompt_id
    for prompt in prompts:
        if prompt.frontmatter.id == sample.prompt_id:
            slash = prompt.frontmatter.slash
            break
    print(f"playbook eval {sample_id}:")
    print(
        _RUN_HINT_TEMPLATE.format(sample_id=sample_id, slash=slash, default_runner=_DEFAULT_RUNNER)
    )
    return 0


def _short_source(source_package: str) -> str:
    """Render the prompt's source package as ``"engine"``/``"overlay X"``/etc.

    Matches the SPEC §12.8 example where the engine is annotated ``engine`` and
    overlay packages get ``overlay <name>``.
    """
    if source_package == "coding_agent_playbook":
        return "engine"
    if source_package == "<repo-local>":
        return "repo-local"
    return f"overlay {source_package}"


def _display_source_path(sample: EvalSample) -> str:
    """Label the sample's directory for the ``Source:`` line, by its layer.

    SPEC §12.8 shows a layer-relative path, never the absolute filesystem path,
    which would leak the local workspace layout into the output. The label is
    built from the layer kind and ``<dir>``, the sample directory's name
    (``sample.source_path.parent.name``, never ``sample.id``, which nothing ties to
    the directory). No path segment is searched for, so an unusual layout can
    neither crash ``playbook eval --show`` nor change the label:

    - bundled layers (engine, bundled plugins): ``<source_package>/eval_samples/<dir>/``;
    - third-party overlays: ``<source_package>/resources/eval_samples/<dir>/``,
      still a real package-relative path;
    - repo-local samples: ``playbook/eval_samples/<dir>/``.

    The trailing ``/`` makes the label read as a directory (the SPEC example).
    """
    sample_dir = sample.source_path.parent.name
    if sample.source_package == "<repo-local>":
        return f"playbook/eval_samples/{sample_dir}/"
    if is_bundled_layer(sample.source_package):
        return f"{sample.source_package}/eval_samples/{sample_dir}/"
    return f"{sample.source_package}/resources/eval_samples/{sample_dir}/"


def _count_gate_checks(sample: EvalSample) -> int:
    """Number of top-level ``[gate.bind]`` handles (the deterministic gate checks).

    A composed handle (an ``all_of``/``any_of`` group) counts as one — the summary
    line is a coarse handle count, not a deep leaf count.
    """
    if sample.gate is None:
        return 0
    return len(sample.gate.bind)


def _count_rubric_criteria(sample: EvalSample) -> int:
    """Number of judged criteria the ``[rubric.bind]`` rubric groups declare."""
    return len(_rubric_criteria_with_weights(sample))


def _gate_check_descriptions(sample: EvalSample) -> list[str]:
    """A one-line description of each ``[gate.bind]`` handle for ``--show``.

    Renders the handle name + a short shape summary (the ``check`` kind +
    path/pattern for a standalone file/threshold check, or the boolean-group /
    ref shape). Reads the raw binding tables — no compilation — so ``--show`` works
    even on a sample that would fail to compile.
    """
    if sample.gate is None:
        return []
    out: list[str] = []
    for name, binding in sample.gate.bind.items():
        out.append(f"{name}: {_describe_binding(binding)}")
    return out


def _describe_binding(binding: dict[str, object]) -> str:
    """Short human description of one handle binding (its shape + key fields)."""
    if "check" in binding:
        kind = binding["check"]
        path = binding.get("path")
        pattern = binding.get("pattern")
        detail = f" {path}" if path else ""
        detail += f" ~/{pattern}/" if pattern else ""
        return f"check {kind}{detail}"
    if "ref" in binding:
        return f"ref {binding['ref']}"
    if "rubric" in binding:
        criteria = binding["rubric"]
        n = len(criteria) if isinstance(criteria, list) else 0
        return f"rubric ({n} criteria)"
    for group in ("all_of", "any_of", "not"):
        if group in binding:
            return f"{group} group"
    return "(unknown)"


def _rubric_criteria_with_weights(sample: EvalSample) -> list[tuple[float | None, str]]:
    """The ``(weight, criterion)`` pairs across every ``[rubric.bind]`` rubric group.

    Reads the raw binding tables (no compilation): each ``rubric`` group's entries
    are ``{judge=…, weight=…}``, flattened across all rubric-group handles. A
    non-``rubric`` handle (a ref or composed boolean) contributes nothing here.
    """
    if sample.rubric is None:
        return []
    out: list[tuple[float | None, str]] = []
    for binding in sample.rubric.bind.values():
        criteria = binding.get("rubric")
        if not isinstance(criteria, list):
            continue
        for entry in criteria:
            if not isinstance(entry, dict):
                continue
            judge = entry.get("judge")
            weight = entry.get("weight")
            if isinstance(judge, str):
                w = float(weight) if isinstance(weight, (int, float)) else None
                out.append((w, judge))
    return out
