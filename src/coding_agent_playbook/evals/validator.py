"""Eval-sample validator. Enforces the SPEC §15.2 structural rules.

Run by :mod:`coding_agent_playbook.validation.checks` to catch authoring mistakes
at commit time. Each violation is aggregated; callers print them in order and exit
non-zero if the list is non-empty.

The schema rules (``[gate]``/``[rubric]``/``[verdict]``) are checked by **trial-
compiling** the sample via :func:`~coding_agent_playbook.evals.sample.compile_eval_sample`
and turning any :exc:`ValueError` / :exc:`KeyError` (incl.
:exc:`~coding_agent_playbook.evals.compile._expr.ExprError`, a ``ValueError`` subclass) into
an :class:`EvalValidationError`. The compiler already validates: at-least-one
layer present, unknown check ids / metric names / gate-refs / rubric-refs,
malformed handle bindings, expression identifiers ⊄ bind keys, the rubric
weight-sum, and verdict identifiers ⊄ present layers. The non-schema rules
(setup.files exist, an authored ``setup/pyproject.toml`` parses, prompt_id
resolves, prompt↔sample back-reference symmetry) and a light ``[aggregate]``
shape check are kept here.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.evals.sample import EvalSample

#: The aggregate handle ``metric`` axis the multi-trial layer recognizes.
_AGGREGATE_METRICS = frozenset({"pass_at_k", "pass_pow_k"})

#: The aggregate ``over`` axis a handle may reduce.
_AGGREGATE_OVER = frozenset({"gate", "rubric", "verdict"})


@dataclass(frozen=True)
class EvalValidationError:
    """One validation failure. ``path`` points at the offending ``sample.toml``."""

    path: Path
    message: str


def validate_samples(
    samples: list[EvalSample],
    prompts: list[Prompt],
) -> list[EvalValidationError]:
    """Run the SPEC §15.2 checks against the loaded sample + prompt lists.

    The rules:

    1. Each ``sample.toml`` is well-formed — enforced upstream by the loader;
       a sample object reaching the validator has already passed parsing.
    2. The ``[gate]``/``[rubric]``/``[verdict]`` schema compiles cleanly —
       trial-compile via :func:`compile_eval_sample`, surfacing any compiler fault
       (unknown check/metric/ref, malformed binding, expr idents ⊄ bind keys,
       rubric weight-sum, verdict idents ⊄ present layers, no layer at all).
    3. A light ``[aggregate]`` shape check (each handle names a known aggregate
       ``metric``, an integer ``k >= 1``, and an ``over`` axis); the multi-trial
       grading itself runs in the runner.
    4. Each sample's ``setup.files`` must exist under ``<sample_dir>/setup/``.
       When ``setup/pyproject.toml`` is present it must parse as TOML; dep
       installability is the runner's concern (``uv sync``), not the validator's.
    5. Each sample's ``prompt_id`` resolves to a known prompt.
    6. Each sample is listed in its referenced prompt's ``eval_samples:`` frontmatter
       (sample → prompt direction of the symmetry check).
    7. Each prompt's ``eval_samples:`` references an on-disk sample (prompt → sample
       direction, per SPEC §6.5.5 rule 1).

    Aggregates every violation; never raises. Empty list means OK.
    """
    errors: list[EvalValidationError] = []
    prompts_by_id = {p.frontmatter.id: p for p in prompts}
    samples_by_id = {t.id: t for t in samples}

    for sample in samples:
        # Rule 2: the gate/rubric/verdict schema must compile.
        errors.extend(_validate_schema(sample))

        # Rule 3: light [aggregate] shape checks (multi-trial grading runs in the runner).
        if sample.aggregate is not None:
            errors.extend(_validate_aggregate(sample))

        # Rule 4: setup.files must exist relative to <sample_dir>/setup/, and an
        # authored setup/pyproject.toml must parse as TOML. The runner installs
        # its deps via ``uv sync``; installability is not validated here.
        sample_dir = sample.source_path.parent
        setup_root = sample_dir / "setup"
        for declared in sample.setup.files:
            absolute = setup_root / declared
            if not absolute.is_file():
                errors.append(
                    EvalValidationError(
                        path=sample.source_path,
                        message=(f"setup.files declares {declared} but {absolute} not found"),
                    )
                )
        pyproject = setup_root / "pyproject.toml"
        if pyproject.is_file():
            try:
                tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                errors.append(
                    EvalValidationError(
                        path=sample.source_path,
                        message=f"setup/pyproject.toml is not valid TOML: {exc}",
                    )
                )

        # Rule 5: prompt_id must resolve to a known prompt.
        prompt = prompts_by_id.get(sample.prompt_id)
        if prompt is None:
            errors.append(
                EvalValidationError(
                    path=sample.source_path,
                    message=f"prompt_id {sample.prompt_id!r} does not exist",
                )
            )
            # Rule 6 only meaningful when the prompt exists — skip the
            # back-reference check to avoid a confusing follow-on error.
            continue

        # Rule 6: the prompt's eval_samples: frontmatter must list this sample.
        prompt_eval_samples = prompt.frontmatter.eval_samples or []
        if sample.id not in prompt_eval_samples:
            errors.append(
                EvalValidationError(
                    path=sample.source_path,
                    message=(
                        f"prompt {sample.prompt_id!r} does not list eval_sample "
                        f"{sample.id!r} in its eval_samples: frontmatter"
                    ),
                )
            )

    # Rule 7 (prompt → sample direction): every eval_samples: reference must
    # resolve to an on-disk sample. Catches the case where a sample was renamed
    # or deleted but its prompt still references it.
    for prompt in prompts:
        for declared_id in prompt.frontmatter.eval_samples or []:
            if declared_id not in samples_by_id:
                # Anchor the error at the prompt's source so users jump to
                # the prompt frontmatter to fix the dangling reference.
                anchor_path = prompt.source_path or Path(prompt.frontmatter.id)
                errors.append(
                    EvalValidationError(
                        path=anchor_path,
                        message=(
                            f"declares eval_sample {declared_id!r} but "
                            f"eval_samples/{declared_id}/ not found"
                        ),
                    )
                )

    return errors


def _validate_schema(sample: EvalSample) -> list[EvalValidationError]:
    """Trial-compile the sample; turn any compiler fault into a validation error.

    :func:`compile_eval_sample` raises :exc:`ValueError` (incl.
    :exc:`~coding_agent_playbook.evals.compile._expr.ExprError`) or :exc:`KeyError` on any
    structural fault. A clean compile means the gate/rubric/verdict schema is
    well-formed. Imported lazily so the validator module stays import-light and
    free of any eval ↔ evaluator import cycle at module load.
    """
    from coding_agent_playbook.evals.sample import compile_eval_sample

    try:
        compile_eval_sample(sample)
    except (ValueError, KeyError) as exc:
        # KeyError's str() carries surrounding quotes; strip them for a clean message.
        detail = str(exc).strip("'\"") if isinstance(exc, KeyError) else str(exc)
        return [EvalValidationError(path=sample.source_path, message=detail)]
    return []


def _validate_aggregate(sample: EvalSample) -> list[EvalValidationError]:
    """Light shape check of the ``[aggregate.bind]`` handles (grading runs in the runner).

    Each aggregate handle must name a known ``metric`` (``pass_at_k`` /
    ``pass_pow_k``), an integer ``k >= 1``, and an ``over`` axis in
    ``{"gate", "rubric", "verdict"}``. Aggregates every violation; never raises.
    """
    aggregate = sample.aggregate
    assert aggregate is not None  # caller guards; narrows for mypy.
    errors: list[EvalValidationError] = []

    for name, handle in aggregate.bind.items():
        metric = handle.get("metric")
        if metric not in _AGGREGATE_METRICS:
            errors.append(
                EvalValidationError(
                    path=sample.source_path,
                    message=(
                        f"[aggregate.bind.{name}] metric {metric!r} is invalid; "
                        f"must be one of {', '.join(sorted(_AGGREGATE_METRICS))}"
                    ),
                )
            )
        k = handle.get("k")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            errors.append(
                EvalValidationError(
                    path=sample.source_path,
                    message=f"[aggregate.bind.{name}] k must be an integer >= 1, got {k!r}",
                )
            )
        over = handle.get("over")
        if over not in _AGGREGATE_OVER:
            errors.append(
                EvalValidationError(
                    path=sample.source_path,
                    message=(
                        f"[aggregate.bind.{name}] over {over!r} is invalid; "
                        f"must be one of {', '.join(sorted(_AGGREGATE_OVER))}"
                    ),
                )
            )

    return errors
