"""Tests for the R2 ``Judge`` ABC + ``LLMJudge``/``StubJudge`` (SPEC §15.3).

Everything is **hermetic**: the real ``claude`` CLI is never invoked in CI. The
batch wrapper + n-sample averaging are exercised through :class:`StubJudge`, and
:class:`LLMJudge`'s subprocess plumbing is proven with a *fake* command (a tiny
``python -c`` program that prints a score). The single real-CLI smoke test is
gated on both the binary being present **and** ``PLAYBOOK_E2E_CLAUDE=1``, mirroring
the ``ClaudeCodeRunner`` smoke pattern.
"""

from __future__ import annotations

import os
import shutil
import sys
from importlib import metadata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.judge import (
    Judge,
    JudgeError,
    LLMJudge,
    StubJudge,
    parse_score,
)

if TYPE_CHECKING:
    from pathlib import Path

# --------------------------------------------------------------------------- #
# Judge ABC — batch wrapper + n-sample averaging
# --------------------------------------------------------------------------- #


def test_judge_is_abstract() -> None:
    with pytest.raises(TypeError):
        Judge()  # type: ignore[abstract]


def test_default_available_is_true() -> None:
    """The base ``available()`` is always-true; real judges override it."""
    assert StubJudge.available() is True


def test_batch_score_maps_over_score_criterion() -> None:
    judge = StubJudge({"A": 0.1, "B": 0.9})
    scores = judge.score(["A", "B"], "the transcript", {})
    assert scores == [pytest.approx(0.1), pytest.approx(0.9)]


def test_batch_score_passes_transcript_as_artifact_n_one() -> None:
    judge = StubJudge()
    judge.score(["A", "B"], "TX", {})
    assert judge.calls == [("A", "TX", 1), ("B", "TX", 1)]


def test_batch_score_empty_criteria_is_empty_list() -> None:
    assert StubJudge().score([], "tx", {}) == []


def test_n_sample_averaging() -> None:
    """A judge that varies per call: ``score_criterion`` averages ``n`` samples."""

    class _Varying(Judge):
        name = "varying"

        def __init__(self) -> None:
            self._next = iter([0.0, 1.0, 0.0, 1.0])

        def score_criterion(self, criterion: str, artifact: object, n: int = 1) -> float:
            return sum(next(self._next) for _ in range(n)) / n

    judge = _Varying()
    # Mean over 4 of [0,1,0,1] == 0.5.
    assert judge.score_criterion("c", "art", n=4) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# StubJudge specifics
# --------------------------------------------------------------------------- #


def test_stub_default_is_one() -> None:
    judge = StubJudge()
    assert judge.score_criterion("anything", "art") == pytest.approx(1.0)


def test_stub_custom_default() -> None:
    judge = StubJudge(default=0.25)
    assert judge.score_criterion("unmapped", "art") == pytest.approx(0.25)


def test_stub_mapped_score_clamped() -> None:
    judge = StubJudge({"hi": 5.0, "lo": -2.0})
    assert judge.score_criterion("hi", "a") == pytest.approx(1.0)
    assert judge.score_criterion("lo", "a") == pytest.approx(0.0)


def test_stub_records_calls() -> None:
    judge = StubJudge({"c": 0.4})
    judge.score_criterion("c", "artifact", n=3)
    assert judge.calls == [("c", "artifact", 3)]


def test_stub_is_not_registered() -> None:
    """``StubJudge`` is a test helper, never an entry point."""
    names = {ep.name for ep in metadata.entry_points(group="coding_agent_playbook.judges")}
    assert "stub" not in names


# --------------------------------------------------------------------------- #
# parse_score robustness
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.8", 0.8),
        ("  0.42 \n", 0.42),
        ("Score: 0.7", 0.7),
        ("score=0.25", 0.25),
        ("**0.9**", 0.9),
        ("`0.6`", 0.6),
        ("0.8.", 0.8),
        ("**Score:** 0.8", 0.8),
        ("**Score: 0.8**", 0.8),
        ("**Score**: 0.8", 0.8),
        ("__0.8__", 0.8),
        ("0.8\r\n\n", 0.8),
        (".5", 0.5),
        ("1", 1.0),
        ("0", 0.0),
        ("1.0", 1.0),
    ],
)
def test_parse_score_accepts_a_bare_in_range_number(text: str, expected: float) -> None:
    assert parse_score(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "API Error: 529 Overloaded",  # regression: used to score 1.0 (529 clamped)
        "Error: rate limited, retry in 1s",  # one in-range number, but prose
        "Not satisfied - the answer misses step 1.",
        "the score is .9 overall",
        "1.5",  # out of range is off-format, never clamped into a score
        "-0.3",
        "0.4 or maybe 0.6",
        "8/10",
        "1e-1",
        "no number here",
        "",
    ],
)
def test_parse_score_rejects_anything_but_a_bare_number(text: str) -> None:
    """Anything but one number in ``[0, 1]`` is *no score*, not a score.

    An error message or a prose verdict that happens to carry a digit must never
    turn into a grade.
    """
    assert parse_score(text) is None


