---
id: domino-agent-sdk-names
name: Domino agent SDK names
description: "Import the 6.2 agent SDK names in one lazy adapter module, declare dominodatalab[agents] as an optional extra, and depend on the seam elsewhere."
version: 1
scope: scoped
globs:
  - "**/*agent*.py"
  - "**/tracing.py"
  - "**/chat_app.py"
  - "**/main.py"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
applies_if:
  domino_project: true
section: tracing
priority: 49
tags: [python, domino, agents, tracing]
---

# Keep the agent SDK behind one seam

## Description

Import from `domino.agents.tracing` and `domino.agents.logging`; do not use the older `domino.aisystems` alias. On 6.2 the development evaluation wrapper is `DominoRun`, as the 6.2 user guide shows. The Domino Standard Environment provides the SDK, so the repo declares `dominodatalab[agents]` (with a lower bound for 6.2) in an optional extra or dependency group, for custom images and local tracing runs, not as a core dependency. One adapter module imports the SDK lazily and exposes a small seam: a `Tracer` with `trace(name, evaluator=None)` and `evaluation_run(config_path, experiment_name)`, and a `TraceStore` for the evaluation Jobs. Everything else depends on that seam. Outside Domino a missing SDK gives a no-op tracer and one warning; inside Domino it fails at startup naming the package.

## Bad Example

```python
# chat_app.py, agent.py and dev_eval.py each start with:
from domino.agents.logging import DominoRun  # unused here
from domino.agents.tracing import add_tracing
```

Three modules import the SDK unconditionally, two of them never use it, and a local run without the SDK fails with `ImportError` before the app starts.

## Good Example

```python
import logging
from collections.abc import Callable
from typing import Protocol, TypeVar

F = TypeVar("F", bound=Callable[..., object])
logger = logging.getLogger(__name__)


class Tracer(Protocol):
    def trace(
        self, name: str, evaluator: Callable[..., object] | None = None
    ) -> Callable[[F], F]: ...


class NoOpTracer:
    def trace(self, name: str, evaluator: Callable[..., object] | None = None) -> Callable[[F], F]:
        return lambda fn: fn


class DominoTracer:
    def trace(self, name: str, evaluator: Callable[..., object] | None = None) -> Callable[[F], F]:
        from domino.agents.tracing import add_tracing

        return add_tracing(name=name, autolog_frameworks=["pydantic_ai"], evaluator=evaluator)


def select_tracer(settings: AgentSettings) -> Tracer:
    try:
        import domino.agents.tracing  # noqa: F401
    except ImportError as exc:
        if settings.in_domino:
            raise RuntimeError("install dominodatalab[agents] in the Domino environment") from exc
        logger.warning("Domino agent SDK not installed; tracing is off")
        return NoOpTracer()
    return DominoTracer()
```

`evaluation_run` follows the same pattern: `DominoRun(...)` in `DominoTracer`, a `contextlib.nullcontext()` in `NoOpTracer`.

## Notes

- The 6.2 SDK reference already lists `DominoAgentContext`, a `DominoRun` subclass for runs that originate from an agent, and newer docs use it more widely; the development evaluation uses `DominoRun`, as both 6.2 pages show.
- The 6.2 SDK reference names the summary-metric argument `custom_summary_metrics`, while newer material spells it `aggregated_metrics`: check the installed signature before passing it.
- `MLFLOW_TRACKING_URI` is never set in code (domino-env-var-names, domino-jobs); pinning the environment is domino-pinned-environments (domino-jobs).
- Tests use a recording fake of the seam (`domino-agent-fake-domino-tests`).
- The example's app/tracing.py and pyproject.toml show the seam and the optional extra.
