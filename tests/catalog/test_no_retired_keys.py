"""No shipped artifact carries a retired bookkeeping key (#281, #285).

``version`` and ``eval_samples`` are refused by the loaders; this pins the
catalog itself, so a vendored or newly authored file that still has one fails
here with its path, not later in a consumer's sync.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.retired_keys import RETIRED_KEYS
from tests._catalog import CORE_ROOT, MARKDOWN_SUFFIXES, PLUGINS_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: Directories whose markdown is example or fixture content, not an artifact.
_NOT_ARTIFACTS = frozenset({"setup", "solution", "examples", "references"})


def _artifact_markdown() -> list[Path]:
    return [
        path
        for root in (CORE_ROOT, PLUGINS_ROOT)
        for path in sorted(root.rglob("*"))
        if path.name.endswith(MARKDOWN_SUFFIXES)
        and not _NOT_ARTIFACTS.intersection(path.relative_to(root).parts)
        and path.read_text(encoding="utf-8").startswith("---\n")
    ]


def _sample_tomls() -> list[Path]:
    return sorted(
        path
        for root in (CORE_ROOT, PLUGINS_ROOT)
        for path in root.rglob("sample.toml")
        if path.parents[2].name == "eval_samples"
    )


def test_no_artifact_frontmatter_carries_a_retired_key() -> None:
    artifacts = _artifact_markdown()
    offenders = [
        f"{path}: {key}"
        for path in artifacts
        for key in split_frontmatter(path.read_text(encoding="utf-8"))[0]
        if key in RETIRED_KEYS
    ]

    assert len(artifacts) > 300
    assert offenders == []


def test_no_eval_sample_carries_a_retired_key() -> None:
    samples = _sample_tomls()
    offenders = [
        f"{path}: {key}"
        for path in samples
        for key in tomllib.loads(path.read_text(encoding="utf-8"))
        if key in RETIRED_KEYS
    ]

    assert samples
    assert offenders == []
