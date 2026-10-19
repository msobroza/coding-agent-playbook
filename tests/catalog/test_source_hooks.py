"""Hook discovery in ``FileSystemArtifactSource`` (specs/prK-lifecycle-hooks.md §A.1, §A.5).

A hook is a directory holding ``HOOK.md`` or ``HOOK.md.j2``, found at any depth
under each layer's ``hooks/`` root, in :meth:`layer_roots` order. Two markers
in one directory and a hook nested under another are H2 errors.
``collect_hooks`` returns every error; ``list_hooks`` raises the first.
Kept apart from ``tests/catalog/test_source.py`` for the file-size budget.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.catalog.source import FileSystemArtifactSource

if TYPE_CHECKING:
    from collections.abc import Callable

    HookFactory = Callable[..., Path]

_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")


#: An importable engine stand-in without a ``resources/`` tree (the stdlib's ``json``):
#: the real engine ships the §E hook pack (Track K5) in ``catalog/core/hooks/``,
#: which these discovery tests must not see.
_HOOKLESS_ENGINE = "json"


def _hooks_root(repo: Path) -> Path:
    return repo / "playbook" / "hooks"


def _local_source(repo: Path) -> FileSystemArtifactSource:
    """A source walking only ``repo``'s ``playbook/hooks`` (its engine layer has no hooks)."""
    return FileSystemArtifactSource(repo_root=repo, engine_package=_HOOKLESS_ENGINE)


def _package_hooks(name: str) -> Path:
    """``<package>/resources/hooks`` of a package built by ``make_package``."""
    module = importlib.import_module(name)
    assert module.__file__ is not None
    return Path(module.__file__).parent / "resources" / "hooks"


def _ids(source: FileSystemArtifactSource) -> list[str]:
    return [hook.frontmatter.id for hook in source.list_hooks()]


