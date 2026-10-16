"""``PLAYBOOK_HOOK_WRAPPER_PREFIXES``: a per-developer wrapper declaration (specs/prK-lifecycle-hooks.md §D.7, §B.1).

A developer whose commands run through a launcher of their own (``proxy``)
declares it in the shell that launches the agent: committed config cannot
carry it for one developer, and ``.local.toml`` never holds ``[hooks]``
(OQ-2). Like the escape hatches it is read only from the hook process
environment, never from a command's ``VAR=x`` prefix, and ignored when a
settings-file ``env`` sets it. Accepted prefixes join ``[hooks]
wrapper_prefixes`` in ``guard_config.shell`` for the dispatch, so the guards
and verify-run tagging both see the launched command; an entry that would
hide a guarded command is dropped and logged. Driven through ``playbook-hook
simulate`` against repos whose committed config declares no wrapper.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.escape import WRAPPER_PREFIXES_VAR
from coding_agent_playbook.hook_runtime.event import EventName
from tests.hook_runtime.fakes import FakeGit
from tests.hooks.stop_kit import changed_git, py_edit, seed_ledger, session_of, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.content

GUARD: Final = "destructive-command-guard"
GATE: Final = "stop-ci-parity-gate"
FORCE_PUSH: Final = "git push --force origin main"


@pytest.fixture
def guarded(pack_repo: PackRepo) -> PackRepo:
    pack_repo.install_pack([GUARD])  # no [hooks] wrapper_prefixes
    return pack_repo


def _bash(
    repo: PackRepo,
    deps: Deps,
    command: str,
    env: Mapping[str, str] | None = None,
    state: Path | None = None,
) -> SimulateReport:
    git = FakeGit(
        symbolic_refs={"HEAD": "feat/x"},
        default_branch_name="origin/main",
        upstream_ref="refs/remotes/origin/feat/x",
    )
    payload = repo.tool_payload("Bash", {"command": command})
    return repo.simulate(payload, deps(git=git), env=env, state=state)


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


def _log(state: Path) -> list[dict[str, Any]]:
    paths = sorted(state.rglob("decisions-*.jsonl"))
    return [json.loads(line) for path in paths for line in path.read_text("utf-8").splitlines()]


def test_a_declared_wrapper_reaches_every_guard(guarded: PackRepo, deps: Deps) -> None:
    command = f"proxy {FORCE_PUSH}"

    undeclared = _bash(guarded, deps, command)
    declared = _bash(guarded, deps, command, env={WRAPPER_PREFIXES_VAR: "proxy"})

    assert _decision(undeclared) is Decision.NONE  # `proxy` is all a guard could see
    assert _decision(declared) is Decision.DENY


def test_a_multi_word_wrapper_is_stripped_longest_first(guarded: PackRepo, deps: Deps) -> None:
    report = _bash(
        guarded, deps, "proxy run rm -rf /", env={WRAPPER_PREFIXES_VAR: "proxy,proxy run"}
    )

    assert _decision(report) is Decision.DENY


def test_a_wrapper_hiding_a_guarded_command_is_dropped_and_logged(
    guarded: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    env = {WRAPPER_PREFIXES_VAR: "git,proxy"}

    first = _bash(guarded, deps, FORCE_PUSH, env=env, state=state)
    second = _bash(guarded, deps, f"proxy {FORCE_PUSH}", env=env, state=state)

    assert _decision(first) is Decision.DENY  # `git` was never stripped
    assert _decision(second) is Decision.DENY  # `proxy` still was
    escapes = [
        (line["rule_id"], line["escape"]) for line in _log(state) if line["decision"] == "escape"
    ]
    assert escapes == [
        (None, WRAPPER_PREFIXES_VAR),
        (WRAPPER_PREFIXES_VAR, "wrapper_prefix_rejected"),
    ]  # once per session each, and never the declared value


def test_a_command_env_prefix_never_declares_a_wrapper(guarded: PackRepo, deps: Deps) -> None:
    report = _bash(guarded, deps, f"{WRAPPER_PREFIXES_VAR}=proxy proxy {FORCE_PUSH}")

    assert _decision(report) is Decision.NONE


def test_a_wrapper_set_in_a_settings_env_is_ignored(
    guarded: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    settings = guarded.root / ".claude" / "settings.local.json"
    settings.parent.mkdir(exist_ok=True)
    settings.write_text(json.dumps({"env": {WRAPPER_PREFIXES_VAR: "proxy"}}), encoding="utf-8")
    state = tmp_path / "state"

    report = _bash(
        guarded, deps, f"proxy {FORCE_PUSH}", env={WRAPPER_PREFIXES_VAR: "proxy"}, state=state
    )

    assert _decision(report) is Decision.NONE
    assert [line["escape"] for line in _log(state)] == ["escape_via_settings_env"]


def test_a_test_run_behind_a_declared_wrapper_satisfies_verify_claim(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    """Regression (review finding #3): verify-claim blocked a green ``proxy uv run pytest``."""
    pack_repo.install_pack([GATE], detect=DetectInputs(facts={"dev_tools": {"pytest"}}))
    payload = stop_payload(pack_repo)
    session = session_of(payload)

    def after_run(env: Mapping[str, str], state: Path) -> Decision:
        seed_ledger(state, session, py_edit("src/x.py"))
        ran = pack_repo.tool_payload(
            "Bash",
            {"command": "proxy uv run pytest -q tests"},
            event=EventName.POST_TOOL_USE,
            session_id=session,
        )
        pack_repo.simulate(ran, deps(), env=env, event=EventName.POST_TOOL_USE, state=state)
        return stop(
            pack_repo, deps, payload, git=changed_git(), state=state
        ).trace.combined.decision

    assert after_run({}, tmp_path / "plain") is Decision.DENY
    assert after_run({WRAPPER_PREFIXES_VAR: "proxy"}, tmp_path / "declared") is Decision.NONE
