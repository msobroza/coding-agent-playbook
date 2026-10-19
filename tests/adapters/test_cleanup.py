"""Cross-adapter cleanup contract for the anchored sentinel (prK §P3).

Every built-in sentinel scanner (the ABC's directory scan used by Continue and
OpenCode, Claude Code's ``.claude/commands`` scan + ``CLAUDE.md`` and rules-file
checks, AGENTS.md's single-file check and the agent_harness tree scan)
recognises an engine-generated file by ``_sentinel.has_sentinel``: a sentinel line on line 1,
or on the first body line after a leading YAML frontmatter block. A sentinel
anywhere else is user prose and never makes a file deletable. ``stale_outputs``
is the read-only twin ``sync --check`` uses: it reports exactly what
``cleanup_stale`` deletes and deletes nothing. A scan opens each file once,
never through a symlink and never a secret path, and reads only the head
``has_sentinel`` decides on.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._sentinel import SENTINEL_HEAD_BYTES, has_sentinel, sentinel_line
from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.adapters.agents_md import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_ import ContinueAdapter
from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from tests.fakes import record_opens

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.adapters.base import Adapter

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")

_FRONTMATTER = "---\ndescription: Review the diff\ndisallowed-tools: Edit Write NotebookEdit\n---\n"

#: A generated file whose sentinel is the first body line after its frontmatter.
_FRONTMATTER_SENTINEL_TEXT = f"{_FRONTMATTER}{sentinel_line('html')}\n\n# Review\n"

#: A user file that merely *quotes* the sentinel below its first body line.
_QUOTED_SENTINEL_TEXT = f"{_FRONTMATTER}# Notes\n\nOur header reads:\n{sentinel_line('html')}\n"

_SCANNED_OUTPUTS: list[tuple[Callable[[], Adapter], str]] = [
    (ClaudeCodeAdapter, ".claude/commands/review.md"),
    (ClaudeCodeAdapter, ".claude/CLAUDE.md"),
    (ClaudeCodeAdapter, ".claude/rules/coding-agent-playbook.md"),
    (AgentHarnessAdapter, "references/playbook-notes.md"),
    (AgentHarnessAdapter, "rules/50-review.md"),
    (AgentHarnessAdapter, "HARNESS.md"),
    (ContinueAdapter, ".continue/rules/50-review.md"),
    (ContinueAdapter, ".continue/prompts/review.md"),
    (OpenCodeAdapter, ".opencode/command/review.md"),
    (AgentsMdAdapter, "AGENTS.md"),
]
_IDS = [f"{factory.__name__}:{rel}" for factory, rel in _SCANNED_OUTPUTS]


def _write(repo_root: Path, rel: str, text: str) -> Path:
    target = repo_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_frontmatter_sentinel_file_is_cleaned(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    stale = _write(tmp_path, rel, _FRONTMATTER_SENTINEL_TEXT)

    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert deleted == [stale]
    assert not stale.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_frontmatter_sentinel_file_in_written_paths_is_kept(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    current = _write(tmp_path, rel, _FRONTMATTER_SENTINEL_TEXT)

    deleted = make_adapter().cleanup_stale({current.resolve()}, tmp_path)

    assert deleted == []
    assert current.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_sentinel_quoted_below_first_body_line_is_kept(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    user_file = _write(tmp_path, rel, _QUOTED_SENTINEL_TEXT)

    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert deleted == []
    assert user_file.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_binary_file_is_skipped_not_crashed_on(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xfe\x00\x00binary garbage")

    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert deleted == []
    assert target.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_stale_outputs_reports_without_deleting(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    """``sync --check`` asks ``stale_outputs``: same verdict, nothing deleted."""
    stale = _write(tmp_path, rel, _FRONTMATTER_SENTINEL_TEXT)
    _write(tmp_path, f"{rel}.user.md", _QUOTED_SENTINEL_TEXT)

    assert make_adapter().stale_outputs(set(), tmp_path) == [stale]
    assert stale.exists()


def test_harness_user_reference_quoting_the_sentinel_survives_sync_cleanup(
    tmp_path: Path,
) -> None:
    """Regression: agent_harness matched the sentinel *anywhere*, so a user's
    ``references/`` note quoting it in an indented code block was deleted."""
    note = _write(
        tmp_path,
        "references/playbook-notes.md",
        f"# Playbook notes\n\nGenerated files start with:\n\n    {sentinel_line('html')}\n",
    )

    assert AgentHarnessAdapter().cleanup_stale(set(), tmp_path) == []
    assert note.exists()


def test_quoted_sentinel_in_first_line_prose_is_kept(tmp_path: Path) -> None:
    """Only an exact sentinel line counts: prose on line 1 that mentions it is the user's."""
    readme = _write(
        tmp_path,
        ".continue/rules/README.md",
        f"Files whose first line is `{sentinel_line('html')}` are generated.\n\nMy notes.\n",
    )

    assert ContinueAdapter().cleanup_stale(set(), tmp_path) == []
    assert readme.exists()


# --- aliased output dirs, symlinks, secrets, bounded reads ---------------------


