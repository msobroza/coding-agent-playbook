"""Repository guards over the catalog layout: what the build and consumer repos rely on.

Each pin guards a mistake that would otherwise pass silently:

* a tracked file matching ``.gitignore``: hatch's force-include of ``catalog/``
  ignores ``.gitignore``, so a wheel built from the tree ships the file while
  one built from the sdist drops it;
* a bundled plugin directory that breaks the leaf rule (:func:`bundled_plugins`
  skips it, so the plugin silently vanishes) or ships no kind directory (it is
  listed and passes the preflight, but contributes nothing);
* a bundled artifact linking to a layer-root file (``README.md``, ``LICENSE``,
  ``ATTRIBUTIONS.md``): those ship in the wheel but are never synced, so the link
  breaks in every consumer repo while the link gate, whose containment root now
  includes them, still passes;
* content left inside the Python package, which must hold logic only
  (acceptance 2);
* an editable checkout resolving the catalog anywhere but the repository's
  ``catalog/``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

import pytest

from coding_agent_playbook.catalog.roots import _PACKAGE_DIR, catalog_root
from coding_agent_playbook.validation.link_check import extract_markdown_links
from tests._catalog import CATALOG_ROOT, CORE_ROOT, PLUGINS_ROOT, REPO_ROOT, bundled_plugin_dirs

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_GIT_TIMEOUT_SECONDS = 30
#: A bundled plugin needs at least one of these, or it ships nothing.
_KIND_DIRS = ("rules", "prompts", "skills", "eval_tasks", "hooks")
#: The kinds whose files are synced into consumer repos, where their links must resolve
#: (a hook's body renders as advisory text, SPEC §6.6.7).
_SYNCED_KIND_DIRS = ("rules", "prompts", "skills", "hooks")
#: What the link gate reads (``validation/link_check.py``): rendering drops the ``.j2``.
_MARKDOWN_SUFFIXES = (".md", ".md.j2")
_SRC_PACKAGE = REPO_ROOT / "src" / "coding_agent_playbook"
_CONTENT_FILE_PATTERNS = ("*.md", "*.md.j2", "task.toml", "SKILL.md*")


# --- tracked files vs .gitignore ----------------------------------------------


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(not (REPO_ROOT / ".git").exists(), reason="not a git checkout")
def test_no_tracked_file_matches_gitignore() -> None:
    """Releases build from the sdist, but git and pre-commit installs build from the tree.

    ``.git`` is a file in a linked worktree, hence ``exists()`` rather than
    ``is_dir()``.
    """
    # The developer's global excludes file is not the repository's .gitignore
    # and hatch never reads it, so it is neutralized: a personal ignore list
    # must not fail this guard locally. CI has none, so it behaves the same.
    result = subprocess.run(
        ["git", "-c", f"core.excludesFile={os.devnull}", "ls-files", "-ci", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, f"git ls-files failed: {result.stderr}"
    ignored = result.stdout.splitlines()
    assert not ignored, (
        f"tracked files match .gitignore: {ignored}; "
        "add a '!' negation to .gitignore instead of 'git add -f'"
    )


# --- bundled plugin directories -----------------------------------------------


def _leaf_rule_problems(plugin_dir: Path) -> list[str]:
    """Why ``plugin_dir`` is not a valid bundled plugin; empty when it is."""
    name = plugin_dir.name
    problems = []
    if not name.isidentifier():
        problems.append(f"{name!r} is not an identifier")
    if name.startswith(("_", ".")):
        problems.append(f"{name!r} starts with '_' or '.'")
    if not any((plugin_dir / kind).is_dir() for kind in _KIND_DIRS):
        problems.append(f"{name!r} has none of the kind dirs {_KIND_DIRS}")
    return problems


def test_plugin_dirs_follow_the_leaf_rule() -> None:
    plugin_dirs = bundled_plugin_dirs()
    assert plugin_dirs, f"found no bundled plugin directory under {PLUGINS_ROOT}"
    problems = [problem for path in plugin_dirs for problem in _leaf_rule_problems(path)]
    assert not problems, f"bundled plugin dirs under {PLUGINS_ROOT} break the leaf rule: {problems}"


# --- links to layer-root files ------------------------------------------------


def _layer_roots() -> list[Path]:
    """Where layer-root files sit: the core root and every bundled plugin's root."""
    return [CORE_ROOT, *bundled_plugin_dirs()]


def _synced_markdown_files() -> list[Path]:
    """Every ``.md``/``.md.j2`` file under a synced kind directory of any layer."""
    kind_dirs = [layer / kind for layer in _layer_roots() for kind in _SYNCED_KIND_DIRS]
    candidates = [path for kind_dir in kind_dirs for path in kind_dir.rglob("*")]
    return sorted(
        path for path in candidates if path.name.endswith(_MARKDOWN_SUFFIXES) and path.is_file()
    )


def _relative_link_path(target: str) -> str | None:
    """The relative path ``target`` names; ``None`` for anchors, URLs, absolute or Jinja ones."""
    if "{{" in target or "{%" in target:
        return None
    split = urlsplit(target.strip())
    path = unquote(split.path)
    if split.scheme or not path or path.startswith("/"):
        return None
    return path


def _layer_root_links(markdown: Path, layer_roots: frozenset[Path]) -> list[str]:
    """``markdown``'s links whose target is a file directly under a layer root."""
    hits = []
    for link in extract_markdown_links(markdown.read_text(encoding="utf-8")):
        path = _relative_link_path(link.target)
        if path is None:
            continue
        resolved = (markdown.parent / path).resolve()
        if resolved.parent in layer_roots and resolved.is_file():
            hits.append(f"{markdown.relative_to(REPO_ROOT)}:{link.line}: {link.target}")
    return hits


def test_no_bundled_artifact_links_to_a_layer_root_file() -> None:
    layer_roots = frozenset(root.resolve() for root in _layer_roots())
    artifacts = _synced_markdown_files()
    assert artifacts, "found no bundled markdown artifact to scan"
    hits = [hit for markdown in artifacts for hit in _layer_root_links(markdown, layer_roots)]
    assert not hits, (
        "bundled artifacts link to a layer-root file, which ships in the wheel "
        f"but is never synced into consumer repos: {hits}"
    )


# --- the package holds logic only ---------------------------------------------


def test_src_package_holds_no_content() -> None:
    """Acceptance 2: content lives in ``catalog/``, never in the package.

    The package's only non-Python files, ``templates/precommit/config.yaml.j2``
    (engine wiring) and ``py.typed``, match none of the patterns.
    """
    matches = {path for pattern in _CONTENT_FILE_PATTERNS for path in _SRC_PACKAGE.rglob(pattern)}
    stray = sorted(str(path.relative_to(REPO_ROOT)) for path in matches if path.is_file())
    assert not stray, f"content files inside the package belong under catalog/: {stray}"


# --- the editable checkout's catalog root -------------------------------------


@pytest.mark.skipif(
    (_PACKAGE_DIR / "_catalog").exists(), reason="installed wheel: the catalog ships in the package"
)
def test_editable_checkout_resolves_repo_catalog() -> None:
    assert catalog_root() == CATALOG_ROOT
