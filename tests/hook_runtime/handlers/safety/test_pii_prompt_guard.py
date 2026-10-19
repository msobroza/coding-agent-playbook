"""pii-prompt-guard: checksum-validated PII blocks a prompt (specs/prK-hook-pack.md §E.5).

The engine ships the guard inert (``tier: overlay``); every behavior test
activates it through the regulated fixture overlay (``tier: default``,
``on_error: deny``, the §E.5 config), layered over the engine definition by
the real §A.6 merge. Each prompt is a real ``playbook-hook simulate
user_prompt_submit`` whose decision, reason and Claude wire output match the
golden payload files.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Final, cast

import pytest

from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.handlers.safety import pii_prompt_guard as guard
from coding_agent_playbook.hook_runtime.harness.wire import WireOutput
from coding_agent_playbook.hooks.contract.handler_catalog import RegistryCatalog
from coding_agent_playbook.hooks.resolution.effective import resolve_effective_hooks
from coding_agent_playbook.security.pii import PiiConfig, scan_pii
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.handlers.pack_repo import engine_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from coding_agent_playbook.security.pii import PiiMatch
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "pii-prompt-guard"
IBAN: Final = "FR76 3000 6000 0112 3456 7890 189"
#: The overlay's ``max_prompt_bytes`` and the shipped ``timeout`` (seconds).
CAP_BYTES: Final = 1024 * 1024
TIMEOUT_S: Final = 5
UPS: Final = EventName.USER_PROMPT_SUBMIT


@pytest.fixture
def repo(pack_repo: PackRepo, regulated_overlay: str) -> PackRepo:
    pack_repo.install_pack([HOOK_ID], overlays=(regulated_overlay,))
    return pack_repo


def _golden(repo: PackRepo, deps: Deps, case: str, state: Path) -> SimulateReport:
    """Simulate golden ``case``; its decision, reason and wire output must match."""
    golden = load_hook_payload("claude_code", "user_prompt_submit", case)
    report = repo.simulate(repo.relocate(golden), deps(), event=UPS, state=state)
    expected = golden.expected["result"]
    combined = report.trace.combined
    assert (combined.decision.value, combined.reason) == (
        expected["decision"],
        expected.get("reason", ""),
    )
    assert report.trace.wire == golden.wire()
    return report


def _prompt(repo: PackRepo, deps: Deps, prompt: str, state: Path) -> SimulateReport:
    payload = repo.payload(UPS, prompt=prompt, prompt_id="pr_99")
    return repo.simulate(payload, deps(), event=UPS, state=state)


def _guard_lines(state: Path) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for path in sorted(state.rglob("decisions-*.jsonl")):
        lines.extend(json.loads(line) for line in path.read_text("ascii").splitlines())
    return [line for line in lines if line["hook_id"] == HOOK_ID]


def _log_text(state: Path) -> str:
    return "".join(path.read_text("ascii") for path in state.rglob("decisions-*.jsonl"))


def test_valid_example_iban_blocks_with_masked_reason(
    repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    state = tmp_path / "state"

    report = _golden(repo, deps, "pii_iban", state)

    reason = report.trace.combined.reason
    assert "iban at offset 24: FR** **** **** **** **** **** *89" in reason
    assert IBAN not in reason and IBAN.replace(" ", "") not in reason
    assert report.trace.wire.exit_code == 0  # a block on exit 0, shown to the user
    (line,) = _guard_lines(state)
    assert (line["decision"], line["rule_id"], line["escape"]) == ("deny", "iban", None)
    assert "3000" not in _log_text(state)


def test_sixteen_digits_failing_luhn_pass(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    _golden(repo, deps, "pii_random_digits", tmp_path / "state")


def test_test_card_4111_passes(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    _golden(repo, deps, "pii_test_card", tmp_path / "state")


def test_overlay_extra_detector_row_blocks(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    """The overlay's data row (regex + named ``mod97`` checksum) is a detector like the rest."""
    report = _prompt(repo, deps, "Customer CUST-1197530767 complained", tmp_path / "state")

    assert report.trace.combined.decision is Decision.DENY
    assert "bank_customer_id at offset 14: ********67" in report.trace.combined.reason
    assert "1197530767" not in report.trace.combined.reason


