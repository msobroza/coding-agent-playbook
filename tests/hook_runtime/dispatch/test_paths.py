"""Path normalization, globs and git-free repo discovery (specs/prK-lifecycle-hooks.md §D.2.4).

Every function under test is pure over its arguments: ``platform`` and ``home``
are injected, so the darwin and win32 rows run on any host. Only the
``real_git`` rows spawn git, to prove ``find_repo`` agrees with
``git rev-parse``. Paths are built under ``realpath(tmp_path)`` so that a
symlinked temp root (``/var`` -> ``/private/var`` on macOS) never reads as a
symlink in the path under test.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.path_globs import compile_globs, fold_key, glob_to_regex
from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo
from coding_agent_playbook.hook_runtime.dispatch.paths import (
    NormalizedPath,
    find_repo,
    normalize_path,
)
from coding_agent_playbook.security.trust import git_common_dir
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from collections.abc import Callable


def _real(path: Path) -> str:
    return os.path.realpath(path)


def _repo(root: str) -> RepoInfo:
    git_dir = f"{root}/.git"
    return RepoInfo(
        worktree_root=root, git_dir=git_dir, common_dir=git_dir, is_linked_worktree=False
    )


def _norm(
    raw: str, root: str, *, platform: str = "linux", home: str | None = None
) -> NormalizedPath:
    return normalize_path(raw, base=root, repo=_repo(root), home=home, platform=platform)


def _linked_layout(tmp_path: Path, *, feat: Path | None = None) -> tuple[str, str]:
    """A main checkout plus one linked worktree, laid out the way git writes them."""
    root = Path(_real(tmp_path))
    main = root / "main"
    feat = feat or root / "feat"
    admin = main / ".git" / "worktrees" / "feat"
    admin.mkdir(parents=True)
    feat.mkdir(parents=True)
    (admin / "gitdir").write_text(f"{feat}/.git\n", encoding="utf-8")
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    (feat / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return str(main), str(feat)


# --- normalize_path: the §D.9 red-team rows ------------------------------------------


def test_darwin_casefold_makes_dotENV_match_dotenv_glob(tmp_path: Path) -> None:
    root = _real(tmp_path)

    darwin = _norm(".ENV", root, platform="darwin")
    linux = _norm(".ENV", root, platform="linux")

    assert (darwin.repo_rel, darwin.key) == (".ENV", ".env")
    assert compile_globs([".env*"], platform="darwin").matches(darwin.key)
    assert not compile_globs([".env*"], platform="linux").matches(linux.key)


def test_win32_drive_backslash_path_maps_to_claude_settings_repo_rel() -> None:
    repo = _repo("C:/proj")

    absolute = normalize_path(
        "C:\\proj\\.CLAUDE\\settings.json", base="C:/proj", repo=repo, home=None, platform="win32"
    )
    relative = normalize_path(
        ".CLAUDE\\settings.json", base="C:/proj", repo=repo, home=None, platform="win32"
    )

    assert absolute.repo_rel == ".CLAUDE/settings.json"
    assert absolute.key == ".claude/settings.json"
    assert absolute.outside_repo is False
    assert relative.key == ".claude/settings.json"


def test_win32_root_comparison_ignores_case() -> None:
    path = normalize_path(
        "c:\\PROJ\\src\\App.py", base="C:/proj", repo=_repo("C:/Proj"), home=None, platform="win32"
    )

    assert (path.repo_rel, path.key) == ("src/App.py", "src/app.py")


def test_symlink_into_git_dir_sets_is_symlink_and_resolves(tmp_path: Path) -> None:
    root = _real(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / "cfg").symlink_to(".git/config")

    path = _norm("cfg", root)

    assert path.is_symlink is True
    assert path.path == f"{root}/cfg"
    assert path.realpath == f"{root}/.git/config"
    assert (path.repo_rel, path.key, path.exists) == (".git/config", ".git/config", True)


def test_sibling_linked_worktree_path_is_same_repo(tmp_path: Path) -> None:
    main, feat = _linked_layout(tmp_path)
    repo = find_repo(feat)
    assert repo is not None

    path = normalize_path(f"{main}/src/app.py", base=feat, repo=repo, home=None, platform="linux")

    assert path.repo_rel == "src/app.py"
    assert path.worktree_root == main
    assert (path.same_repo, path.sibling_worktree, path.outside_repo) == (True, True, False)


def test_own_worktree_path_is_same_repo_but_not_sibling(tmp_path: Path) -> None:
    _main, feat = _linked_layout(tmp_path)
    repo = find_repo(feat)
    assert repo is not None

    path = normalize_path("src/app.py", base=feat, repo=repo, home=None, platform="linux")

    assert (path.repo_rel, path.worktree_root) == ("src/app.py", feat)
    assert (path.same_repo, path.sibling_worktree) == (True, False)


def test_nested_linked_worktree_wins_over_its_enclosing_checkout(tmp_path: Path) -> None:
    nested = Path(_real(tmp_path)) / "main" / ".claude" / "worktrees" / "feat"
    main, feat = _linked_layout(tmp_path, feat=nested)
    repo = find_repo(main)
    assert repo is not None

    path = normalize_path(f"{feat}/a.py", base=main, repo=repo, home=None, platform="linux")

    assert (path.worktree_root, path.repo_rel, path.sibling_worktree) == (feat, "a.py", True)


def test_hard_link_reports_nlink_2(tmp_path: Path) -> None:
    root = _real(tmp_path)
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    os.link(tmp_path / "a.txt", tmp_path / "b.txt")

    path = _norm("b.txt", root)

    assert (path.exists, path.nlink, path.is_symlink) == (True, 2, False)


def test_outside_repo_has_no_repo_rel(tmp_path: Path) -> None:
    root = Path(_real(tmp_path))
    (root / "repo").mkdir()
    outside = root / "elsewhere" / "notes.txt"

    path = _norm(str(outside), str(root / "repo"))
    without_repo = normalize_path("x", base=str(root), repo=None, home=None, platform="linux")

    assert (path.repo_rel, path.worktree_root) == (None, None)
    assert (path.outside_repo, path.same_repo) == (True, False)
    assert path.key == str(outside)
    assert (path.exists, path.nlink) == (False, 0)
    assert without_repo.outside_repo is True


# --- normalize_path: the other steps --------------------------------------------------


def test_home_is_expanded_only_when_injected(tmp_path: Path) -> None:
    root = _real(tmp_path)

    expanded = _norm("~/.ssh/id_rsa", root, home="/home/dev")
    literal = _norm("~/.ssh/id_rsa", root)
    bare = _norm("~", root, home="/home/dev")

    assert expanded.path == "/home/dev/.ssh/id_rsa"
    assert literal.path == f"{root}/~/.ssh/id_rsa"
    assert bare.path == "/home/dev"


def test_relative_path_joins_base_and_resolves_dotdot(tmp_path: Path) -> None:
    root = _real(tmp_path)

    path = _norm("missing/../src/a.py", root)

    assert (path.path, path.realpath) == (f"{root}/src/a.py", f"{root}/src/a.py")
    assert (path.repo_rel, path.is_symlink, path.raw) == ("src/a.py", False, "missing/../src/a.py")


def test_the_worktree_root_itself_is_dot(tmp_path: Path) -> None:
    root = _real(tmp_path)

    assert _norm(".", root).repo_rel == "."


def test_fold_key_applies_nfc_and_casefold_only_on_folding_platforms() -> None:
    decomposed = "Cafe\u0301/README"

    assert fold_key(decomposed, "darwin") == "caf\u00e9/readme"
    assert fold_key(decomposed, "win32") == "caf\u00e9/readme"
    assert fold_key(decomposed, "linux") == decomposed


# --- globs ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "key", "expected"),
    [
        ("docs/**", "docs/a/b.md", True),
        ("docs/**", "docs", False),
        ("**/secrets/*", "a/b/secrets/x", True),
        ("**/secrets/*", "secrets/x", True),
        ("a/**/b", "a/b", True),
        ("a/**/b", "a/x/y/b", True),
        ("src/*.py", "src/a.py", True),
        ("src/*.py", "src/sub/a.py", False),
        ("src/?.py", "src/a.py", True),
        ("src/?.py", "src/ab.py", False),
        ("a?b", "a/b", False),
        (".env*", "deploy/.env.prod", True),
        (".env*", ".env", True),
        ("*.pem", "a/b/key.pem", True),
        ("key.pem", "key.pem.bak", False),
        ("src/a.py", "x/src/a.py", False),
        ("[abc].txt", "b.txt", True),
        ("[!abc].txt", "b.txt", False),
        ("[!abc].txt", "d.txt", True),
        ("[]x].txt", "].txt", True),
        ("[unclosed", "[unclosed", True),
        ("secrets/", "secrets/x/y", True),
        ("/etc/**", "/etc/passwd", True),
        ("a.b", "aXb", False),
    ],
)
def test_glob_semantics(pattern: str, key: str, expected: bool) -> None:
    globs = compile_globs([pattern], platform="linux")

    assert globs.matches(key) is expected
    assert globs.matching(key) == ((pattern,) if expected else ())


def test_glob_to_regex_is_a_fullmatch_body() -> None:
    assert glob_to_regex("src/*.py") == "src/[^/]*\\.py"


def test_home_globs_expand_only_when_home_is_injected() -> None:
    with_home = compile_globs(["~/.ssh/**"], platform="linux", home="/home/dev")
    without_home = compile_globs(["~/.ssh/**"], platform="linux")

    assert with_home.matches("/home/dev/.ssh/id_rsa")
    assert not without_home.matches("/home/dev/.ssh/id_rsa")


def test_patterns_are_folded_like_keys_on_folding_platforms() -> None:
    globs = compile_globs([".CLAUDE/Settings.json"], platform="darwin")

    assert globs.matches(fold_key(".claude/settings.JSON", "darwin"))
    assert globs.patterns == (".CLAUDE/Settings.json",)


# --- find_repo ------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["main", "linked_worktree"])
def test_find_repo_matches_git_rev_parse(
    which: str, tmp_path: Path, real_git: Callable[..., str]
) -> None:
    main = tmp_path / "main"
    main.mkdir()
    real_git("init", "-q", cwd=main)
    real_git("commit", "-q", "--allow-empty", "-m", "init", cwd=main)
    real_git("worktree", "add", "-q", str(tmp_path / "feat"), cwd=main)
    top = main if which == "main" else tmp_path / "feat"
    start = top / "pkg"
    start.mkdir()
    lines = real_git(
        "rev-parse",
        "--path-format=absolute",
        "--git-dir",
        "--git-common-dir",
        "--show-toplevel",
        cwd=start,
    ).splitlines()
    git_dir, common_dir, toplevel = (os.path.realpath(line) for line in lines)

    info = find_repo(str(start))

    assert info is not None
    assert (info.git_dir, info.common_dir, info.worktree_root) == (git_dir, common_dir, toplevel)
    assert info.is_linked_worktree is (which == "linked_worktree")
    other = tmp_path / ("feat" if which == "main" else "main")
    assert info.sibling_roots == (_real(other),)


def test_find_repo_outside_git_returns_none(tmp_path: Path) -> None:
    assert find_repo(str(tmp_path)) is None


def test_find_repo_in_a_plain_checkout_has_no_siblings(tmp_path: Path) -> None:
    root = _real(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()

    assert find_repo(f"{root}/src") == _repo(root)


def test_find_repo_reads_gitdir_files_and_commondir(tmp_path: Path) -> None:
    main, feat = _linked_layout(tmp_path)
    (Path(feat) / "sub").mkdir()

    info = find_repo(f"{feat}/sub")

    assert info == RepoInfo(
        worktree_root=feat,
        git_dir=f"{main}/.git/worktrees/feat",
        common_dir=f"{main}/.git",
        is_linked_worktree=True,
        sibling_roots=(main,),
    )
    assert info.common_dir == str(git_common_dir(Path(feat)))


def test_find_repo_resolves_a_relative_gitdir(tmp_path: Path) -> None:
    main, feat = _linked_layout(tmp_path)
    (Path(feat) / ".git").write_text("gitdir: ../main/.git/worktrees/feat\n", encoding="utf-8")

    info = find_repo(feat)

    assert info is not None
    assert info.git_dir == f"{main}/.git/worktrees/feat"


def test_find_repo_with_a_malformed_gitfile_is_none(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("not a gitdir line\n", encoding="utf-8")

    assert find_repo(str(tmp_path)) is None


def test_find_repo_skips_unreadable_worktree_admin_entries(tmp_path: Path) -> None:
    main, _feat = _linked_layout(tmp_path)
    (Path(main) / ".git" / "worktrees" / "stale").mkdir()

    info = find_repo(main)

    assert info is not None
    assert info.sibling_roots == (str(Path(_real(tmp_path)) / "feat"),)


# --- import-light ---------------------------------------------------------------------


def test_event_paths_and_globs_import_only_the_stdlib_and_the_runtime() -> None:
    loaded = new_modules_after("import coding_agent_playbook.hook_runtime.dispatch.paths")

    engine = {name for name in loaded if name.startswith("coding_agent_playbook")}
    assert engine == {
        "coding_agent_playbook.hook_runtime",
        "coding_agent_playbook.hook_runtime.dispatch",
        "coding_agent_playbook.hook_runtime.dispatch.event",
        "coding_agent_playbook.artifacts",
        "coding_agent_playbook.artifacts.path_globs",
        "coding_agent_playbook.hook_runtime.dispatch.paths",
    }
    assert not {"unicodedata", "pathlib", "tomllib", "json"} & set(loaded)
