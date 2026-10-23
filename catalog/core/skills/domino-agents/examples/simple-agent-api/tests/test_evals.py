"""The evaluators and both evaluation Jobs, on fake spans, a fake trace store and a scripted model."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals import dev_eval, prod_eval
from evals.evaluators import (
    ANSWER_CHARS,
    ANSWERED,
    PRODUCTION_METRICS,
    SINGLE_TOOL,
    TOOL_MATCH,
    dev_span_evaluator,
)
from evals.prod_eval import ProdEvalConfig, WatermarkError, WatermarkFile, score_new_traces
from evals.trace_store import (
    DominoTraceStore,
    TracePage,
    TraceQuery,
    TraceRecord,
    TraceStoreError,
)
from tests.fakes import (
    FakeDominoSdk,
    FakeSpan,
    FakeTraceStore,
    RecordingTracer,
    latest_prompt,
    make_settings,
    scripted_model,
    scripted_response,
    sdk_trace,
)

NOW = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
CONFIG = ProdEvalConfig(
    agent_id="agent-1",
    agent_version="7",
    lookback=timedelta(hours=24),
    overlap=timedelta(minutes=5),
)


def trace(trace_id: str, answer: str = "A line.") -> TraceRecord:
    return TraceRecord(trace_id, answer, ("philosophy_line",), frozenset())


@pytest.mark.parametrize(
    ("outputs", "expected_tool", "scores"),
    [
        (
            {"answer": "A line.", "tools": ["science_line"]},
            "science_line",
            {ANSWERED: 1.0, SINGLE_TOOL: 1.0, ANSWER_CHARS: 7.0, TOOL_MATCH: 1.0},
        ),
        (
            {"answer": "A line.", "tools": ["philosophy_line"]},
            "science_line",
            {ANSWERED: 1.0, SINGLE_TOOL: 1.0, ANSWER_CHARS: 7.0, TOOL_MATCH: 0.0},
        ),
        (
            {"answer": "A line.", "tools": []},
            "science_line",
            {ANSWERED: 1.0, SINGLE_TOOL: 0.0, ANSWER_CHARS: 7.0, TOOL_MATCH: 0.0},
        ),
        (
            {"answer": "  ", "tools": ["science_line"]},
            "science_line",
            {ANSWERED: 0.0, SINGLE_TOOL: 1.0, ANSWER_CHARS: 2.0, TOOL_MATCH: 1.0},
        ),
    ],
    ids=["right-tool", "wrong-tool", "no-tool", "empty-answer"],
)
def test_dev_span_evaluator_scores_a_case(
    outputs: dict[str, object], expected_tool: str, scores: dict[str, float]
) -> None:
    span = FakeSpan(inputs={"question": "q", "expected_tool": expected_tool}, outputs=outputs)

    assert dev_span_evaluator(span) == scores


def test_prod_eval_scores_every_trace_on_every_page_once(tmp_path: Path) -> None:
    store = FakeTraceStore(pages=[[trace("t1"), trace("t2")], [trace("t3")]])

    scored = score_new_traces(store, WatermarkFile(tmp_path / "wm.json"), CONFIG, now=NOW)

    assert scored == 3
    assert store.scored_ids() == ["t1", "t2", "t3"]
    assert {name for _, name, _ in store.logged} == PRODUCTION_METRICS


def test_prod_eval_passes_the_agent_and_the_window_to_the_store(tmp_path: Path) -> None:
    store = FakeTraceStore(pages=[[trace("t1")]])

    score_new_traces(store, WatermarkFile(tmp_path / "wm.json"), CONFIG, now=NOW)

    [query] = store.queries
    assert (query.agent_id, query.agent_version, query.trace_name) == ("agent-1", "7", "ask_agent")
    assert query.start == NOW - timedelta(hours=24, minutes=5)
    assert query.end == NOW


def test_a_failed_page_keeps_the_watermark_and_the_rerun_scores_the_rest(tmp_path: Path) -> None:
    store = FakeTraceStore(pages=[[trace("t1")], [trace("t2")]], fail_on_page=1)
    watermark = WatermarkFile(tmp_path / "wm.json")

    with pytest.raises(TraceStoreError):
        score_new_traces(store, watermark, CONFIG, now=NOW)
    assert watermark.read() is None
    store.fail_on_page = None
    score_new_traces(store, watermark, CONFIG, now=NOW)

    assert store.scored_ids() == ["t1", "t2"]
    assert watermark.read() == NOW


def test_a_late_trace_inside_the_overlap_is_scored_exactly_once(tmp_path: Path) -> None:
    store = FakeTraceStore(pages=[[trace("t1")]])
    watermark = WatermarkFile(tmp_path / "wm.json")
    score_new_traces(store, watermark, CONFIG, now=NOW)
    # t2 ended just before NOW but became searchable after the first run; the
    # second window starts the overlap before NOW, so it sees t1 again and t2.
    store.pages = [[*store.pages[0], trace("t2")]]

    later = NOW + timedelta(hours=1)
    score_new_traces(store, watermark, CONFIG, now=later)

    assert store.scored_ids() == ["t1", "t2"]
    assert store.queries[-1].start == NOW - CONFIG.overlap


def test_a_corrupt_watermark_fails_naming_its_path(tmp_path: Path) -> None:
    path = tmp_path / "wm.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(WatermarkError, match=re.escape(str(path))):
        score_new_traces(FakeTraceStore(pages=[[]]), WatermarkFile(path), CONFIG, now=NOW)


def _questions(tmp_path: Path, *questions: str) -> Path:
    path = tmp_path / "questions.csv"
    rows = [f"{index},{question},philosophy_line" for index, question in enumerate(questions)]
    path.write_text(
        "\n".join(["question_id,question,expected_tool", *rows]) + "\n", encoding="utf-8"
    )
    return path


def _failing_on(word: str) -> FunctionModel:
    """The scripted model, except that a question containing ``word`` fails."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if word in latest_prompt(messages):
            raise ModelHTTPError(status_code=500, model_name="chat-model")
        return scripted_response(messages)

    return FunctionModel(respond)


