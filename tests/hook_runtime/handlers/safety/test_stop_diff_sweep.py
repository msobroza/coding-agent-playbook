"""stop-diff-sweep: the ``secrets`` Stop stage (specs/prK-hook-pack.md §E.4).

Every Stop is a real ``playbook-hook simulate stop`` with the coordinator
(stop-ci-parity-gate) and this hook on. ``FakeGit`` answers the working
tree's added lines (``diff_added``), its untracked files and the ``HEAD``
blobs; the files themselves are real, so a ``pathlib`` spy can prove that a
credential file is flagged by path without ever being opened.
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.git.parse import AddedLine
from coding_agent_playbook.hook_runtime.handlers.safety._secret_sweep import FIX, PII_FIX
from coding_agent_playbook.hook_runtime.handlers.safety.stop_diff_sweep import PARTIAL_NOTE
from coding_agent_playbook.hook_runtime.stop.output import red_note
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from tests.hook_runtime.handlers.pack_repo import engine_rules
from tests.hook_runtime.handlers.stop_kit import changed_git, reason_lines, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.fakes import FakeGit
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "stop-diff-sweep"
GATE_ID: Final = "stop-ci-parity-gate"
DESER_ID: Final = "ml-unsafe-deserialization-guard"
#: Real-shaped (AKIA + 16) but never issued; built so no scanner flags this file.
AWS_KEY: Final = "AKIA" + "Z7Q2" * 4
KEY_LINE: Final = f'KEY = "{AWS_KEY}"'
MIB: Final = 1024 * 1024


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write("config.py", f"import os\n\n{KEY_LINE}\n")
    pack_repo.install_pack([GATE_ID, HOOK_ID])
    return pack_repo


def _stop(
    repo: PackRepo, deps: Deps, git: FakeGit, state: Path, *, case: str = "plain"
) -> SimulateReport:
    payload = stop_payload(repo, message="Done.", case=case)
    return stop(repo, deps, payload, git=git, state=state)


def _sed_key() -> FakeGit:
    """``sed -i`` wrote a key into config.py: one added line in ``git diff HEAD``."""
    return changed_git(added=(AddedLine("config.py", 3, KEY_LINE),))


def test_sed_written_key_joins_combined_block(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    report = _stop(repo, deps, _sed_key(), tmp_path / "state")

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [
        f'[secrets] "config.py":3 aws-access-key-id (20 chars); {FIX}',
    ]
    assert AWS_KEY[4:] not in report.trace.combined.reason


def test_untracked_env_prod_flagged_by_path_never_read(
    repo: PackRepo, deps: Deps, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.write(".env.prod", f"AWS_ACCESS_KEY_ID={AWS_KEY}\n")
    repo.write("notes/todo.py", "x = 1\n")
    opened: list[Path] = []
    original = pathlib.Path.open

    def _spy(self: pathlib.Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", _spy)
    git = changed_git(untracked=(".env.prod", "notes/todo.py"))

    report = _stop(repo, deps, git, tmp_path / "state")

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [f'[secrets] ".env.prod" secret-path; {FIX}']
    assert repo.root / ".env.prod" not in opened
    assert repo.root / "notes/todo.py" in opened  # the spy saw the real reads


def test_sparse_200mb_model_pt_warn_line(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    for name in ("model.pt", "dump.bin"):
        with (repo.root / name).open("wb") as handle:
            handle.truncate(200 * MIB)  # sparse: no 200 MB written to the test disk
    git = changed_git(untracked=("model.pt", "dump.bin"))

    report = _stop(repo, deps, git, tmp_path / "state")

    assert report.trace.combined.decision is Decision.NONE
    notes = [n for n in report.trace.combined.user_notes if n.startswith("[secrets]")]
    assert notes == [
        '[secrets] "model.pt" is an untracked artifact (200 MiB); '
        "gitignore it or keep it outside the repository",
        '[secrets] "dump.bin" is an untracked large file (200 MiB); '
        "gitignore it or keep it outside the repository",
    ]


def test_same_fingerprint_system_message_only(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    state = tmp_path / "state"

    first = _stop(repo, deps, _sed_key(), state)
    again = _stop(repo, deps, _sed_key(), state, case="block_chain")  # stop_hook_active

    assert first.trace.combined.decision is Decision.DENY
    assert again.trace.combined.decision is Decision.NONE
    assert again.trace.combined.user_notes == (red_note("secrets"),)


def test_mode_warn_never_blocks(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    pack_repo.install_pack([GATE_ID, HOOK_ID], handler_config={HOOK_ID: {"mode": "warn"}})

    report = _stop(pack_repo, deps, _sed_key(), tmp_path / "state")

    assert report.trace.combined.decision is Decision.NONE
    assert f'[secrets] "config.py":3 aws-access-key-id (20 chars); {FIX}' in (
        report.trace.combined.user_notes
    )


def test_guardrails_cannot_lower_the_shipped_mode(pack_repo: PackRepo, deps: Deps) -> None:
    """``mode`` is strictest: a consumer layer asking for ``warn`` keeps the engine's ``block``."""
    data = pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: {"mode": "warn"}})

    assert b'"mode":"block"' in data and b'"mode":"warn"' not in data


