"""Eval-sample loader: parses one sample directory's ``sample.toml`` into an ``EvalSample``.

It never walks ``eval_samples/``: :mod:`coding_agent_playbook.evals.task_registry`
finds the sample directories and passes in the task (the prompt id) each one
belongs to.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.sample import EvalSample

if TYPE_CHECKING:
    from pathlib import Path


def load_eval_sample_from_dir(
    sample_dir: Path,
    *,
    task: str,
    source_package: str,
) -> EvalSample:
    """Load the ``sample.toml`` inside ``sample_dir``, a sample of the prompt ``task``.

    The sample's id must be ``<task>/<sample_dir.name>``, so the id always says
    where the sample lives.

    Raises :exc:`FileNotFoundError` if ``sample.toml`` is missing, and
    :exc:`ValueError` (its message starting with the ``sample.toml`` path, for
    jump-to-file) on malformed TOML, a schema violation or an id that does not
    match the directory.

    Example::

        >>> load_eval_sample_from_dir(Path("eval_samples/review/spot-the-bug"),
        ...     task="review", source_package="coding_agent_playbook").id  # doctest: +SKIP
        'review/spot-the-bug'
    """
    sample_toml = sample_dir / "sample.toml"
    if not sample_toml.is_file():
        raise FileNotFoundError(f"no sample.toml in {sample_dir}")
    try:
        with sample_toml.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{sample_toml}: malformed TOML: {exc}") from exc
    try:
        sample = EvalSample.from_dict(
            data, prompt_id=task, source_path=sample_toml, source_package=source_package
        )
    except ValueError as exc:
        raise ValueError(f"{sample_toml}: {exc}") from exc
    expected_id = f"{task}/{sample_dir.name}"
    if sample.id != expected_id:
        raise ValueError(
            f"{sample_toml}: id {sample.id!r} does not match its directory; "
            f"a sample in eval_samples/{expected_id}/ has id {expected_id!r}"
        )
    return sample