# --------------------------------------------------------------------------- #
# LLMJudge availability guard
# --------------------------------------------------------------------------- #


def test_llm_available_false_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert LLMJudge.available() is False


def test_llm_available_true_when_cli_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/claude")
    assert LLMJudge.available() is True


# --------------------------------------------------------------------------- #
# LLMJudge subprocess plumbing (fake command, no real CLI)
# --------------------------------------------------------------------------- #


def test_llm_score_criterion_parses_fake_command_stdout() -> None:
    """A fake command that prints a score is parsed + clamped to ``[0, 1]``."""
    judge = LLMJudge(command=[sys.executable, "-c", "print('0.75')"])
    assert judge.score_criterion("crit", "artifact") == pytest.approx(0.75)


def test_llm_score_criterion_averages_n_invocations() -> None:
    """``n`` invocations are averaged.

    The fake command emits a different score each run by reading + bumping a
    counter file, so two invocations average ``(0.0 + 1.0) / 2 = 0.5``.
    """
    import tempfile
    import textwrap
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        counter = Path(tmp) / "n"
        program = textwrap.dedent(
            f"""\
            import pathlib
            p = pathlib.Path({str(counter)!r})
            i = int(p.read_text()) if p.exists() else 0
            p.write_text(str(i + 1))
            print(1.0 if i % 2 else 0.0)
            """
        )
        judge = LLMJudge(command=[sys.executable, "-c", program])
        assert judge.score_criterion("crit", "artifact", n=2) == pytest.approx(0.5)


def _counting_program(counter: Path, body: str) -> str:
    """A ``python -c`` program that bumps ``counter`` then runs ``body``.

    ``body`` sees the pre-increment attempt index as ``i``.
    """
    return (
        "import pathlib, sys, time\n"
        f"p = pathlib.Path({str(counter)!r})\n"
        "i = int(p.read_text()) if p.exists() else 0\n"
        "p.write_text(str(i + 1))\n"
        f"{body}\n"
    )


def test_llm_nonzero_exit_raises_instead_of_scoring() -> None:
    """A failing CLI is a judge error, even when its output carries a number."""
    program = "import sys; print('API Error: 529 Overloaded'); sys.exit(1)"
    judge = LLMJudge(command=[sys.executable, "-c", program], retries=0)
    with pytest.raises(JudgeError, match=r"exited 1.*529 Overloaded"):
        judge.score_criterion("crit", "artifact")


def test_llm_off_format_stdout_raises() -> None:
    """Exit 0 but no single in-range number on stdout is a judge error."""
    judge = LLMJudge(command=[sys.executable, "-c", "print('API Error: 529')"], retries=0)
    with pytest.raises(JudgeError, match="off-format"):
        judge.score_criterion("crit", "artifact")


def test_llm_timeout_raises() -> None:
    program = "import time; time.sleep(10)"
    judge = LLMJudge(command=[sys.executable, "-c", program], timeout=0.2, retries=0)
    with pytest.raises(JudgeError, match="timed out"):
        judge.score_criterion("crit", "artifact")


def test_llm_retries_a_failed_attempt_then_scores(tmp_path: Path) -> None:
    """A transient failure is retried; the first good answer is the score."""
    counter = tmp_path / "n"
    body = "sys.exit(1) if i == 0 else print('0.6')"
    judge = LLMJudge(command=[sys.executable, "-c", _counting_program(counter, body)], retries=1)
    assert judge.score_criterion("crit", "artifact") == pytest.approx(0.6)
    assert counter.read_text() == "2"


def test_llm_retries_are_bounded(tmp_path: Path) -> None:
    """``retries=2`` means three attempts in total, then a :class:`JudgeError`."""
    counter = tmp_path / "n"
    judge = LLMJudge(
        command=[sys.executable, "-c", _counting_program(counter, "sys.exit(3)")], retries=2
    )
    with pytest.raises(JudgeError, match="3 attempt"):
        judge.score_criterion("crit", "artifact")
    assert counter.read_text() == "3"