@posix_only
@pytest.mark.parametrize(
    ("make_adapter", "real_dir", "alias"),
    [
        (ContinueAdapter, ".continue/rules", ".continue/prompts"),
        (AgentHarnessAdapter, "rules", "references"),
    ],
    ids=["continue", "agent_harness"],
)
def test_aliased_output_dirs_report_a_stale_file_once(
    tmp_path: Path, make_adapter: Callable[[], Adapter], real_dir: str, alias: str
) -> None:
    """Regression: with ``.continue/prompts -> rules`` the stale file was listed
    under both spellings and the second ``unlink()`` raised FileNotFoundError
    mid-sync, after the outputs were written but before the lockfile was saved."""
    stale = _write(tmp_path, f"{real_dir}/50-x.md", f"{sentinel_line('html')}\nBody\n")
    (tmp_path / alias).symlink_to(Path(real_dir).name, target_is_directory=True)

    assert len(make_adapter().stale_outputs(set(), tmp_path)) == 1
    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert len(deleted) == 1
    assert deleted[0].resolve() == (tmp_path / real_dir / "50-x.md").resolve()
    assert not stale.exists()


def test_cleanup_stale_tolerates_an_override_reporting_a_file_twice(tmp_path: Path) -> None:
    stale = _write(tmp_path, ".continue/rules/50-x.md", f"{sentinel_line('html')}\nBody\n")

    class TwiceAdapter(ContinueAdapter):
        def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
            return [stale, stale]

    assert TwiceAdapter().cleanup_stale(set(), tmp_path) == [stale, stale]
    assert not stale.exists()


@posix_only
@pytest.mark.parametrize(
    ("make_adapter", "out_dir"),
    [
        (ContinueAdapter, ".continue/rules"),
        (ClaudeCodeAdapter, ".claude/commands"),
        (OpenCodeAdapter, ".opencode/command"),
        (AgentHarnessAdapter, "rules"),
        (AgentHarnessAdapter, "references"),
    ],
    ids=["continue", "claude_code", "opencode", "harness-rules", "harness-references"],
)
def test_scan_never_opens_secrets_or_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_adapter: Callable[[], Adapter],
    out_dir: str,
) -> None:
    """Regression: ``sync --check`` (a pre-commit hook) read every file under the
    scanned dirs in full — ``.env``, ``prod.tfvars``, an SSH key, and links out
    of the repo such as ``references/aws-notes.md -> ~/.aws/credentials``."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    secret_store = home / ".aws" / "credentials"
    secret_store.parent.mkdir(parents=True)
    secret_store.write_text(f"{sentinel_line('html')}\nkey = AKIA\n", encoding="utf-8")
    repo = tmp_path / "repo"
    tagged = f"{sentinel_line('html')}\nTOKEN=secret\n"
    secrets = [_write(repo, f"{out_dir}/{name}", tagged) for name in (".env", "prod.tfvars")]
    secrets.append(_write(repo, f"{out_dir}/id_ed25519", tagged))
    link = repo / out_dir / "aws-notes.md"
    link.symlink_to(secret_store)
    opened = record_opens(monkeypatch)

    stale = make_adapter().stale_outputs(set(), repo)

    assert stale == []
    never_opened = {*secrets, link, secret_store}
    assert [p for p in opened if p in never_opened or p.resolve() == secret_store] == []


_HEAD_CASES = {
    "sentinel-line-1": f"{sentinel_line('html')}\nbody\n",
    "sentinel-line-1-crlf": f"{sentinel_line('html')}\r\nbody\r\n",
    "frontmatter-then-sentinel": f"{_FRONTMATTER}{sentinel_line('html')}\nbody\n",
    "frontmatter-crlf": f"---\r\nname: x\r\n---\r\n{sentinel_line('html')}\r\n",
    "bom-line-1": f"\ufeff{sentinel_line('html')}\nbody\n",
    "bom-frontmatter-then-sentinel": f"\ufeff{_FRONTMATTER}{sentinel_line('html')}\nbody\n",
    "quoted-below-body": _QUOTED_SENTINEL_TEXT,
    "lone-cr-after-sentinel": f"{sentinel_line('html')}\rjunk\nbody\n",
    "unclosed-frontmatter": f"---\nname: x\n{sentinel_line('html')}\n",
    "fence-at-eof": "---\nname: x\n---",
    "empty": "",
    "sentinel-without-newline": sentinel_line("hash"),
}


@pytest.mark.parametrize("text", list(_HEAD_CASES.values()), ids=list(_HEAD_CASES))
def test_sentinel_head_verdict_matches_a_whole_file_read(tmp_path: Path, text: str) -> None:
    target = tmp_path / "f.md"
    target.write_bytes(text.encode("utf-8"))
    assert ContinueAdapter._carries_sentinel(target) is has_sentinel(text)


def test_sentinel_head_read_is_bounded(tmp_path: Path) -> None:
    """Only line 1 (or a frontmatter block + one line) is read, never the whole file.

    The bounded read itself lives in ``_sentinel.file_has_sentinel`` (shared
    with the hook guards); this pins that adapters still go through it.
    """
    big_body = "x" * (2 * SENTINEL_HEAD_BYTES) + "\n"
    fronted = tmp_path / "fronted.md"
    fronted.write_text(f"{_FRONTMATTER}{sentinel_line('html')}\n{big_body}", encoding="utf-8")
    plain = tmp_path / "plain.md"
    plain.write_text(f"# Title\n{big_body}", encoding="utf-8")

    assert ContinueAdapter._carries_sentinel(fronted) is True
    assert ContinueAdapter._carries_sentinel(plain) is False
