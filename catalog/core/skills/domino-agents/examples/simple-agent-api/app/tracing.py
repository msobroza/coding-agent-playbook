"""The seam in front of the Domino agent SDK: tracing and the development evaluation run.

Only this module (and evals/trace_store.py) imports the SDK, lazily, so the App,
the Jobs and the tests run without it. DominoTracer applies ``add_tracing``
directly to the request function, with pydantic-ai autologging, and opens
``DominoRun`` for a development evaluation; NoOpTracer returns the function
unchanged and a null context. select_tracer decides once, on settings.in_domino:
inside Domino the SDK traces and a missing SDK fails at startup naming the
package; outside Domino tracing is off with one warning, installed SDK or not.
"""

import contextlib
import importlib
import logging
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Final, Protocol, TypeVar, cast

from app.settings import AgentSettings

logger = logging.getLogger(__name__)

#: The span name of the request function, shared by the App and both evaluation Jobs.
REQUEST_SPAN_NAME: Final = "ask_agent"
#: The frameworks the SDK autologs under the traced function.
AUTOLOG_FRAMEWORKS: Final = ("pydantic_ai",)
#: The package that provides domino.agents (the Domino Standard Environment ships it).
SDK_PACKAGE: Final = "dominodatalab[agents]"

F = TypeVar("F", bound=Callable[..., object])


class SpanLike(Protocol):
    """What an evaluator reads from a span: the traced function's inputs and outputs."""

    @property
    def inputs(self) -> Mapping[str, object]: ...

    @property
    def outputs(self) -> Mapping[str, object]: ...


SpanEvaluator = Callable[[SpanLike], Mapping[str, float]]


class Tracer(Protocol):
    """Traces a function under a span name, and opens a development evaluation run."""

    def trace(self, name: str, evaluator: SpanEvaluator | None = None) -> Callable[[F], F]: ...

    def evaluation_run(
        self, config_path: Path, experiment_name: str
    ) -> AbstractContextManager[object]: ...


class NoOpTracer:
    """Tracing off: functions run unchanged and the evaluation run is a null context."""

    def trace(self, name: str, evaluator: SpanEvaluator | None = None) -> Callable[[F], F]:
        def unchanged(function: F) -> F:
            return function

        return unchanged

    def evaluation_run(
        self, config_path: Path, experiment_name: str
    ) -> AbstractContextManager[object]:
        return contextlib.nullcontext()


class DominoTracer:
    """The Domino agent SDK: add_tracing on the request function, DominoRun for evaluations."""

    def trace(self, name: str, evaluator: SpanEvaluator | None = None) -> Callable[[F], F]:
        from domino.agents.tracing import add_tracing

        decorator = add_tracing(
            name=name, autolog_frameworks=list(AUTOLOG_FRAMEWORKS), evaluator=evaluator
        )
        return cast("Callable[[F], F]", decorator)

    def evaluation_run(
        self, config_path: Path, experiment_name: str
    ) -> AbstractContextManager[object]:
        from domino.agents.logging import DominoRun

        run = DominoRun(agent_config_path=str(config_path), experiment_name=experiment_name)
        return cast("AbstractContextManager[object]", run)


def sdk_installed() -> bool:
    """True when ``domino.agents.tracing`` imports."""
    try:
        importlib.import_module("domino.agents.tracing")
    except ImportError:
        return False
    return True


def select_tracer(
    settings: AgentSettings, *, sdk_available: Callable[[], bool] = sdk_installed
) -> Tracer:
    """DominoTracer inside Domino, where a missing SDK is a startup error; else NoOpTracer."""
    if not settings.in_domino:
        logger.warning("outside Domino; tracing is off", extra={"package": SDK_PACKAGE})
        return NoOpTracer()
    if not sdk_available():
        raise RuntimeError(f"the Domino agent SDK is missing: install {SDK_PACKAGE}")
    return DominoTracer()