def test_llm_unlaunchable_command_raises_judge_error(tmp_path: Path) -> None:
    """A command that cannot be launched (here: not executable) is a judge error.

    Covers ``OSError`` from ``subprocess.run`` — e.g. ``E2BIG`` when a huge
    artifact overflows the argv limit — which must not escape as a traceback.
    """
    not_executable = tmp_path / "judge.txt"
    not_executable.write_text("not a program", encoding="utf-8")
    judge = LLMJudge(command=[str(not_executable), "{prompt}"], retries=0)
    with pytest.raises(JudgeError, match="could not launch"):
        judge.score_criterion("crit", "artifact")


def test_parse_score_is_fast_on_a_long_degenerate_answer() -> None:
    """A huge whitespace run after a ``Score`` label must not backtrack quadratically."""
    import time

    started = time.monotonic()
    assert parse_score("Score" + "\n" * 200_000 + "N/A") is None
    assert parse_score("Score:" + " " * 200_000 + "0.5x") is None
    assert time.monotonic() - started < 1.0


def test_llm_undecodable_output_raises_judge_error() -> None:
    """Bytes that are not UTF-8 are off-format, not a ``UnicodeDecodeError`` crash."""
    program = "import sys; sys.stdout.buffer.write(b'\\xff\\xfe0.9')"
    judge = LLMJudge(command=[sys.executable, "-c", program], retries=0)
    with pytest.raises(JudgeError, match="off-format"):
        judge.score_criterion("crit", "artifact")


def test_llm_nul_byte_in_artifact_raises_judge_error() -> None:
    """A NUL in the artifact cannot go on argv; it is a judge error, not a ValueError."""
    judge = LLMJudge(command=[sys.executable, "-c", "print('0.5')", "{prompt}"], retries=0)
    with pytest.raises(JudgeError, match="NUL byte"):
        judge.score_criterion("crit", "before\x00after")


def test_llm_rejects_an_empty_command() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        LLMJudge(command=[])


def test_llm_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="retries"):
        LLMJudge(retries=-1)


def test_llm_default_command_targets_claude_print_mode() -> None:
    judge = LLMJudge()
    cmd = judge._build_command("the grading prompt")
    assert cmd[0] == "claude"
    assert "the grading prompt" in cmd


def test_llm_build_command_appends_prompt_when_no_token() -> None:
    judge = LLMJudge(command=["mytool", "--grade"])
    assert judge._build_command("PROMPT") == ["mytool", "--grade", "PROMPT"]


def test_llm_grading_prompt_embeds_criterion_and_artifact() -> None:
    """The prompt handed to the CLI embeds both the criterion and the artifact."""
    seen: dict[str, str] = {}

    program = (
        "import sys; "
        "open(sys.argv[2], 'w').write(sys.argv[1]); "  # write prompt to a file
        "print('0.5')"
    )
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        promptfile = Path(tmp) / "prompt.txt"
        judge = LLMJudge(command=[sys.executable, "-c", program, "{prompt}", str(promptfile)])
        judge.score_criterion("CRITERION-XYZ", "ARTIFACT-ABC")
        seen["prompt"] = promptfile.read_text(encoding="utf-8")

    assert "CRITERION-XYZ" in seen["prompt"]
    assert "ARTIFACT-ABC" in seen["prompt"]


# --------------------------------------------------------------------------- #
# Registry / discovery
# --------------------------------------------------------------------------- #


def test_llm_judge_is_registered_via_entry_point() -> None:
    eps = metadata.entry_points(group="coding_agent_playbook.judges")
    by_name = {ep.name: ep for ep in eps}
    assert "llm" in by_name
    loaded = by_name["llm"].load()
    assert loaded is LLMJudge
    assert loaded.name == "llm"


# --------------------------------------------------------------------------- #
# Real-CLI smoke test — NEVER runs in CI
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (shutil.which("claude") and os.environ.get("PLAYBOOK_E2E_CLAUDE") == "1"),
    reason="real claude CLI smoke test: needs the CLI on PATH and PLAYBOOK_E2E_CLAUDE=1",
)
def test_real_claude_judge_smoke() -> None:  # pragma: no cover - opt-in only
    judge = LLMJudge()
    score = judge.score_criterion(
        "The artifact mentions the word banana",
        "Here is a recipe that uses a banana and some flour.",
    )
    assert 0.0 <= score <= 1.0


def test_llm_judge_model_reaches_the_cli_unchanged() -> None:
    """``[evals.judge] model`` is passed as ``--model <model>`` (spec #281 ticket 05)."""
    grade_on_model = "import sys; print(1 if sys.argv[-2:] == ['--model', 'org/j:v2'] else 0)"
    judge = LLMJudge(command=[sys.executable, "-c", grade_on_model, "{prompt}"], model="org/j:v2")
    assert judge.score_criterion("criterion", "artifact") == 1.0
    assert "--model" not in LLMJudge()._build_command("p")
