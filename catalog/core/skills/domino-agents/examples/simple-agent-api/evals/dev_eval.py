# Changed from Domino Data Lab's simple_agent_api_only example (Apache-2.0); see README.md.
"""The development evaluation Job: every labelled question through the agent, in one DominoRun.

Run it as a Domino Job from the project root, so the run carries the commit, the
agent config, the traces and the summary metrics, and Deploy Agent can deploy it:

    python -m evals.dev_eval sample_questions.csv --max-rows 10

The agent is built by the App's own builders. Each case runs through the traced
run_case, whose evaluator scores it, and which calls the same traced request
function the App serves. Cases run one after another. A case that raises is logged
with its id and counted, and the Job exits 1 when any case failed.
"""

import argparse
import asyncio
import csv
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic_ai.models import Model

from app.agent import AgentAnswer, AskAgent
from app.logs import configure_logging
from app.main import build_runtime
from app.settings import AgentSettings
from app.tracing import REQUEST_SPAN_NAME, Tracer, select_tracer
from evals.evaluators import dev_span_evaluator

logger = logging.getLogger(__name__)

#: The span name of one evaluation case; the request span nests under it.
CASE_SPAN_NAME: Final = "dev_eval_case"

CaseRunner = Callable[[str, str, str], Awaitable[AgentAnswer]]


@dataclass(frozen=True)
class Case:
    """One labelled question of the evaluation file."""

    case_id: str
    question: str
    expected_tool: str


def read_cases(path: Path, max_rows: int | None = None) -> list[Case]:
    """The cases of a CSV file with question_id, question and expected_tool columns.

    Lines starting with ``#`` are comments.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(line for line in handle if not line.startswith("#"))
        cases = [Case(row["question_id"], row["question"], row["expected_tool"]) for row in rows]
    return cases if max_rows is None else cases[:max_rows]


def make_run_case(ask: AskAgent) -> CaseRunner:
    """The case function: its parameters are the span inputs dev_span_evaluator reads."""

    async def run_case(question_id: str, question: str, expected_tool: str) -> AgentAnswer:
        return await ask(question)

    return run_case


async def run_cases(run_case: CaseRunner, cases: Sequence[Case]) -> int:
    """Run each case in turn; return how many raised."""
    failed = 0
    for case in cases:
        try:
            await run_case(case.case_id, case.question, case.expected_tool)
        except Exception:
            logger.exception("evaluation case failed", extra={"case_id": case.case_id})
            failed += 1
    return failed


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: AgentSettings | None = None,
    model: Model | None = None,
    tracer: Tracer | None = None,
) -> int:
    """Evaluate the agent on the question file; 1 when any case failed, else 0."""
    parser = argparse.ArgumentParser(description="Development evaluation of the agent.")
    parser.add_argument("questions", type=Path)
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args(argv)

    settings = settings or AgentSettings()
    configure_logging(settings.log_level)
    tracer = tracer or select_tracer(settings)
    cases = read_cases(args.questions, args.max_rows)
    runtime = build_runtime(settings, model=model)
    ask = tracer.trace(REQUEST_SPAN_NAME)(runtime.ask)
    run_case = tracer.trace(CASE_SPAN_NAME, evaluator=dev_span_evaluator)(make_run_case(ask))

    async def evaluate() -> int:
        try:
            return await run_cases(run_case, cases)
        finally:
            await runtime.aclose()

    with tracer.evaluation_run(settings.config_path, settings.experiment_name):
        failed = asyncio.run(evaluate())
    logger.info("evaluation finished", extra={"cases": len(cases), "failed": failed})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
