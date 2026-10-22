# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The production evaluation Job: score each production trace once, out of band.

Run it as a scheduled Domino Job set to run sequentially. It fixes the window end
when it starts (aware UTC now), starts ``trace_overlap_seconds`` before the stored
watermark (or a configured lookback on the first run), pages through every trace
of the request span until no page token comes back, skips traces that already hold
this Job's metrics, logs the reference-free scores back to each trace, and only
then writes the window end to the watermark file atomically. A rerun after a crash
scores nothing twice. The overlap must be at least the agent config's run
deadline (agent.timeout_seconds), or a request still running at a window's end
could finish outside both windows; the Job refuses to start otherwise.

    python -m evals.prod_eval --agent-id <id> --agent-version <version>
"""

import argparse
import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.logs import configure_logging
from app.settings import AgentSettings, RunConfig, load_agent_config
from app.tracing import REQUEST_SPAN_NAME
from evals.evaluators import PRODUCTION_METRICS, score_answer
from evals.trace_store import DominoTraceStore, TracePage, TraceQuery, TraceStore

logger = logging.getLogger(__name__)

_WATERMARK_KEY = "window_end"


@dataclass(frozen=True)
class ProdEvalConfig:
    """Which agent to score, and how far back to look."""

    agent_id: str
    agent_version: str | None
    lookback: timedelta
    overlap: timedelta


class ProdEvalSetupError(ValueError):
    """The flags and settings do not describe a runnable Job; says what to set."""


class WatermarkError(RuntimeError):
    """The watermark file exists but cannot be read; names the path."""


class WatermarkFile:
    """The end of the last fully scored window, as JSON on a dataset path."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> datetime | None:
        """The stored window end; None when the file does not exist yet (a first run)."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            value = datetime.fromisoformat(json.loads(text)[_WATERMARK_KEY])
        except (ValueError, TypeError, KeyError) as exc:
            raise WatermarkError(f"corrupt watermark file {self.path}: {exc}") from exc
        if value.tzinfo is None:
            raise WatermarkError(f"corrupt watermark file {self.path}: the time has no timezone")
        return value

    def write(self, value: datetime) -> None:
        """Replace the file atomically: a temp file in the same directory, then os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({_WATERMARK_KEY: value.isoformat()})
        handle, temp_name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temp:
                temp.write(payload)
            os.replace(temp_name, self.path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise


def score_page(store: TraceStore, page: TracePage) -> int:
    """Log the scores of every trace on ``page`` not scored before; return how many."""
    unscored = [t for t in page.traces if not PRODUCTION_METRICS.issubset(t.evaluation_names)]
    for trace in unscored:
        for name, value in score_answer(trace.answer, trace.tools).items():
            store.log_evaluation(trace.trace_id, name, value)
    return len(unscored)


def score_new_traces(
    store: TraceStore, watermark: WatermarkFile, config: ProdEvalConfig, *, now: datetime
) -> int:
    """Score the window from the watermark (minus the overlap) to ``now``; then advance it."""
    start = (watermark.read() or now - config.lookback) - config.overlap
    query = TraceQuery(config.agent_id, config.agent_version, REQUEST_SPAN_NAME, start, now)
    scored = 0
    page_token: str | None = None
    while True:
        page = store.search(query, page_token)
        scored += score_page(store, page)
        page_token = page.page_token
        if page_token is None:
            break
    watermark.write(now)
    return scored


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_config(
    args: argparse.Namespace, settings: AgentSettings, run: RunConfig
) -> ProdEvalConfig:
    """The Job's config: flags win over settings, and the overlap covers the run deadline."""
    agent_id = args.agent_id or settings.agent_id
    if not agent_id:
        raise ProdEvalSetupError("set --agent-id or SIMPLE_AGENT_AGENT_ID")
    if settings.trace_overlap_seconds < run.timeout_seconds:
        raise ProdEvalSetupError(
            f"SIMPLE_AGENT_TRACE_OVERLAP_SECONDS ({settings.trace_overlap_seconds:g}) must be at"
            f" least the run deadline agent.timeout_seconds ({run.timeout_seconds:g})"
        )
    return ProdEvalConfig(
        agent_id=agent_id,
        agent_version=args.agent_version or settings.agent_version,
        lookback=timedelta(hours=settings.lookback_hours),
        overlap=timedelta(seconds=settings.trace_overlap_seconds),
    )


def resolve_watermark(args: argparse.Namespace, settings: AgentSettings) -> WatermarkFile:
    """The watermark file from --watermark or settings; a dataset path is required."""
    path: Path | None = args.watermark or settings.watermark_path
    if path is None:
        raise ProdEvalSetupError("set --watermark or SIMPLE_AGENT_WATERMARK_PATH (a dataset path)")
    return WatermarkFile(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score the agent's new production traces.")
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--agent-version", default=None)
    parser.add_argument("--watermark", type=Path, default=None)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: AgentSettings | None = None,
    store: TraceStore | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> int:
    """Score new production traces; agent id, version and watermark come from settings or flags."""
    parser = _parser()
    args = parser.parse_args(argv)
    settings = settings or AgentSettings()
    configure_logging(settings.log_level)
    try:
        config = resolve_config(args, settings, load_agent_config(settings.config_path).agent)
        watermark = resolve_watermark(args, settings)
    except ProdEvalSetupError as exc:
        parser.error(str(exc))
    scored = score_new_traces(store or DominoTraceStore(), watermark, config, now=clock())
    logger.info("scored production traces", extra={"scored": scored, "agent_id": config.agent_id})
    return 0


if __name__ == "__main__":
    sys.exit(main())
