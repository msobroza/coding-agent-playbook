"""prompt-output-contract-on-stop: the ``output-contract`` Stop stage (specs/prK-hook-pack.md §E.2).

Driven through ``playbook-hook simulate stop`` with the coordinator and this
hook on, and the engine's shipped prompts rendered into ``guard_config.prompts``.
The turn's record is seeded in a real state root (what an earlier call of the
turn resolved); the last tests derive it end to end from a Claude transcript,
with no ``user_prompt_submit`` dispatch (review finding #6). A review turn
changes no file, so ``FakeGit`` reports a tree equal to ``HEAD``: only
``needs_diff=False`` stages run, and ruff never does.
"""

from __future__ import annotations

import builtins
import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.git.safe_git import Fingerprint
from coding_agent_playbook.hook_runtime.state.active_prompt import TurnRecord, write_turn_record
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME, StateStore
from tests._catalog import CORE_ROOT
from tests.hook_runtime.fakes import FakeGit, FakeStageRunner
from tests.hook_runtime.handlers.stop_kit import (
    HEAD_TREE,
    changed_git,
    session_of,
    stop,
    stop_payload,
)
from tests.hook_runtime.transcript_kit import SessionTranscript

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "prompt-output-contract-on-stop"
GATE_ID: Final = "stop-ci-parity-gate"
PROMPTS: Final = CORE_ROOT / "prompts"
REVIEW_NO_VERDICT: Final = "Two findings:\n- src/app.py:3 shadows `os`.\n- a nit on naming."
MISS_LINE: Final = (
    '[output-contract] "/review-core": no final answer matches '
    "`(?im)^\\W*(verdict\\W*)?(approve with comments|approve|request changes)\\W*$`; end with it."
)


def _engine_prompts() -> list[Prompt]:
    names = ("review.md.j2", "find-injected-vulnerability.md.j2", "explain.md.j2")
    return [Prompt.from_markdown(PROMPTS / name, "coding_agent_playbook") for name in names]


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.install_pack([GATE_ID, HOOK_ID], prompts=_engine_prompts())
    return pack_repo


def _unchanged() -> FakeGit:
    fingerprint = Fingerprint(tree_id=HEAD_TREE, aux="", mode="tree", unchanged_vs_head=True)
    return FakeGit(fingerprint_value=fingerprint, head_tree_id=HEAD_TREE)


def _activate(state: Path, payload: bytes, slash: str = "review-core", turn: str = "pr_17") -> None:
    """Seed the turn record an earlier call of turn ``turn`` resolved for ``/<slash>``."""
    record = TurnRecord(slash, "prompt", turn)
    write_turn_record(StateStore(state / STATE_DIR_NAME), session_of(payload), record)


def _stop(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    message: str,
    *,
    slash: str | None = "review-core",
    git: FakeGit | None = None,
    runner: FakeStageRunner | None = None,
) -> SimulateReport:
    payload = stop_payload(repo, message=message)
    if slash is not None:
        _activate(state, payload, slash)
    return stop(repo, deps, payload, git=git or _unchanged(), state=state, runner=runner)


def test_review_without_verdict_context_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    report = _stop(repo, deps, tmp_path, REVIEW_NO_VERDICT)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (MISS_LINE,)


@pytest.mark.parametrize(
    "verdict", ["Verdict: approve", "**Approve with comments**", "- request changes."]
)
def test_verdict_approve_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path, verdict: str
) -> None:
    report = _stop(repo, deps, tmp_path, f"{REVIEW_NO_VERDICT}\n\n{verdict}")

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == ()
    assert report.trace.wire.stdout == ""


def test_resolved_turn_never_reopens_the_transcript(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads(stop_payload(repo, message=REVIEW_NO_VERDICT))
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"type": "user"}\n', "utf-8")
    payload["transcript_path"] = str(transcript)
    raw = json.dumps(payload).encode("utf-8")
    _activate(tmp_path, raw)
    opened: list[str] = []
    real_open = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)

    report = stop(repo, deps, raw, git=_unchanged(), state=tmp_path)

    assert report.trace.combined.user_notes == (MISS_LINE,)  # the stage did run
    assert str(transcript) not in opened


