"""secret-content-guard: secret tokens never reach the disk or a push (specs/prK-hook-pack.md §E.4).

Writes, Edits, NotebookEdits and OpenCode ``apply_patch`` calls run through
``playbook-hook simulate pre_tool_use``; ``FakeGit`` answers the ``HEAD``
blob the pragma check reads and the unpushed commits of a push. One case
builds a real repository and pushes with the real, hardened ``SafeGit``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime._git_parse import AddedLine, DiffLines
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.git import SafeGit
from coding_agent_playbook.hook_runtime.handlers.secret_content import PRAGMA_ADVICE
from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.security.secrets import SECRET_ADVICE
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.proc import SubprocessProc
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.content

HOOK_ID: Final = "secret-content-guard"
#: Real-shaped (AKIA + 16) but not a key anyone issued; built so no scanner flags this file.
AWS_KEY: Final = "AKIA" + "Z7Q2" * 4
SETTINGS: Final = "src/app/settings.py"
PRAGMA: Final = "  # playbook: allow-secret aws-access-key-id"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write(SETTINGS, "import os\n\nKEY = None\nDEBUG = False\n")
    pack_repo.install_pack([HOOK_ID])
    return pack_repo


def _run(
    repo: PackRepo,
    deps: Deps,
    tool: str,
    tool_input: dict[str, Any],
    *,
    git: FakeGit | SafeGit | None = None,
    harness: Harness = Harness.CLAUDE_CODE,
) -> SimulateReport:
    payload = repo.tool_payload(tool, tool_input)
    return repo.simulate(payload, deps(git=git or FakeGit()), harness=harness)


def _write(repo: PackRepo, deps: Deps, rel: str, content: str, **kw: Any) -> SimulateReport:
    return _run(repo, deps, "Write", {"file_path": str(repo.root / rel), "content": content}, **kw)


def _edit(repo: PackRepo, deps: Deps, new: str, **kw: Any) -> SimulateReport:
    tool_input = {
        "file_path": str(repo.root / SETTINGS),
        "old_string": "KEY = None",
        "new_string": new,
    }
    return _run(repo, deps, "Edit", tool_input, **kw)


def _leaks(text: str, secret: str, window: int = 6) -> bool:
    """Whether any ``window``-character run of ``secret`` appears in ``text``."""
    return any(secret[i : i + window] in text for i in range(len(secret) - window + 1))


@pytest.mark.parametrize("harness", [Harness.CLAUDE_CODE, Harness.OPENCODE])
def test_write_real_aws_key_denied_reason_masked(
    repo: PackRepo, deps: Deps, harness: Harness
) -> None:
    report = _write(
        repo, deps, "src/app/aws.py", f'"""AWS."""\nKEY = "{AWS_KEY}"\n', harness=harness
    )

    combined = report.trace.combined
    assert combined.decision is Decision.DENY
    assert combined.reason.splitlines() == [
        'Blocked: this write adds a secret token at "src/app/aws.py":2 aws-access-key-id '
        "(20 chars).",
        SECRET_ADVICE,
    ]
    assert not _leaks(combined.reason, AWS_KEY[4:])
    assert not _leaks(report.trace.wire.stdout + report.trace.wire.stderr, AWS_KEY[4:])


def test_documented_example_key_passes(repo: PackRepo, deps: Deps) -> None:
    report = _write(repo, deps, "docs/aws.md", "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n")

    assert report.trace.combined.decision is Decision.NONE


def test_low_entropy_assignment_passes(repo: PackRepo, deps: Deps) -> None:
    report = _write(repo, deps, "src/app/db.py", 'PASSWORD = "hunter2"\nURL = "postgres://db/x"\n')

    assert report.trace.combined.decision is Decision.NONE


def test_edit_names_the_file_line_it_lands_on(repo: PackRepo, deps: Deps) -> None:
    report = _edit(repo, deps, f'KEY = "{AWS_KEY}"')

    assert report.trace.combined.reason.splitlines()[0] == (
        'Blocked: this write adds a secret token at "src/app/settings.py":3 aws-access-key-id '
        "(20 chars)."
    )


def test_new_allow_secret_pragma_asks(repo: PackRepo, deps: Deps) -> None:
    head = FakeGit(head_blobs={SETTINGS: b"import os\n\nKEY = None\n"})

    report = _edit(repo, deps, f'KEY = "{AWS_KEY}"{PRAGMA}', git=head)

    assert report.trace.combined.decision is Decision.ASK
    assert report.trace.combined.reason.splitlines() == [
        '"src/app/settings.py":3 aws-access-key-id (20 chars) carries a new allow-secret pragma.',
        PRAGMA_ADVICE,
    ]


def test_pragma_at_head_passes(repo: PackRepo, deps: Deps) -> None:
    line = f'KEY = "{AWS_KEY}"{PRAGMA}'
    head = FakeGit(head_blobs={SETTINGS: f"import os\n\n{line}\n".encode()})

    report = _edit(repo, deps, line, git=head)

    assert report.trace.combined.decision is Decision.NONE
    assert head.calls == [("cat_head", (SETTINGS,))]


def test_push_with_upstream_scans_its_range(repo: PackRepo, deps: Deps) -> None:
    added = (AddedLine("deploy/ci.sh", 4, f"export AWS_ACCESS_KEY_ID={AWS_KEY}"),)
    git = FakeGit(upstream_ref="refs/remotes/origin/main", unpushed=DiffLines(added=added))

    report = _run(repo, deps, "Bash", {"command": "git -C . push origin HEAD"}, git=git)

    assert report.trace.combined.reason.splitlines()[0] == (
        'Blocked: an unpushed commit adds a secret token at "deploy/ci.sh":4 '
        "aws-access-key-id (20 chars)."
    )
    assert ("unpushed_lines", ("refs/remotes/origin/main",)) in git.calls


def test_push_scan_without_upstream_finds_key_in_only_commit(
    pack_repo: PackRepo,
    deps: Deps,
    real_git: Callable[..., str],
    real_proc: SubprocessProc,
) -> None:
    real_git("init", "-q", cwd=pack_repo.root)
    pack_repo.write("deploy/config.py", f'KEY = "{AWS_KEY}"\n')
    real_git("add", "deploy/config.py", cwd=pack_repo.root)
    real_git("commit", "-q", "-m", "add deploy config", cwd=pack_repo.root)
    pack_repo.install_pack([HOOK_ID])
    found = find_repo(str(pack_repo.root))
    assert found is not None
    git = SafeGit(found, proc=real_proc, env=dict(os.environ))

    report = _run(pack_repo, deps, "Bash", {"command": "git push -u origin feature"}, git=git)

    assert report.trace.combined.decision is Decision.DENY
    assert '"deploy/config.py":1 aws-access-key-id' in report.trace.combined.reason


def test_non_push_git_command_reads_no_git(repo: PackRepo, deps: Deps) -> None:
    git = FakeGit()

    report = _run(repo, deps, "Bash", {"command": "git status && echo push"}, git=git)

    assert report.trace.combined.decision is Decision.NONE
    assert git.calls == []


def test_five_mb_write_scans_head_tail_and_asks(repo: PackRepo, deps: Deps) -> None:
    body = "x = 1\n" * (5 * 1024 * 1024 // 6)

    clean = _write(repo, deps, "data/big.py", body)
    tail_key = _write(repo, deps, "data/big.py", f'{body}KEY = "{AWS_KEY}"\n')

    assert clean.trace.combined.decision is Decision.ASK
    assert clean.trace.combined.reason.splitlines()[0] == (
        '"data/big.py" is too large to scan whole: only its head and tail were.'
    )
    assert tail_key.trace.combined.decision is Decision.DENY


def test_notebook_edit_and_apply_patch_added_lines_scanned(repo: PackRepo, deps: Deps) -> None:
    notebook = repo.write("nb/explore.ipynb", '{"cells": [], "metadata": {}, "nbformat": 4}\n')
    cell = {
        "notebook_path": str(notebook),
        "new_source": f'key = "{AWS_KEY}"',
        "edit_mode": "insert",
    }
    patch = (
        "*** Begin Patch\n*** Add File: deploy/env.sh\n"
        f"+export AWS_ACCESS_KEY_ID={AWS_KEY}\n*** End Patch\n"
    )

    edited = _run(repo, deps, "NotebookEdit", cell)
    patched = _run(
        repo,
        deps,
        "apply_patch",
        {"patchText": patch, "patch_text": patch},
        harness=Harness.OPENCODE,
    )

    assert edited.trace.combined.decision is Decision.DENY
    assert patched.trace.combined.decision is Decision.DENY
    assert '"deploy/env.sh" aws-access-key-id' in patched.trace.combined.reason


def test_credential_file_content_is_left_to_the_path_guard(repo: PackRepo, deps: Deps) -> None:
    report = _write(repo, deps, ".env.local", f"AWS_ACCESS_KEY_ID={AWS_KEY}\n")

    assert report.trace.combined.decision is Decision.NONE


def test_overlay_extra_pattern_joins_the_ruleset(pack_repo: PackRepo, deps: Deps) -> None:
    row = {"id": "acme-token", "regex": "acme_[0-9a-f]{32}", "label": "Acme token"}
    pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: {"extra_patterns": [row]}})

    report = _write(pack_repo, deps, "src/acme.py", f'TOKEN = "acme_{"0f" * 16}"\n')

    assert report.trace.combined.decision is Decision.DENY
    assert '"src/acme.py":1 acme-token (37 chars)' in report.trace.combined.reason
