"""``playbook sync`` then ``sync --check`` is clean for every spelling of ``--repo-root`` (#268).

Write mode used the typed path (``Path(".").name == ""`` gave ``name: harness``,
``x/sub/..`` gave ``name: ..``, a symlink its own name) while ``--check`` rendered
into a scratch dir named after the resolved directory, so a fresh sync reported
``HARNESS.md`` drift. The pipeline now resolves the root once
(``generated_output.repo_name.canonical_root``) and both modes take the name from
one helper. Every form must also produce the exact tree a plain ``playbook sync``
writes (the default invocation stays byte-identical).
"""

from __future__ import annotations

import os
import sys
import tomllib
import unicodedata
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.cli import main
from coding_agent_playbook.generated_output.output_io import write_output_text
from coding_agent_playbook.generated_output.repo_name import repo_dir_name
from coding_agent_playbook.sync import _check_modes
from coding_agent_playbook.validation.context import SyncContext
from tests.conftest import _DEFAULT_CONFIG

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule

    SyntheticRepoFactory = Callable[..., Path]

pytestmark = pytest.mark.usefixtures("hermetic_git_env")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")

_ADAPTERS_LINE = 'adapters_enabled = ["continue", "claude_code", "opencode"]'
_HARNESS_ONLY = _DEFAULT_CONFIG.replace(_ADAPTERS_LINE, 'adapters_enabled = ["agent_harness"]')
_LOCKFILE = ".coding-agent-playbook.lock"
_FAKE_OUTPUT = "ROOT-NAME.txt"


@pytest.fixture
def probe(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory) -> Path:
    """An ``agent_harness``-only repo named ``probe``, with ``sub/`` inside and a ``sib/`` beside it."""
    root = tmp_path / "probe"
    (root / "sub").mkdir(parents=True)
    (tmp_path / "sib").mkdir()
    make_synthetic_repo(root, config_text=_HARNESS_ONLY)
    return root.resolve()


def _playbook(*argv: str) -> int:
    """Run ``playbook <argv>`` in-process; return its exit code."""
    return main(list(argv))


def _sync_then_check(sync_form: list[str], check_form: list[str]) -> int:
    assert _playbook("sync", *sync_form) == 0
    return _playbook("sync", "--check", *check_form)


def _harness_name(repo: Path) -> str:
    text = (repo / "HARNESS.md").read_text(encoding="utf-8")
    return next(
        line.removeprefix("name: ") for line in text.splitlines() if line.startswith("name: ")
    )


def _tree(repo: Path) -> dict[str, bytes]:
    """Every file under ``repo`` (``.git`` aside) by relative path; the lockfile minus ``rendered_at``."""
    files = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    }
    lock = tomllib.loads(files.pop(_LOCKFILE).decode())
    lock.pop("rendered_at", None)
    files[_LOCKFILE] = repr(sorted(lock.items())).encode()
    return files


