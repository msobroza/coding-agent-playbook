"""``playbook scan-secrets``: the secret guards' off-workstation twin (specs/prK-hook-pack.md §E.4).

Every row runs the real command in-process against a real repository built
under ``hermetic_git_env`` (through ``real_git``); a stateless ``SafeGit``
reads the index, the range or the working tree. Exit codes: 0 clean, 1 a
secret token or a credential file, 2 a usage or git error. Sample tokens are
assembled at run time so this file holds none.
"""

from __future__ import annotations

import json
import os
import pathlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

AWS_KEY: Final = "AKIA" + "Z7Q2" * 4
GITHUB_TOKEN: Final = "gh" + "p_" + "a1B2" * 9
PRAGMA: Final = "# playbook: allow-secret aws-access-key-id"


class Repo:
    """A real repository on ``main``; ``write`` edits files, ``stage`` adds, ``commit`` commits."""

    def __init__(self, root: Path, git: Callable[..., str]) -> None:
        self.root = root
        self.git = git

    def write(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def stage(self, files: dict[str, str]) -> None:
        self.write(files)
        self.git("add", "-A", cwd=self.root)

    def commit(self, message: str, files: dict[str, str]) -> None:
        self.stage(files)
        self.git("commit", "-q", "-m", message, cwd=self.root)

    def scan(self, *args: str) -> int:
        return main(["scan-secrets", *args, "--repo-root", str(self.root)])


def _new_repo(tmp_path: Path, real_git: Callable[..., str]) -> Repo:
    root = Path(os.path.realpath(tmp_path)) / "consumer"
    root.mkdir()
    real_git("init", "-q", "-b", "main", cwd=root)
    return Repo(root, real_git)


@pytest.fixture
def repo(tmp_path: Path, real_git: Callable[..., str]) -> Repo:
    built = _new_repo(tmp_path, real_git)
    built.commit("init", {"src/app.py": "x = 1\n", ".gitignore": ".env\n"})
    return built


def _assert_masked(*streams: str) -> None:
    for secret in (AWS_KEY, GITHUB_TOKEN):
        assert all(secret[4:] not in stream for stream in streams)


def test_staged_key_exits_1_with_masked_output(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.stage({"src/conf.py": f"import os\nKEY = '{AWS_KEY}'\n"})

    assert repo.scan("--staged") == 1

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines[0] == "src/conf.py:2: aws-access-key-id: AWS access key id (20 chars)"
    assert lines[-2] == "Use an env var or the secret manager and reference it by name."
    assert lines[-1] == "scan-secrets staged: 1 finding"
    _assert_masked(captured.out, captured.err)


def test_staged_mode_works_before_the_first_commit(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    fresh = _new_repo(tmp_path, real_git)
    fresh.stage({"deploy.sh": f"export GH={GITHUB_TOKEN}\n"})

    assert fresh.scan("--staged") == 1
    assert "deploy.sh:1: github-token" in capsys.readouterr().out


def test_staged_credential_file_is_flagged_by_path_not_scanned(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.stage({"config/credentials.json": f'{{"key": "{AWS_KEY}"}}\n'})

    assert repo.scan("--staged") == 1

    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("config/credentials.json: secret-path: ")
    assert "aws-access-key-id" not in out


def test_range_mode_scans_added_lines_only(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit("legacy key", {"src/old.py": f"OLD = '{AWS_KEY}'\n"})
    repo.commit("feature", {"src/new.py": f"a = 1\nb = 2\nTOKEN = '{GITHUB_TOKEN}'\n"})

    assert repo.scan("--range", "HEAD~1..HEAD", "--format", "json") == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["scope"] == "HEAD~1..HEAD"
    assert [(f["path"], f["line"], f["rule"]) for f in report["findings"]] == [
        ("src/new.py", 3, "github-token")
    ]
    assert report["exit"] == 1
    _assert_masked(captured.out, captured.err)


def test_worktree_flags_untracked_secret_file_by_path_without_reading(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.write(
        {
            ".env.prod": f"AWS_ACCESS_KEY_ID={AWS_KEY}\n",
            ".env": f"IGNORED={AWS_KEY}\n",  # gitignored: git never lists it
            "notes/todo.py": f"x = 1\nt = '{GITHUB_TOKEN}'\n",
            "src/app.py": f"x = 1\nKEY = '{AWS_KEY}'\n",
        }
    )
    opened: list[Path] = []
    original = pathlib.Path.open

    def _spy(self: pathlib.Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", _spy)

    assert repo.scan("--worktree") == 1

    out = capsys.readouterr().out.splitlines()
    assert out[:3] == [  # sorted by path, then line
        ".env.prod: secret-path: a credential file; gitignore it and commit only an "
        ".env.example of variable names",
        "notes/todo.py:2: github-token: GitHub token (40 chars)",
        "src/app.py:2: aws-access-key-id: AWS access key id (20 chars)",
    ]
    assert out[-1] == "scan-secrets worktree: 3 findings"
    assert repo.root / ".env.prod" not in opened
    assert repo.root / ".env" not in opened
    assert repo.root / "notes/todo.py" in opened  # the spy saw the real reads


def test_worktree_never_follows_an_untracked_symlink(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = Path(os.path.realpath(tmp_path)) / "outside.txt"
    outside.write_text(f"KEY = '{AWS_KEY}'\n", encoding="utf-8")
    (repo.root / "link.txt").symlink_to(outside)

    assert repo.scan("--worktree") == 0
    assert "note: link.txt: a symlink; not followed" in capsys.readouterr().out


def test_pragma_at_base_honored_new_pragma_not(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    vouched = f"FIXTURE = '{AWS_KEY}'  {PRAGMA}"
    repo.commit("fixture", {"tests/keys.py": f"{vouched}\n"})

    assert repo.scan("tests/keys.py") == 0  # committed at HEAD: honored

    repo.write({"tests/keys.py": f"{vouched}\nOTHER = '{AWS_KEY}'  {PRAGMA}\n"})

    assert repo.scan("tests/keys.py") == 1
    out = capsys.readouterr().out
    assert (
        "tests/keys.py:2: aws-access-key-id: AWS access key id (20 chars); its allow-secret "
        "pragma is new: it counts only once committed" in out
    )
    assert "tests/keys.py:1:" not in out


def test_clean_tree_exits_0(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert repo.scan("--worktree") == 0
    assert capsys.readouterr().out.strip() == "scan-secrets worktree: clean"


def test_guardrails_extra_globs_extend(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    config = (
        '[guardrails.secrets]\nextra_globs = ["*.vaultdump"]\nallow_paths = ["tests/fixtures/**"]\n'
    )
    repo.commit("policy", {".coding-agent-playbook.toml": config})
    repo.stage({"backup/db.vaultdump": "x\n", "tests/fixtures/app/.env.test": "A=1\n"})

    assert repo.scan("--staged") == 1

    out = capsys.readouterr().out
    assert "backup/db.vaultdump: secret-path: " in out
    assert "tests/fixtures/app/.env.test" not in out


def test_policy_comes_from_the_base_not_the_change(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    relaxed = '[guardrails.secrets]\nallow_paths = ["deploy/**"]\n'
    repo.stage({".coding-agent-playbook.toml": relaxed, "deploy/.env.prod": "A=1\n"})

    assert repo.scan("--staged") == 1
    assert "deploy/.env.prod: secret-path: " in capsys.readouterr().out


def test_paths_and_a_mode_is_a_usage_error(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert repo.scan("--staged", "src/app.py") == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_missing_path_is_a_usage_error(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert repo.scan("no/such.py") == 2
    assert "no/such.py" in capsys.readouterr().err


def test_malformed_guardrails_at_base_exit_2(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("bad", {".coding-agent-playbook.toml": "[guardrails.secrets]\nextra_globs = 3\n"})

    assert repo.scan("--worktree") == 2
    assert "extra_globs" in capsys.readouterr().err


def test_a_base_config_that_is_not_toml_exits_2_naming_the_revision(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("bad", {".coding-agent-playbook.toml": "[guardrails.secrets\n"})

    assert repo.scan("--worktree") == 2

    captured = capsys.readouterr()
    assert captured.err.startswith("error: .coding-agent-playbook.toml at HEAD: invalid TOML: ")
    assert captured.out == ""


#: Valid example-format values (checksums hold), assembled so this file holds none whole.
IBAN: Final = "GB33" + "BUKB" + "2020" + "1555" + "5555" + "55"
SSN: Final = "123" + "-45-" + "6789"


def test_pii_flag_reports_masked_category(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    """pii-prompt-guard's CI twin (§E.5): off by default, masked ``pii:<detector>`` with --pii."""
    repo.write(
        {
            "exports/customers.csv": f"name;iban\nAda;{IBAN}\n",
            "tests/cards.py": "SANDBOX = '4111 1111 1111 1111'\n",  # a published test value
        }
    )
    paths = ("exports/customers.csv", "tests/cards.py")

    assert repo.scan(*paths) == 0
    capsys.readouterr()
    assert repo.scan("--pii", *paths) == 1

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "exports/customers.csv:2: pii:iban: IBAN (22 chars)",
        "Replace personal data with a placeholder or a synthetic value.",
        "scan-secrets paths: 1 finding",
    ]
    assert IBAN[4:] not in captured.out + captured.err


def test_pii_detectors_choose_the_detectors(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.stage({"src/hr.py": f"OWNER_SSN = '{SSN}'\n"})

    assert repo.scan("--staged", "--pii") == 0  # us_ssn is an overlay choice, not the default
    capsys.readouterr()
    assert repo.scan("--staged", "--pii-detectors", "iban,us_ssn", "--format", "json") == 1

    report = json.loads(capsys.readouterr().out)
    assert report["findings"] == [
        {"path": "src/hr.py", "line": 1, "rule": "pii:us_ssn", "detail": "US SSN (11 chars)"}
    ]


def test_unknown_pii_detector_is_a_usage_error(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert repo.scan("--worktree", "--pii-detectors", "iban,email") == 2
    assert "unknown PII detector 'email'" in capsys.readouterr().err