def test_byte_cap_reports_partially_scanned(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    pack_repo.install_pack([GATE_ID, HOOK_ID], per_hook={HOOK_ID: {"max_scan_bytes": 64}})
    added = tuple(AddedLine("src/big.py", n, f"value_{n} = {n} * 1000") for n in range(1, 20))

    report = _stop(pack_repo, deps, changed_git(added=added), tmp_path / "state")

    assert report.trace.combined.decision is Decision.NONE
    assert PARTIAL_NOTE in report.trace.combined.user_notes


def test_pragma_at_head_waives_a_tracked_line(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    vouched = f"{KEY_LINE}  # playbook: allow-secret aws-access-key-id"
    at_head = changed_git(
        added=(AddedLine("tests/keys.py", 1, vouched),),
        head_blobs={"tests/keys.py": f"{vouched}\n".encode()},
    )
    fresh = changed_git(added=(AddedLine("tests/keys.py", 1, vouched),))

    waived = _stop(repo, deps, at_head, tmp_path / "a")
    blocked = _stop(repo, deps, fresh, tmp_path / "b")

    assert waived.trace.combined.decision is Decision.NONE
    assert blocked.trace.combined.decision is Decision.DENY


def test_deser_rescan_warn_line_rides_same_walk(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    facts = DetectInputs(facts={"ml_stack": {"torch": ">=2.3"}})
    pack_repo.install_pack([GATE_ID, HOOK_ID, DESER_ID], rules=engine_rules(), detect=facts)
    pack_repo.write("src/app/model.py", "import pickle\nx = pickle.loads(b)\n")
    git = changed_git(
        added=(AddedLine("src/app/model.py", 2, "x = pickle.loads(b)"),),
        head_blobs={"src/app/model.py": b"import pickle\n"},
    )

    report = _stop(pack_repo, deps, git, tmp_path / "state")

    assert report.trace.combined.decision is Decision.NONE
    [line] = [n for n in report.trace.combined.user_notes if n.startswith("[secrets]")]
    assert line.startswith('[secrets] "src/app/model.py":2 adds pickle.loads(...) outside the')


def test_alone_without_the_coordinator_still_blocks(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    pack_repo.install_pack([HOOK_ID])
    payload = stop_payload(pack_repo, message="Done.")
    runtime = deps(git=_sed_key())

    report = pack_repo.simulate(payload, runtime, event=EventName.STOP, state=tmp_path / "s")

    assert report.trace.combined.decision is Decision.DENY
    assert report.trace.combined.reason.startswith('[secrets] "config.py":3 aws-access-key-id')


#: A valid example-format IBAN (mod-97 holds), spaced as printed; never a real account.
IBAN_LINE: Final = 'REFUND_TO = "FR76 3000 6000 0112 3456 7890 189"'


def _pii_tree(repo: PackRepo) -> FakeGit:
    """An added line and an untracked export, each carrying an IBAN."""
    repo.write("exports/customers.txt", "name;iban\nAda;GB33BUKB20201555555555\n")
    return changed_git(
        added=(AddedLine("refunds.py", 2, IBAN_LINE),), untracked=("exports/customers.txt",)
    )


def test_pii_tier_runs_only_when_enabled(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    """pii-prompt-guard's file twin (§E.5): off in the engine, on once ``pii`` names detectors."""
    pack_repo.install_pack([GATE_ID, HOOK_ID])
    off = _stop(pack_repo, deps, _pii_tree(pack_repo), tmp_path / "off")

    pack_repo.install_pack([GATE_ID, HOOK_ID], handler_config={HOOK_ID: {"pii": ["iban"]}})
    on = _stop(pack_repo, deps, _pii_tree(pack_repo), tmp_path / "on")

    assert off.trace.combined.decision is Decision.NONE
    assert on.trace.combined.decision is Decision.DENY
    assert reason_lines(on)[1:] == [
        f'[secrets] "refunds.py":2 pii:iban (33 chars); {PII_FIX}',
        f'[secrets] "exports/customers.txt":2 pii:iban (22 chars); {PII_FIX}',
    ]
    assert "3000" not in on.trace.combined.reason
    assert "BUKB" not in on.trace.combined.reason