def test_override_token_logged_by_category_only(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    state = tmp_path / "state"

    _golden(repo, deps, "pii_override", state)

    (line,) = _guard_lines(state)
    assert (line["decision"], line["effective"], line["rule_id"], line["escape"]) == (
        "escape",
        "none",
        "iban",
        "override_token",
    )
    raw = _log_text(state)
    for leaked in ("#pii-ok", "3000", "Refund", "agreed"):
        assert leaked not in raw  # no token, value or prompt text


def test_ten_mb_paste_chunked_within_budget(
    repo: PackRepo, deps: Deps, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the capped head is scanned, in chunks; the unchecked rest fails closed."""
    scanned: list[int] = []

    def spy(text: str, cfg: PiiConfig) -> list[PiiMatch]:
        scanned.append(len(text))
        return scan_pii(text, cfg)

    monkeypatch.setattr(f"{guard.__name__}.scan_pii", spy)
    paste = ("2024-01-02 order 1234 5678 9012 3456 total 99.95\n" * 220_000)[: 10 * 1024 * 1024]

    started = time.perf_counter()
    report = _prompt(repo, deps, paste, tmp_path / "state")
    elapsed = time.perf_counter() - started

    assert scanned == [CAP_BYTES]  # one capped head, which scan_pii reads in 16 chunks
    assert elapsed < TIMEOUT_S
    combined = report.trace.combined
    assert combined.decision is Decision.DENY
    assert combined.reason.startswith(
        f"Prompt not sent: it is {len(paste)} bytes, over the PII guard's {CAP_BYTES}-byte limit"
    )


def test_hit_in_an_oversize_paste_is_listed_with_the_partial_note(
    repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    paste = f"pay {IBAN}\n" + "x" * (2 * CAP_BYTES)

    report = _prompt(repo, deps, paste, tmp_path / "state")

    reason = report.trace.combined.reason
    assert "iban at offset 4: " in reason
    assert f"Only the first {CAP_BYTES} bytes were checked." in reason
    assert report.trace.combined.outcomes[0].rule_id == "iban,oversize"


def test_head_is_cut_on_a_character_boundary() -> None:
    """A multi-byte character straddling the cap is left out whole, so offsets stay exact."""
    scan = guard.scan_prompt("é" * 10, PiiConfig(), max_bytes=5)

    assert (scan.size, scan.oversize, scan.matches) == (20, True, ())


def test_internal_error_renders_block_json_on_exit_0(
    pack_repo: PackRepo, regulated_overlay: str, deps: Deps, tmp_path: Path
) -> None:
    """A broken overlay row is an internal error: fail closed with the guard's own reason."""
    broken = [{"name": "acct", "pattern": "ACCT-[0-9]{6}", "checksum": "crc32"}]
    pack_repo.install_pack(
        [HOOK_ID],
        overlays=(regulated_overlay,),
        handler_config={HOOK_ID: {"extra_detectors": broken}},
    )
    state = tmp_path / "state"

    report = _prompt(pack_repo, deps, "hello", state)

    assert report.trace.wire == WireOutput(
        '{"decision":"block","reason":"PII guard error; resubmit or use the override"}\n', "", 0
    )
    (line,) = _guard_lines(state)
    assert (line["decision"], line["effective"], line["degraded"]) == ("degraded", "deny", True)


def test_engine_default_definition_is_not_rendered(tmp_path: Path) -> None:
    """Shipped inert: no tier or enable list switches it on without an overlay (K-11)."""
    hooks_cfg = HooksConfig(enabled=True, tiers=("default", "opt-in"), enable=(HOOK_ID,))

    view = resolve_effective_hooks(
        [engine_hook(HOOK_ID)],
        [],
        hooks_cfg,
        GuardrailsConfig(),
        cast("Facts", {}),
        tmp_path,
        adapters_enabled=["claude_code"],
        handlers=RegistryCatalog(),
    )

    assert view.resolved == []
    assert [skipped.id for skipped in view.skipped] == [HOOK_ID]
    fm = engine_hook(HOOK_ID).frontmatter
    assert (fm.tier, fm.enabled, fm.on_error, fm.handler_for("user_prompt_submit").config) == (
        "overlay",
        True,
        "open",
        {
            "detectors": [],
            "extra_detectors": [],
            "test_value_allowlist": [],
            "override_token": "",
            "max_prompt_bytes": CAP_BYTES,
        },
    )