def test_list_hooks_discovers_hook_dirs_at_any_depth(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    root = _hooks_root(tmp_path)
    make_hook(root, "top-level", category="")
    make_hook(root, "in-category")
    make_hook(root / "a" / "b", "deep", marker="HOOK.md.j2")

    hooks = _local_source(tmp_path).list_hooks()

    by_id = {hook.frontmatter.id: hook for hook in hooks}
    assert sorted(by_id) == ["deep", "in-category", "top-level"]
    assert by_id["deep"].is_templated is True
    assert by_id["deep"].source_path == root / "a" / "b" / "protect" / "deep" / "HOOK.md.j2"
    assert {hook.source_package for hook in hooks} == {"<repo-local>"}


def test_list_hooks_orders_engine_then_overlays_then_repo_local(
    tmp_path: Path, make_package: Callable[..., str], make_hook: HookFactory
) -> None:
    engine = make_package("k1_fake_engine", resources=True)
    first = make_package("k1_overlay_b", resources=True)
    second = make_package("k1_overlay_a", resources=True)
    for package in (second, first, engine):
        make_hook(_package_hooks(package), "guard-x")
    make_hook(_hooks_root(tmp_path), "guard-x")
    source = FileSystemArtifactSource(
        repo_root=tmp_path, engine_package=engine, overlay_packages=[first, second]
    )

    packages = [hook.source_package for hook in source.list_hooks()]

    assert packages == [engine, first, second, "<repo-local>"]


def test_list_hooks_is_empty_without_any_hooks_dir(tmp_path: Path) -> None:
    assert _local_source(tmp_path).list_hooks() == []


def test_list_hooks_skips_dot_directories(tmp_path: Path, make_hook: HookFactory) -> None:
    root = _hooks_root(tmp_path)
    make_hook(root, "kept")
    make_hook(root / ".cache", "hidden")
    make_hook(root, "dotted", category=".git")

    assert _ids(_local_source(tmp_path)) == ["kept"]


def test_list_hooks_ignores_other_markdown_and_scripts_readme(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    hook_md = make_hook(_hooks_root(tmp_path), "guard-x", scripts=True)
    (hook_md.parent / "README.md").write_text("# not a hook\n", encoding="utf-8")
    (hook_md.parent / "scripts" / "README.md").write_text("---\nbroken: [\n", encoding="utf-8")
    (hook_md.parent.parent / "NOTES.md").write_text("notes\n", encoding="utf-8")
    (hook_md.parent / "HOOK.md.bak").write_text("not the marker\n", encoding="utf-8")

    assert _ids(_local_source(tmp_path)) == ["guard-x"]


def test_hook_nested_under_another_hook_is_rejected(tmp_path: Path, make_hook: HookFactory) -> None:
    outer = make_hook(_hooks_root(tmp_path), "outer", scripts=True)
    nested = make_hook(outer.parent / "scripts", "inner", category="")

    hooks, errors = _local_source(tmp_path).collect_hooks()

    assert [hook.frontmatter.id for hook in hooks] == ["outer"]
    assert len(errors) == 1
    assert errors[0].where == str(nested)
    assert errors[0].field == "layout"
    assert f"nested under hook directory {str(outer.parent)!r}" in str(errors[0])


def test_hook_md_and_hook_md_j2_together_are_rejected(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    plain = make_hook(_hooks_root(tmp_path), "guard-x")
    make_hook(_hooks_root(tmp_path), "guard-x", marker="HOOK.md.j2")
    make_hook(_hooks_root(tmp_path), "guard-y")

    hooks, errors = _local_source(tmp_path).collect_hooks()

    assert [hook.frontmatter.id for hook in hooks] == ["guard-y"]
    assert len(errors) == 1
    assert errors[0].where == str(plain.parent)
    assert "both HOOK.md and HOOK.md.j2" in str(errors[0])


def test_hook_under_a_rejected_two_marker_dir_is_still_nested(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    outer = make_hook(_hooks_root(tmp_path), "outer")
    make_hook(_hooks_root(tmp_path), "outer", marker="HOOK.md.j2")
    make_hook(outer.parent, "inner", category="")

    hooks, errors = _local_source(tmp_path).collect_hooks()

    assert hooks == []
    assert [error.field for error in errors] == ["layout", "layout"]


def test_scripts_dir_recorded_only_when_present(tmp_path: Path, make_hook: HookFactory) -> None:
    with_scripts = make_hook(_hooks_root(tmp_path), "with-scripts", scripts=True)
    make_hook(_hooks_root(tmp_path), "without-scripts")
    (with_scripts.parent.parent / "without-scripts" / "scripts").write_text("a file\n")

    by_id = {h.frontmatter.id: h for h in _local_source(tmp_path).list_hooks()}

    assert by_id["with-scripts"].scripts_dir == with_scripts.parent / "scripts"
    assert by_id["without-scripts"].scripts_dir is None


def test_collect_hooks_returns_every_error_without_raising(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    root = _hooks_root(tmp_path)
    bad_timeout = make_hook(root, "bad-timeout", timeout="2s")
    bad_fence = make_hook(root, "bad-fence")
    bad_fence.write_text("no frontmatter here\n", encoding="utf-8")
    make_hook(root, "good")

    hooks, errors = _local_source(tmp_path).collect_hooks()

    assert [hook.frontmatter.id for hook in hooks] == ["good"]
    assert sorted(error.where for error in errors) == sorted([str(bad_fence), str(bad_timeout)])
    assert all(isinstance(error, HookSchemaError) for error in errors)


def test_list_hooks_raises_first_hook_schema_error(tmp_path: Path, make_hook: HookFactory) -> None:
    root = _hooks_root(tmp_path)
    first = make_hook(root, "a-first", timeout="2s")
    make_hook(root, "b-second", tier=3)

    with pytest.raises(HookSchemaError) as caught:
        _local_source(tmp_path).list_hooks()

    assert caught.value.where == str(first)
    assert caught.value.field == "timeout"


@_POSIX_ONLY
def test_symlinked_directories_are_not_followed(tmp_path: Path, make_hook: HookFactory) -> None:
    outside = tmp_path / "elsewhere"
    make_hook(outside, "linked")
    root = _hooks_root(tmp_path)
    make_hook(root, "kept")
    (root / "via-link").symlink_to(outside, target_is_directory=True)

    assert _ids(_local_source(tmp_path)) == ["kept"]


@_POSIX_ONLY
def test_marker_linking_out_of_its_layer_is_rejected(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    outside = make_hook(tmp_path / "elsewhere", "linked")
    link = _hooks_root(tmp_path) / "linked" / "HOOK.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    hooks, errors = _local_source(tmp_path).collect_hooks()

    assert hooks == []
    assert [error.where for error in errors] == [str(link)]
    assert "outside its layer" in str(errors[0])


def _broken_link(marker: Path) -> None:
    marker.symlink_to(marker.parent / "missing.md")


def _fifo(marker: Path) -> None:
    os.mkfifo(marker)  # reading one would block forever


@_POSIX_ONLY
@pytest.mark.parametrize("make_marker", [_broken_link, _fifo], ids=["broken-link", "fifo"])
def test_marker_that_is_not_a_regular_file_is_an_error(
    tmp_path: Path, make_hook: HookFactory, make_marker: Callable[[Path], None]
) -> None:
    marker = _hooks_root(tmp_path) / "odd" / "HOOK.md"
    marker.parent.mkdir(parents=True)
    make_marker(marker)
    make_hook(_hooks_root(tmp_path), "good")

    hooks, errors = _local_source(tmp_path).collect_hooks()

    assert [hook.frontmatter.id for hook in hooks] == ["good"]
    assert [error.where for error in errors] == [str(marker)]
    assert "is not a regular file" in str(errors[0])


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX modes, ignored by root"
)
def test_unreadable_marker_is_an_error_not_a_traceback(
    tmp_path: Path, make_hook: HookFactory
) -> None:
    marker = make_hook(_hooks_root(tmp_path), "locked")
    marker.chmod(0)
    try:
        hooks, errors = _local_source(tmp_path).collect_hooks()
    finally:
        marker.chmod(0o644)

    assert hooks == []
    assert [error.where for error in errors] == [str(marker)]
    assert "cannot be read" in str(errors[0])