def _default_tree(repo: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """The tree a plain ``playbook sync`` (no flag, cwd = repo) writes."""
    monkeypatch.chdir(repo)
    assert _playbook("sync") == 0
    return _tree(repo)


@pytest.mark.parametrize(
    ("cwd", "form"),
    [
        ("probe", "."),
        ("probe", "./"),
        ("probe", ""),
        ("probe/sub", ".."),
        ("probe", "sub/.."),
        ("sib", "../probe"),
        (".", "probe/"),
    ],
)
def test_relative_forms_round_trip(
    probe: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cwd: str,
    form: str,
) -> None:
    expected = _default_tree(probe, monkeypatch)
    monkeypatch.chdir(probe.parent / cwd)
    capsys.readouterr()

    assert _sync_then_check(["--repo-root", form], ["--repo-root", form]) == 0, capsys.readouterr()
    assert _harness_name(probe) == "probe"
    assert _tree(probe) == expected


def test_absolute_dot_dot_form_round_trips(probe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = _default_tree(probe, monkeypatch)
    typed = str(probe / "sub" / "..")
    assert _sync_then_check(["--repo-root", typed], ["--repo-root", typed]) == 0
    assert _harness_name(probe) == "probe"
    assert _tree(probe) == expected


@pytest.mark.parametrize(
    ("sync_form", "check_form"),
    [(["--repo-root", "."], []), (["--repo-root", "."], ["ABS"]), (["ABS"], ["--repo-root", "."])],
    ids=["dot-then-no-flag", "dot-then-abs", "abs-then-dot"],
)
def test_cross_form_pairs_agree(
    probe: Path, monkeypatch: pytest.MonkeyPatch, sync_form: list[str], check_form: list[str]
) -> None:
    monkeypatch.chdir(probe)

    def _expand(form: list[str]) -> list[str]:
        return ["--repo-root", str(probe)] if form == ["ABS"] else form

    assert _sync_then_check(_expand(sync_form), _expand(check_form)) == 0
    assert _harness_name(probe) == "probe"


@posix_only
def test_symlink_alias_with_another_name_round_trips(
    probe: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = _default_tree(probe, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(probe, target_is_directory=True)
    assert _sync_then_check(["--repo-root", str(alias)], ["--repo-root", str(alias)]) == 0
    assert _harness_name(probe) == "probe"
    assert _tree(probe) == expected


def test_case_variant_root_round_trips(probe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """On a case-insensitive filesystem (macOS APFS default) ``../PROBE`` is ``probe``."""
    if not (probe.parent / "PROBE").exists():
        pytest.skip("case-sensitive filesystem: PROBE is another directory")
    expected = _default_tree(probe, monkeypatch)
    # The check side alone: a clean tree checked through the case variant.
    monkeypatch.chdir(probe.parent / "sib")
    assert _playbook("sync", "--check", "--repo-root", "../PROBE") == 0
    # The sync side: written through the case variant, checked with no flag.
    assert _playbook("sync", "--repo-root", "../PROBE") == 0
    monkeypatch.chdir(probe)
    assert _playbook("sync", "--check") == 0
    assert _harness_name(probe) == "probe"
    assert _tree(probe) == expected


_CAFE_NFC = unicodedata.normalize("NFC", "caf\u00e9")
_CAFE_NFD = unicodedata.normalize("NFD", _CAFE_NFC)


@pytest.mark.parametrize(
    ("on_disk", "typed"),
    [(_CAFE_NFD, _CAFE_NFC), (_CAFE_NFC, _CAFE_NFD)],
    ids=["nfd-dir", "nfc-dir"],
)
def test_normalization_variant_root_round_trips(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    monkeypatch: pytest.MonkeyPatch,
    on_disk: str,
    typed: str,
) -> None:
    """On APFS ``../café`` typed NFC reaches an NFD ``café`` (and back): HARNESS.md names the stored bytes."""
    repo = tmp_path / on_disk
    repo.mkdir()
    (tmp_path / "sib").mkdir()
    if not (tmp_path / typed).exists():
        pytest.skip("normalization-sensitive filesystem: the other spelling is another name")
    make_synthetic_repo(repo, config_text=_HARNESS_ONLY)
    [stored] = (name for name in os.listdir(tmp_path) if name != "sib")
    monkeypatch.chdir(tmp_path / "sib")
    assert _playbook("sync", "--repo-root", f"../{typed}") == 0
    assert _harness_name(repo) == stored
    monkeypatch.chdir(repo)
    assert _playbook("sync", "--check") == 0


def test_init_with_dot_root_is_clean(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "probe"
    root.mkdir()
    make_synthetic_repo(root, write_config=False)
    monkeypatch.chdir(root)
    init = ["init", "--non-interactive", "--name", "demo", "--kind", "python-library"]
    assert _playbook(*init, "--adapters", "agent_harness", "--repo-root", ".") == 0
    assert _harness_name(root) == "probe"
    assert _playbook("sync", "--check", "--repo-root", ".") == 0
    assert _playbook("sync", "--check") == 0


def test_sync_context_root_is_absolute_at_the_pipeline(
    probe: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``execute`` hands every stage the canonical root, whatever the caller passed."""
    seen: list[Path] = []
    real_from_repo = SyncContext.from_repo

    def _spy(repo_root: Path, **kwargs: object) -> SyncContext:
        seen.append(repo_root)
        return real_from_repo(repo_root, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(SyncContext, "from_repo", _spy)
    monkeypatch.chdir(probe / "sub")
    assert _playbook("sync", "--repo-root", "..") == 0
    assert seen
    assert all(root == probe for root in seen), seen


def test_check_scratch_leaf_is_the_repo_dir_name(
    probe: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(probe)
    ctx = SyncContext.from_repo(probe)
    with _check_modes._rendered_scratch(ctx, None) as (scratch, _recorder):
        assert scratch.name == repo_dir_name(Path(".")) == "probe"


# --- an out-of-tree adapter that names a file after its output root ----------


class FakeNameAdapter(Adapter):
    """Writes ``ROOT-NAME.txt`` holding ``output_root.name`` (the H4 extension-point probe)."""

    name = "fakename"
    output_locations: ClassVar[tuple[str, ...]] = (_FAKE_OUTPUT,)

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        del rule, repo_root
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        del prompt, repo_root
        return []

    def finalize(self, repo_root: Path) -> list[Path]:
        target = repo_root / _FAKE_OUTPUT
        write_output_text(target, f"root-name={repo_root.name}\n")
        return [target]


@pytest.fixture
def fake_name_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register :class:`FakeNameAdapter` beside the installed adapters for this test."""
    real_entry_points = metadata.entry_points
    fake = metadata.EntryPoint(
        name="fakename",
        value=f"{__name__}:FakeNameAdapter",
        group="coding_agent_playbook.adapters",
    )

    # importlib.metadata's own function is patched, so every other caller passes through.
    def _entry_points(**kwargs: Any) -> list[metadata.EntryPoint]:
        found = list(real_entry_points(**kwargs))
        return [*found, fake] if kwargs.get("group") == fake.group else found

    monkeypatch.setattr(
        "coding_agent_playbook.adapters.registry.metadata.entry_points", _entry_points
    )


@pytest.mark.usefixtures("fake_name_adapter")
@pytest.mark.parametrize("form", [".", "ALIAS"])
def test_out_of_tree_adapter_sees_the_real_root_name(
    probe: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    config = probe / ".coding-agent-playbook.toml"
    config.write_text(
        _DEFAULT_CONFIG.replace(_ADAPTERS_LINE, 'adapters_enabled = ["fakename"]'), encoding="utf-8"
    )
    if form == "ALIAS":
        if sys.platform == "win32":
            pytest.skip("POSIX symlinks")
        alias = tmp_path / "alias"
        alias.symlink_to(probe, target_is_directory=True)
        form = str(alias)
    monkeypatch.chdir(probe)
    assert _sync_then_check(["--repo-root", form], ["--repo-root", form]) == 0
    assert (probe / _FAKE_OUTPUT).read_text(encoding="utf-8").endswith("root-name=probe\n")
