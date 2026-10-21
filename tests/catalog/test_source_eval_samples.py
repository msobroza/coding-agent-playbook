"""Tests for ``FileSystemArtifactSource.list_eval_samples`` (PR 11).

PR 5 shipped this method as a stub returning ``[]``; PR 11 makes it walk the
engine's ``catalog/core/eval_samples/`` tree, each overlay's (a bundled plugin's
``catalog/plugins/<name>/eval_samples/``, a third-party overlay package's
``resources/eval_samples/``), and the consumer repo's ``playbook/eval_samples/``.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.evals.sample import EvalSample

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


SAMPLE_TOML_TEMPLATE = """\
id = "{sample_id}"
prompt_id = "{prompt_id}"
description = "{description}"
"""


def _make_overlay_with_eval_sample(
    tmp_path: Path,
    package_name: str,
    sample_id: str,
    *,
    prompt_id: str = "demo",
    description: str = "An overlay sample",
) -> None:
    """Create a tiny third-party overlay package with one eval sample under resources/eval_samples/."""
    pkg_dir = tmp_path / package_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("")
    sample_dir = pkg_dir / "resources" / "eval_samples" / sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "sample.toml").write_text(
        SAMPLE_TOML_TEMPLATE.format(
            sample_id=sample_id, prompt_id=prompt_id, description=description
        ),
        encoding="utf-8",
    )
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
    if package_name in sys.modules:
        importlib.reload(sys.modules[package_name])


@pytest.fixture
def overlay_cleanup(tmp_path: Path) -> Iterator[None]:
    yield
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))
    for mod_name in list(sys.modules):
        if mod_name.startswith("temp_eval_overlay"):
            del sys.modules[mod_name]


def test_list_eval_samples_walks_engine_resources(tmp_path: Path) -> None:
    """The engine ships eval samples under ``catalog/core/eval_samples/``
    (resolved through ``catalog.roots``). Confirm
    the walker picks them up and tags them with
    ``source_package="coding_agent_playbook"``."""
    source = FileSystemArtifactSource(repo_root=tmp_path)
    samples = source.list_eval_samples()
    engine_samples = [t for t in samples if t.source_package == "coding_agent_playbook"]
    assert engine_samples, "expected at least one engine-shipped eval sample"
    assert all(t.source_package == "coding_agent_playbook" for t in engine_samples)


def test_list_eval_samples_walks_overlay_packages(tmp_path: Path, overlay_cleanup: None) -> None:
    _make_overlay_with_eval_sample(tmp_path, "temp_eval_overlay", "overlay-sample-foo")
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_eval_overlay"],
    )
    samples = source.list_eval_samples()
    overlay_samples = [t for t in samples if t.source_package == "temp_eval_overlay"]
    assert len(overlay_samples) == 1
    sample = overlay_samples[0]
    assert isinstance(sample, EvalSample)
    assert sample.id == "overlay-sample-foo"


def test_list_eval_samples_walks_repo_local(tmp_path: Path) -> None:
    sample_dir = tmp_path / "playbook" / "eval_samples" / "local-sample"
    sample_dir.mkdir(parents=True)
    (sample_dir / "sample.toml").write_text(
        SAMPLE_TOML_TEMPLATE.format(
            sample_id="local-sample", prompt_id="local-prompt", description="repo-local"
        ),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=tmp_path)
    samples = source.list_eval_samples()
    repo_local_samples = [t for t in samples if t.source_package == "<repo-local>"]
    assert len(repo_local_samples) == 1
    assert repo_local_samples[0].id == "local-sample"


def test_list_eval_samples_aggregates_overlay_and_repo_local(
    tmp_path: Path, overlay_cleanup: None
) -> None:
    _make_overlay_with_eval_sample(tmp_path, "temp_eval_overlay2", "overlay-sample-bar")
    repo_local = tmp_path / "playbook" / "eval_samples" / "repo-sample"
    repo_local.mkdir(parents=True)
    (repo_local / "sample.toml").write_text(
        SAMPLE_TOML_TEMPLATE.format(
            sample_id="repo-sample", prompt_id="p", description="repo sample"
        ),
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(
        repo_root=tmp_path,
        overlay_packages=["temp_eval_overlay2"],
    )
    samples = source.list_eval_samples()
    non_engine = [t for t in samples if t.source_package != "coding_agent_playbook"]
    ids = {t.id for t in non_engine}
    assert ids == {"overlay-sample-bar", "repo-sample"}
    by_id = {t.id: t for t in non_engine}
    assert by_id["overlay-sample-bar"].source_package == "temp_eval_overlay2"
    assert by_id["repo-sample"].source_package == "<repo-local>"
