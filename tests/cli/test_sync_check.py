"""``playbook sync --check`` reports orphans (specs/prK-lifecycle-hooks.md §P P2).

An orphan is generated output a real ``playbook sync`` would delete: a
sentinel-tagged file the adapters' ``cleanup_stale`` removes, or a lockfile
entry the leftover policy deletes (pristine, untracked, in a declared output
location) — the only record for files without a sentinel, such as copied skill
scripts. Either makes ``--check`` exit 1 with the hint "run 'playbook sync' to
remove", and that hint is always true: the next sync deletes it and the check
passes. Leftovers the policy keeps (edited, tracked) are owned by design and
are not drift (``test_sync_orphans.py``).

The check renders into an *empty* scratch directory and reads every input in
place, so nothing from the working tree — VCS, environments, secrets, links
leaving the repo — is ever copied (P2(b)); a skill's secret files and links
leaving its source dir are never copied into any tree, and the orphan scan
never opens a secret path or follows a file symlink.
"""

from __future__ import annotations

import io
import shutil
import socket
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.commands import _sync_output
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.lockfile.model import LockEntry, compute_hash
from coding_agent_playbook.security.files import is_secret_file
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.detector.facts import Facts

    SyntheticRepoFactory = Callable[..., Path]

_ORPHAN_HINT = "    Orphaned generated file; run 'playbook sync' to remove."
_CLAUDE_ONLY_CONFIG = _DEFAULT_CONFIG.replace(
    'adapters_enabled = ["continue", "claude_code", "opencode"]',
    'adapters_enabled = ["claude_code"]',
)
_CONTINUE_ONLY_CONFIG = _DEFAULT_CONFIG.replace(
    'adapters_enabled = ["continue", "claude_code", "opencode"]',
    'adapters_enabled = ["continue"]',
)
_HARNESS_CONFIG = _DEFAULT_CONFIG.replace(
    'adapters_enabled = ["continue", "claude_code", "opencode"]',
    'adapters_enabled = ["continue", "claude_code", "agent_harness"]',
)
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def _orphan_line(rel: str) -> str:
    return f"  {rel}\n{_ORPHAN_HINT}"


def _sync_repo(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0


def _check(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """Run ``playbook sync --check`` on ``repo``; return (exit code, stdout)."""
    capsys.readouterr()
    rc = _sync.execute(repo, check=True, git=FakeGitClient())
    return rc, capsys.readouterr().out


def _write_skill(repo: Path, skill_id: str, scripts: tuple[str, ...] = ("run.sh",)) -> Path:
    skill_dir = repo / "playbook" / "skills" / skill_id
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: Skill\ndescription: Do it.\n---\nRun it.\n",
        encoding="utf-8",
    )
    for name in scripts:
        (skill_dir / "scripts" / name).write_text(f"echo {name}\n", encoding="utf-8")
    return skill_dir


def _write_gated_rule(repo: Path, rule_id: str, applies_if: str) -> None:
    """Write a repo-local rule whose frontmatter carries ``applies_if`` (YAML text)."""
    target = repo / "playbook" / "rules" / f"{rule_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nid: {rule_id}\nname: Gated\ndescription: d\nscope: always\npriority: 50\n"
        f"applies_if:\n  {applies_if}\n---\nGated body for {rule_id}.\n",
        encoding="utf-8",
    )


def _spy_scratch_trees(monkeypatch: pytest.MonkeyPatch) -> list[set[str]]:
    """Record every scratch tree ``--check`` renders (relative paths, files and links)."""
    trees: list[set[str]] = []
    real_file_drift = _sync_output.file_drift

    def spy(written: list[Path], scratch: Path, repo_root: Path, **options: Any) -> list[str]:
        trees.append(
            {p.relative_to(scratch).as_posix() for p in scratch.rglob("*") if not p.is_dir()}
        )
        return real_file_drift(written, scratch, repo_root, **options)

    monkeypatch.setattr(_sync_output, "file_drift", spy)
    return trees


