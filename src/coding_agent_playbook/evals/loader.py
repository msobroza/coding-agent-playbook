"""Eval-sample loader. Parses ``eval_samples/<id>/sample.toml`` into ``EvalSample``."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.sample import EvalSample

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def discover_eval_sample_dirs(root: Path) -> Iterator[Path]:
    """Yield each ``<root>/<id>/`` subdir that contains a ``sample.toml``.

    Skips dot-prefixed directories (``.git``, ``.cache``, ``__pycache__``, etc.)
    so accidentally nested infrastructure doesn't get loaded as samples. Results
    are sorted alphabetically by directory name for deterministic ordering in
    ``playbook eval --list`` output.

    Returns nothing (no exception) when ``root`` does not exist — overlay
    packages can ship without an ``eval_samples/`` directory.
    """
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if (entry / "sample.toml").is_file():
            yield entry


def load_eval_sample_from_dir(
    sample_dir: Path,
    *,
    source_package: str,
) -> EvalSample:
    """Load and parse the ``sample.toml`` inside ``sample_dir`` into an ``EvalSample``.

    Raises :exc:`FileNotFoundError` if ``sample.toml`` is missing.

    Wraps any TOML parse error or schema violation from
    :meth:`EvalSample.from_dict` into a :exc:`ValueError` whose message embeds
    the full ``sample.toml`` path so users can jump straight to the offending
    file.
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
        return EvalSample.from_dict(data, source_path=sample_toml, source_package=source_package)
    except ValueError as exc:
        raise ValueError(f"{sample_toml}: {exc}") from exc
