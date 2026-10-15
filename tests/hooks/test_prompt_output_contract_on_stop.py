"""prompt-output-contract-on-stop: the ``output-contract`` Stop stage (specs/prK-hook-pack.md §E.2).

Driven through ``playbook-hook simulate stop`` with the coordinator and this
hook on, and the engine's shipped prompts rendered into ``guard_config.prompts``.
The active-prompt record is seeded in a real state root, because K7 owns its
writer (OQ-45). A review turn changes no file, so ``FakeGit`` reports a tree
equal to ``HEAD``: only ``needs_diff=False`` stages run, and ruff never does.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

import coding_agent_playbook
from coding_agent_playbook.hook_runtime.active_prompt import ActivePrompt, active_prompt_doc
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.git import Fingerprint
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME
from coding_agent_playbook.types import Prompt
from tests.hook_runtime.fakes import FakeGit, FakeStageRunner
from tests.hooks.stop_kit import HEAD_TREE, changed_git, session_of, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase
    from tests.hooks.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

HOOK_ID: Final = "prompt-output-contract-on-stop"
GATE_ID: Final = "stop-ci-parity-gate"
PROMPTS: Final = Path(coding_agent_playbook.__file__).parent / "resources" / "prompts"
REVIEW_NO_VERDICT: Final = "Two findings:\n- src/app.py:3 shadows `os`.\n- a nit on naming."
MISS_LINE: Final = (
    '[output-contract] "/review": no final answer matches '
    "`(?im)^\\W*(verdict\\W*)?(approve with comments|approve|request changes)\\W*$`; end with it."
)


def _engine_prompts() -> list[Prompt]:
    names = ("review.md.j2", "find-injected-vulnerability.md.j2", "explain.md")
    return [Prompt.from_markdown(PROMPTS / name, "coding_agent_playbook") for name in names]


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.install_pack([GATE_ID, HOOK_ID], prompts=_engine_prompts())
    return pack_repo


def _unchanged() -> FakeGit:
    fingerprint = Fingerprint(tree_id=HEAD_TREE, aux="", mode="tree", unchanged_vs_head=True)
    return FakeGit(fingerprint_value=fingerprint, head_tree_id=HEAD_TREE)


def _activate(state: Path, payload: bytes, slash: str = "review", turn: str = "pr_17") -> None:
    """Seed the record K7's user_prompt_submit branch writes for ``/<slash>``."""
    doc = state / STATE_DIR_NAME / active_prompt_doc(session_of(payload))
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(json.dumps(ActivePrompt(slash, slash, turn).to_json()), "utf-8")


def _stop(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    message: str,
    *,
    slash: str | None = "review",
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


def test_transcript_never_opened(
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
    _activate(tmp_path / "b", payload, turn="pr_16")  # a /review of an earlier turn
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