def test_no_active_prompt_inert(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    runner = FakeStageRunner()

    report = _stop(repo, deps, tmp_path, REVIEW_NO_VERDICT, slash=None, runner=runner)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == ()
    assert runner.calls == []


def test_prompt_without_contract_or_stale_turn_inert(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    explain = _stop(repo, deps, tmp_path / "a", REVIEW_NO_VERDICT, slash="explain")
    payload = stop_payload(repo, message=REVIEW_NO_VERDICT)
    _activate(tmp_path / "b", payload, turn="pr_16")  # a /review-core of an earlier turn
    stale = stop(repo, deps, payload, git=_unchanged(), state=tmp_path / "b")

    assert explain.trace.combined.user_notes == ()
    assert stale.trace.combined.user_notes == ()


def test_block_once_deny_line(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.install_pack(
        [GATE_ID, HOOK_ID], prompts=_engine_prompts(), per_hook={HOOK_ID: {"block_once": True}}
    )

    first = _stop(pack_repo, deps, tmp_path, REVIEW_NO_VERDICT)
    second = _stop(pack_repo, deps, tmp_path, REVIEW_NO_VERDICT, git=changed_git())

    assert first.trace.combined.decision is Decision.DENY
    assert first.trace.combined.reason.splitlines()[1:] == [MISS_LINE]
    assert second.trace.combined.decision is Decision.NONE  # once per prompt invocation
    assert MISS_LINE in second.trace.combined.user_notes


def test_runs_on_unchanged_tree(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    git, runner = _unchanged(), FakeStageRunner()

    report = _stop(repo, deps, tmp_path, REVIEW_NO_VERDICT, git=git, runner=runner)

    assert report.trace.combined.user_notes == (MISS_LINE,)
    assert runner.calls == []  # lint needs a diff: it never ran
    assert git.calls == [("fingerprint", ()), ("head_tree", ())]


def test_only_last_4000_chars_checked(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    early = "Verdict: approve\n" + "x" * 4_100

    report = _stop(repo, deps, tmp_path, early)

    assert report.trace.combined.user_notes == (MISS_LINE,)


@pytest.mark.parametrize(
    ("message", "met"),
    [
        ("The sink is subprocess.run(shell=True): CWE-78, OS command injection.", True),
        ("After tracing every source, there is no reachable chain to a sink.", True),
        ("The code is a bit messy but I could not decide.", False),
    ],
)
def test_find_injected_vulnerability_cwe_or_no_chain(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path, message: str, met: bool
) -> None:
    report = _stop(repo, deps, tmp_path, message, slash="find-injected-vulnerability")

    notes = report.trace.combined.user_notes
    assert (notes == ()) is met
    assert met or notes[0].startswith('[output-contract] "/find-injected-vulnerability": no final')


def test_golden_claude_payload(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path, hook_payload: Payload
) -> None:
    """The ``poc_review_no_verdict`` golden pins parse, the user note and wire at once."""
    golden = hook_payload("claude_code", "stop", "poc_review_no_verdict")
    payload = repo.relocate(golden)
    _activate(tmp_path, payload)

    report = stop(repo, deps, payload, git=_unchanged(), state=tmp_path)

    expected = golden.expected["result"]
    assert report.trace.combined.decision.value == expected["decision"]
    assert list(report.trace.combined.user_notes) == expected["user_notes"]
    assert report.trace.wire == golden.wire()


def test_without_the_coordinator_the_stage_reports_alone(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.install_pack([HOOK_ID], prompts=_engine_prompts())

    report = _stop(pack_repo, deps, tmp_path, REVIEW_NO_VERDICT)

    assert report.trace.combined.decision is Decision.NONE
    assert report.trace.combined.user_notes == (MISS_LINE,)


@pytest.mark.parametrize(
    ("follow_up", "expected"),
    [(None, (MISS_LINE,)), ("now fix it", ())],
    ids=["review-turn", "next-turn"],
)
def test_transcript_turn_drives_the_stage(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    tmp_path: Path,
    follow_up: str | None,
    expected: tuple[str, ...],
) -> None:
    """K6 + finding #6: a review turn with no tool call is resolved at Stop from the transcript."""
    transcript = SessionTranscript(tmp_path / "session.jsonl")
    transcript.command("review-core", "src/app.py")
    if follow_up is not None:
        transcript.typed(follow_up)
    body = json.loads(stop_payload(repo, message=REVIEW_NO_VERDICT))
    body.update(transcript.fields())

    report = stop(repo, deps, json.dumps(body).encode(), git=_unchanged(), state=tmp_path)

    assert report.trace.combined.user_notes == expected