# --- orphans ------------------------------------------------------------------


def test_check_reports_orphaned_generated_file(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A deleted rule's generated file is reported (once) as an orphan."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    _sync_repo(repo)
    (repo / "playbook" / "rules" / "x.md").unlink()
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(".continue/rules/50-x.md") in out
    # Found by both the sentinel scan and the lockfile; reported once.
    assert out.count(".continue/rules/50-x.md") == 1
    assert (repo / ".continue" / "rules" / "50-x.md").is_file()  # real tree untouched


def test_check_fails_on_sentinel_orphan_alone(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale sentinel-tagged output is drift even when nothing else differs."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    _sync_repo(repo)
    stale = repo / ".continue" / "rules" / "99-stale.md"
    stale.write_text(f"{sentinel_line('html')}\nstale\n", encoding="utf-8")
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert out.startswith("Drift detected:\n")
    assert _orphan_line(".continue/rules/99-stale.md") in out
    assert "Generated content differs" not in out
    assert stale.is_file()


def test_check_reports_lockfile_orphan_without_sentinel(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A removed skill's outputs are orphans via the lockfile (no sentinel scan
    ever looks inside a skill dir)."""
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "query-db")
    _sync_repo(repo)
    shutil.rmtree(repo / "playbook" / "skills" / "query-db")
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(".claude/skills/query-db/scripts/run.sh") in out
    assert _orphan_line(".claude/skills/query-db/SKILL.md") in out


def test_sync_removes_lockfile_orphan_reported_by_check(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the hint was false — write mode never deleted sentinel-less
    orphans and silently dropped them from the lockfile, so the next ``--check``
    passed with the files still on disk. Now sync does what the hint says."""
    repo = make_synthetic_repo(tmp_path)
    _write_skill(repo, "query-db")
    _sync_repo(repo)
    shutil.rmtree(repo / "playbook" / "skills" / "query-db")
    assert _check(repo, capsys)[0] == 1
    _sync_repo(repo)
    for rel in ("SKILL.md", "scripts/run.sh"):
        assert not (repo / ".claude" / "skills" / "query-db" / rel).exists(), rel
    rc, out = _check(repo, capsys)
    assert rc == 0, out


def test_check_reports_lockfile_orphan_for_script_removed_from_live_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: a script dropped from a skill that still exists was never an
    orphan (the old copy recorded every file under the skill dir as written)."""
    repo = make_synthetic_repo(tmp_path, config_text=_CLAUDE_ONLY_CONFIG)
    skill_dir = _write_skill(repo, "query-db", ("run.sh", "old.sh"))
    _sync_repo(repo)
    (skill_dir / "scripts" / "old.sh").unlink()
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(".claude/skills/query-db/scripts/old.sh") in out
    assert ".claude/skills/query-db/scripts/run.sh" not in out
    _sync_repo(repo)
    assert not (repo / ".claude" / "skills" / "query-db" / "scripts" / "old.sh").exists()
    assert _check(repo, capsys)[0] == 0


def test_check_lockfile_orphan_needs_pristine_whole_file_in_an_output_location(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only an entry sync would delete is reported: unscoped, inside a declared
    output location, its file still there with the recorded bytes."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir, rules=[("x", "Body of x\n")])
    _sync_repo(repo)
    skill_dir = repo / ".claude" / "skills" / "old"
    skill_dir.mkdir(parents=True)
    content = b"generated once\n"
    for rel in ("pristine.txt", "edited.txt", "scoped.json"):
        (skill_dir / rel).write_bytes(content)
    (repo / "outside-locations.txt").write_bytes(content)
    (tmp_path / "outside.txt").write_bytes(content)
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    sha, size = compute_hash(content), len(content)
    lockfile.entries += [
        LockEntry(path=".claude/skills/old/pristine.txt", sha256=sha, bytes=size, kind="skill"),
        LockEntry(path=".claude/skills/old/edited.txt", sha256="0", bytes=1, kind="skill"),
        LockEntry(path=".claude/skills/old/gone.txt", sha256=sha, bytes=size, kind="skill"),
        LockEntry(
            path=".claude/skills/old/scoped.json",
            sha256=sha,
            bytes=size,
            kind="runtime",
            scope="json:/x",
        ),
        LockEntry(path="outside-locations.txt", sha256=sha, bytes=size),
        LockEntry(path="../outside.txt", sha256=sha, bytes=size),
    ]
    state.save_lockfile(lockfile)
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert out.count("Orphaned generated file") == 1
    assert _orphan_line(".claude/skills/old/pristine.txt") in out


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        pytest.param("<<<<<<< HEAD\n", "TOMLDecodeError", id="conflict-markers"),
        pytest.param(
            'schema_version = 2\nengine_version = "x"\nrendered_at = "t"\nentries = "oops"\n',
            "entries: expected list, got str 'oops'",
            id="entries-not-a-list",
        ),
        pytest.param(
            'schema_version = 2\nengine_version = "x"\nrendered_at = "t"\n\n'
            '[[entries]]\npath = 3\nsha256 = "a"\nbytes = 1\n',
            "entries[0].path: expected str, got int 3",
            id="path-not-a-string",
        ),
    ],
)
def test_check_reports_unreadable_lockfile(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    content: str,
    detail: str,
) -> None:
    """A conflicted or mis-shaped lockfile is one drift line, never a traceback."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    _sync_repo(repo)
    (repo / ".coding-agent-playbook.lock").write_text(content, encoding="utf-8")
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert "  .coding-agent-playbook.lock\n    Unreadable lockfile (" in out
    assert detail in out


# --- orphans for outputs whose names look like caches or secrets --------------


def test_check_reports_orphan_for_secret_named_artifact(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the scratch copy excluded ``*credentials*`` paths, so a deleted
    ``rotate-credentials`` prompt's outputs were never reported."""
    repo = make_synthetic_repo(
        tmp_path, prompts=[("rotate-credentials", {"body": "Rotate the keys.\n"})]
    )
    _sync_repo(repo)
    (repo / "playbook" / "prompts" / "rotate-credentials.md").unlink()
    rc, out = _check(repo, capsys)
    assert rc == 1
    for rel in (
        ".claude/commands/rotate-credentials.md",
        ".continue/prompts/rotate-credentials.md",
        ".opencode/command/rotate-credentials.md",
    ):
        assert _orphan_line(rel) in out, rel


@pytest.mark.parametrize("skill_id", ["build", "dist", "aws-credentials"])
def test_check_reports_orphan_under_build_named_skill(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    skill_id: str,
) -> None:
    """Regression: skills named like a build dir or a secret were invisible to the
    orphan check (their outputs never reached the scratch copy)."""
    repo = make_synthetic_repo(tmp_path, config_text=_CLAUDE_ONLY_CONFIG)
    _write_skill(repo, skill_id)
    _sync_repo(repo)
    shutil.rmtree(repo / "playbook" / "skills" / skill_id)
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(f".claude/skills/{skill_id}/SKILL.md") in out
    assert _orphan_line(f".claude/skills/{skill_id}/scripts/run.sh") in out


def test_check_renders_build_and_credentials_named_artifacts(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """``playbook/`` is read in place: a ``build`` skill or a ``*credentials*`` rule
    renders in ``--check`` exactly as in write mode (no false drift)."""
    repo = make_synthetic_repo(tmp_path, rules=[("handling-credentials", "Rotate keys.\n")])
    _write_skill(repo, "build")
    _sync_repo(repo)
    rc, out = _check(repo, capsys)
    assert rc == 0, out


# --- symlinks -----------------------------------------------------------------


@posix_only
def test_check_symlinked_output_dir_has_no_false_lockfile_orphans(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: with ``.claude/commands`` an in-repo symlink, the lockfile holds
    resolved paths, and the scratch paths were never mapped back through the link,
    so every command was a false orphan that no sync could clear."""
    repo = make_synthetic_repo(tmp_path, prompts=[("mycmd", {"body": "Do it.\n"})])
    (repo / "tools" / "claude-commands").mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "commands").symlink_to("../tools/claude-commands", target_is_directory=True)
    _sync_repo(repo)
    assert (repo / "tools" / "claude-commands" / "mycmd.md").is_file()
    for _ in range(2):
        rc, out = _check(repo, capsys)
        assert rc == 0, out
        _sync_repo(repo)


@posix_only
def test_check_follows_canonical_symlink_outside_repo(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the scratch copy skipped links leaving the repo even under
    ``playbook/``, so a shared rule kept outside the repo vanished from the check
    render (false drift + a false orphan right after a clean sync)."""
    shared = tmp_path / "shared" / "org-style.md"
    shared.parent.mkdir()
    shared.write_text(
        "---\nid: org-style\nname: Org\ndescription: d\nscope: always\npriority: 50\n---\n"
        "Org body.\n",
        encoding="utf-8",
    )
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir)
    (repo / "playbook" / "rules").mkdir(parents=True)
    (repo / "playbook" / "rules" / "org-style.md").symlink_to(shared)
    _sync_repo(repo)
    assert (repo / ".continue" / "rules" / "50-org-style.md").is_file()
    rc, out = _check(repo, capsys)
    assert rc == 0, out


@posix_only
def test_check_never_copies_the_working_tree(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2(b): VCS, envs, caches, build outputs, secrets and links leaving the repo
    never reach the scratch tree — it holds generated output only."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_rsa").write_text("PRIVATE\n", encoding="utf-8")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir, rules=[("x", "Body of x\n")])
    for rel in (".venv/lib/site.py", ".git/HEAD", "node_modules/pkg/index.js", "dist/p.whl"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n", encoding="utf-8")
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / "ssh").symlink_to(home / ".ssh", target_is_directory=True)
    (repo / "loop").symlink_to(repo, target_is_directory=True)
    _sync_repo(repo)
    trees = _spy_scratch_trees(monkeypatch)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    [tree] = trees
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    assert tree == {entry.path for entry in lockfile.entries}


@posix_only
def test_check_survives_symlink_cycles_and_sockets(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: two directory links pointing at each other recursed until
    ENAMETOOLONG and a UNIX socket raised ``shutil.Error`` in the scratch copy."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    (repo / "a").mkdir()
    (repo / "b").mkdir()
    (repo / "a" / "to_b").symlink_to("../b", target_is_directory=True)
    (repo / "b" / "to_a").symlink_to("../a", target_is_directory=True)
    (repo / "run").mkdir()
    # Bind by a relative path: AF_UNIX caps the path length (~104 bytes) and
    # pytest's tmp_path is often longer.
    monkeypatch.chdir(repo)
    with socket.socket(socket.AF_UNIX) as sock:
        sock.bind("run/a.sock")
        assert (repo / "run" / "a.sock").is_socket()
        _sync_repo(repo)
        rc, out = _check(repo, capsys)
    assert rc == 0, out


# --- inputs come from the real repo -------------------------------------------


def test_check_facts_come_from_the_real_repo(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Facts are detected once, on the real repo: a notebook under ``build/``
    keeps ``has_notebooks`` true, so the check renders the gated rule."""
    repo = make_synthetic_repo(tmp_path)
    (repo / "build").mkdir()
    (repo / "build" / "analysis.ipynb").write_text("{}\n", encoding="utf-8")
    _write_gated_rule(repo, "notebook-hygiene", "has_notebooks: true")
    _sync_repo(repo)
    assert (repo / ".continue" / "rules" / "50-notebook-hygiene.md").is_file()
    detected: list[Path] = []

    def spy_detect(root: Path) -> Facts:
        detected.append(root)
        return detect(root)

    monkeypatch.setattr("coding_agent_playbook.validation.context.detect", spy_detect)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    assert detected == [repo]


def test_check_has_file_predicate_sees_real_repo(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """``applies_if: has_file`` is evaluated against the real repo, so a secret
    path (``.env``) still flips the rendered rule set exactly as in write mode."""
    repo = make_synthetic_repo(tmp_path)
    (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    _write_gated_rule(repo, "dotenv-hygiene", 'has_file: [".env"]')
    _sync_repo(repo)
    assert (repo / ".continue" / "rules" / "50-dotenv-hygiene.md").is_file()
    rc, out = _check(repo, capsys)
    assert rc == 0, out


# --- aliased and out-of-repo output dirs --------------------------------------


@posix_only
def test_sync_survives_aliased_continue_output_dirs(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: with ``.continue/prompts -> rules`` a removed rule's output was
    listed twice and the second unlink crashed ``playbook sync`` with
    FileNotFoundError before the lockfile and the managed block were saved."""
    repo = make_synthetic_repo(
        tmp_path, config_text=_CONTINUE_ONLY_CONFIG, rules=[("x", "Body of x\n")]
    )
    (repo / ".continue" / "rules").mkdir(parents=True)
    (repo / ".continue" / "prompts").symlink_to("rules", target_is_directory=True)
    _sync_repo(repo)
    (repo / "playbook" / "rules" / "x.md").unlink()
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert out.count("50-x.md") == 1
    _sync_repo(repo)
    assert not (repo / ".continue" / "rules" / "50-x.md").exists()
    rc, out = _check(repo, capsys)
    assert rc == 0, out


@posix_only
def test_check_reports_orphan_in_output_dir_symlinked_outside_repo(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the orphan list dropped every path resolving outside the repo,
    so with ``.claude/commands -> ../shared-commands`` the check passed while the
    next sync deleted ``shared-commands/px.md``."""
    shared = tmp_path / "shared-commands"
    shared.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(
        repo_dir, config_text=_CLAUDE_ONLY_CONFIG, prompts=[("px", {"body": "Do it.\n"})]
    )
    (repo / ".claude").mkdir()
    (repo / ".claude" / "commands").symlink_to("../../shared-commands", target_is_directory=True)
    _sync_repo(repo)
    assert (shared / "px.md").is_file()
    (repo / "playbook" / "prompts" / "px.md").unlink()
    rc, out = _check(repo, capsys)
    assert rc == 1
    assert _orphan_line(".claude/commands/px.md") in out
    _sync_repo(repo)
    assert not (shared / "px.md").exists()


# --- adapters on the pre-v0.16 cleanup contract -------------------------------


def _never_delete(self: ContinueAdapter, written_paths: set[Path], repo_root: Path) -> list[Path]:
    """A conservative legacy ``cleanup_stale`` override that never deletes."""
    return []


def test_check_skips_orphans_of_adapter_overriding_only_cleanup_stale(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: an adapter overriding ``cleanup_stale`` (as SPEC §10.1 used to
    say) but not ``stale_outputs`` got the default sentinel scan in ``--check``:
    an orphan its cleanup never deletes was reported after every sync, forever."""
    monkeypatch.setattr(ContinueAdapter, "cleanup_stale", _never_delete)
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    _sync_repo(repo)
    (repo / "playbook" / "rules" / "x.md").unlink()
    stale = repo / ".continue" / "rules" / "50-x.md"
    stale.write_text(stale.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
    for _ in range(2):
        _sync_repo(repo)
        assert stale.is_file()  # the legacy cleanup never deletes it
        rc, out = _check(repo, capsys)
        assert rc == 0, out


def test_check_warns_about_adapter_overriding_only_cleanup_stale(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ContinueAdapter, "cleanup_stale", _never_delete)
    repo = make_synthetic_repo(tmp_path)
    _sync_repo(repo)
    capsys.readouterr()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    err = capsys.readouterr().err
    assert "adapter 'continue' overrides cleanup_stale() but not stale_outputs()" in err


# --- secrets are never read or published --------------------------------------


def _record_opens(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every path opened through ``open``/``Path.open`` (read or write)."""
    opened: list[Path] = []
    real_open = io.open

    def spy(file: object, *args: object, **kwargs: object) -> object:
        if isinstance(file, str | Path):
            opened.append(Path(file))
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(io, "open", spy)
    monkeypatch.setattr("builtins.open", spy)
    return opened


@posix_only
def test_check_never_opens_a_secret_path(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the orphan scan read every file under the scanned dirs in full,
    so the pre-commit ``--check`` read ``rules/prod.tfvars``, ``.continue/rules/.env``,
    ``.claude/commands/id_ed25519`` and ``references/aws-notes.md -> ~/.aws/credentials``."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    credentials = home / ".aws" / "credentials"
    credentials.parent.mkdir(parents=True)
    credentials.write_text("[default]\nkey = AKIA\n", encoding="utf-8")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir, config_text=_HARNESS_CONFIG, rules=[("x", "Body\n")])
    _sync_repo(repo)
    for rel in ("rules/prod.tfvars", ".continue/rules/.env", ".claude/commands/id_ed25519"):
        (repo / rel).write_text("TOKEN=secret\n", encoding="utf-8")
    (repo / "references").mkdir(exist_ok=True)
    (repo / "references" / "aws-notes.md").symlink_to(credentials)
    opened = _record_opens(monkeypatch)
    rc, out = _check(repo, capsys)
    monkeypatch.undo()
    assert rc == 0, out
    secret_reads = [
        path for path in opened if is_secret_file(path, relative_to=repo, home=str(home))
    ]
    assert secret_reads == []


def _write_skill_with_secrets(repo: Path, home: Path, outside: Path) -> Path:
    """A skill whose ``scripts/`` holds a ``.env``, links out of the skill, and an
    in-skill link (the only link that may be copied)."""
    skill_dir = _write_skill(repo, "demo")
    scripts = skill_dir / "scripts"
    (scripts / ".env").write_text("DB_PASSWORD=hunter2\n", encoding="utf-8")
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "config").write_text("Host *\n", encoding="utf-8")
    (scripts / "ssh-notes.txt").symlink_to(home / ".ssh" / "config")
    outside.mkdir(parents=True)
    (outside / "helper.sh").write_text("echo outside\n", encoding="utf-8")
    (scripts / "helper.sh").symlink_to(outside / "helper.sh")
    (scripts / "alias.sh").symlink_to("run.sh")
    return skill_dir


_REFUSED_SCRIPTS = (".env", "ssh-notes.txt", "helper.sh")


@posix_only
def test_skill_secrets_and_escaping_links_are_never_copied(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a skill's ``scripts/.env`` and ``scripts/notes.txt -> ~/.ssh/...``
    were copied into ``.claude/skills/``, ``shared_skills/`` and the ``--check``
    scratch tree, and hashed into the lockfile, under innocent names."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = make_synthetic_repo(repo_dir, config_text=_CLAUDE_ONLY_CONFIG)
    _write_skill_with_secrets(repo, home, tmp_path / "outside")
    _sync_repo(repo)
    err = capsys.readouterr().err
    copied = repo / ".claude" / "skills" / "demo" / "scripts"
    assert sorted(p.name for p in copied.iterdir()) == ["alias.sh", "run.sh"]
    for name in _REFUSED_SCRIPTS:
        assert f"scripts/{name} into" in err, name
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    listed = {entry.path for entry in lockfile.entries}
    assert not any(path.endswith(_REFUSED_SCRIPTS) for path in listed), listed
    trees = _spy_scratch_trees(monkeypatch)
    rc, out = _check(repo, capsys)
    assert rc == 0, out
    [tree] = trees
    assert not any(path.endswith(_REFUSED_SCRIPTS) for path in tree), tree