def test_dev_eval_exits_0_and_scores_every_case_inside_one_run(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    settings = make_settings()

    code = dev_eval.main(
        [str(_questions(tmp_path, "Why?", "What is virtue?"))],
        settings=settings,
        model=scripted_model(),
        tracer=tracer,
    )

    assert code == 0
    assert tracer.evaluation_runs == [(settings.config_path, settings.experiment_name)]
    cases = [span for span in tracer.spans if span.name == dev_eval.CASE_SPAN_NAME]
    assert [span.evaluation and span.evaluation[TOOL_MATCH] for span in cases] == [1.0, 1.0]
    assert len(tracer.inputs("ask_agent")) == 2


def test_dev_eval_exits_1_when_one_case_raises(tmp_path: Path) -> None:
    tracer = RecordingTracer()

    code = dev_eval.main(
        [str(_questions(tmp_path, "Why?", "boom", "What is virtue?"))],
        settings=make_settings(),
        model=_failing_on("boom"),
        tracer=tracer,
    )

    assert code == 1
    assert len([s for s in tracer.spans if s.name == dev_eval.CASE_SPAN_NAME]) == 2


def test_the_shipped_questions_carry_a_label_per_case() -> None:
    cases = dev_eval.read_cases(Path(__file__).resolve().parents[1] / "sample_questions.csv")

    assert len(cases) >= 20
    assert {case.expected_tool for case in cases} == {"science_line", "philosophy_line"}


def test_the_domino_trace_store_scores_the_request_span_and_skips_a_trace_without_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sdk = FakeDominoSdk(
        traces=[
            sdk_trace(
                "t1",
                {
                    "dev_eval_case": {},
                    "ask_agent": {"answer": "A line.", "tools": ["science_line"]},
                },
                evaluations=("answered",),
            ),
            sdk_trace("t2", {"other_span": {"answer": "x"}}),
        ],
        page_token="next",
    )
    sdk.install(monkeypatch)
    query = TraceQuery("agent-1", "7", "ask_agent", NOW - timedelta(hours=1), NOW)

    page = DominoTraceStore().search(query, None)

    assert page == TracePage(
        (TraceRecord("t1", "A line.", ("science_line",), frozenset({"answered"})),), "next"
    )
    [search] = sdk.searches
    assert (search["agent_id"], search["trace_name"], search["page_token"]) == (
        "agent-1",
        "ask_agent",
        None,
    )
    warnings = [r.getMessage() for r in caplog.records if r.name == "evals.trace_store"]
    assert warnings == ["trace has no request span"]


def test_the_domino_trace_store_logs_an_evaluation_by_trace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = FakeDominoSdk()
    sdk.install(monkeypatch)

    DominoTraceStore().log_evaluation("t1", ANSWERED, 1.0)

    assert sdk.logged == [{"trace_id": "t1", "name": ANSWERED, "value": 1.0}]


def test_an_sdk_failure_leaves_the_trace_store_as_its_own_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeDominoSdk(error=ConnectionError("tracking server down")).install(monkeypatch)
    store = DominoTraceStore()
    query = TraceQuery("agent-1", None, "ask_agent", NOW - timedelta(hours=1), NOW)

    with pytest.raises(TraceStoreError, match="agent-1"):
        store.search(query, None)
    with pytest.raises(TraceStoreError, match="t1"):
        store.log_evaluation("t1", ANSWERED, 1.0)


def test_prod_eval_main_scores_with_flags_over_settings_and_advances_the_watermark(
    tmp_path: Path,
) -> None:
    store = FakeTraceStore(pages=[[trace("t1")]])
    watermark = tmp_path / "wm.json"
    settings = make_settings(agent_id="from-settings", agent_version="3")

    code = prod_eval.main(
        ["--agent-id", "agent-1", "--watermark", str(watermark)],
        settings=settings,
        store=store,
        clock=lambda: NOW,
    )

    assert code == 0
    [query] = store.queries
    assert (query.agent_id, query.agent_version) == ("agent-1", "3")
    assert store.scored_ids() == ["t1"]
    assert WatermarkFile(watermark).read() == NOW


@pytest.mark.parametrize(
    ("argv", "overlap_seconds", "message"),
    [
        (["--watermark", "wm.json"], 300.0, "--agent-id or SIMPLE_AGENT_AGENT_ID"),
        (["--agent-id", "agent-1"], 300.0, "--watermark or SIMPLE_AGENT_WATERMARK_PATH"),
        (
            ["--agent-id", "agent-1", "--watermark", "wm.json"],
            60.0,
            "SIMPLE_AGENT_TRACE_OVERLAP_SECONDS (60) must be at least the run deadline",
        ),
    ],
    ids=["no-agent-id", "no-watermark", "overlap-below-the-deadline"],
)
def test_prod_eval_main_refuses_to_start_naming_what_to_set(
    argv: list[str],
    overlap_seconds: float,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = FakeTraceStore(pages=[[trace("t1")]])

    with pytest.raises(SystemExit) as exited:
        prod_eval.main(
            argv,
            settings=make_settings(trace_overlap_seconds=overlap_seconds),
            store=store,
            clock=lambda: NOW,
        )

    assert exited.value.code == 2
    assert message in capsys.readouterr().err
    assert store.queries == []


def test_the_domino_trace_store_reads_the_sdk() -> None:
    """The real adapter's one thin check; it needs the SDK, which CI does not install."""
    pytest.importorskip("domino.agents.tracing", reason="the Domino agent SDK is not installed")
    from domino.agents.tracing import search_agent_traces

    assert callable(search_agent_traces)
