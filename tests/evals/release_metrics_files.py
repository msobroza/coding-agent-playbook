"""Hand-written release metrics files (schema version 1) for the regression check's tests.

:func:`metrics_file` writes out every key the schema needs; a test passes only
the numbers it is about, through :func:`sample_entry`.
"""

from __future__ import annotations

from typing import Any

#: The sample digest every hand-written entry carries unless a test changes it.
DIGEST = "sample-digest-1"


def sample_entry(
    mean: float,
    *,
    passes: int = 3,
    runs: int = 3,
    digest: str = DIGEST,
    cost: float | None = None,
    tokens: float | None = None,
    graded: str = "head",
) -> dict[str, Any]:
    """One ``samples.<id>`` (or ``controls.<id>``) entry with ``passes`` of ``runs``."""
    return {
        "prompt_id": "review",
        "graded": graded,
        "prompt_digest": "prompt-digest-1",
        "sample_digest": digest,
        "passes": passes,
        "runs": runs,
        "mean_score": mean,
        "stdev": 0.0,
        "checks": {"gate": mean},
        "duration_seconds_mean": 10.0,
        "tokens_mean": tokens,
        "cost_usd_mean": cost,
    }


def metrics_file(
    release: str,
    samples: dict[str, dict[str, Any]],
    *,
    target: str = "claude-opus",
    harness_version: str | None = "2.1.300",
    commit: str | None = None,
    controls: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A whole release metrics file of ``samples`` on ``target``.

    ``controls`` adds the pinned samples' edition runs; ``None`` leaves the key out,
    as files written before ticket 15 did.
    """
    extra = {} if controls is None else {"controls": controls}
    return extra | {
        "schema_version": 1,
        "release": release,
        "previous": None,
        "commit": commit,
        "target": {
            "name": target,
            "harness": "claude_code",
            "harness_version": harness_version,
            "model": "claude-opus-5-5",
            "reported_model": "claude-opus-5-5",
            "label": None,
            "endpoint": None,
            "price": None,
            "judge_model": None,
            "runs": 3,
        },
        "summary": {
            "samples": len(samples),
            "runs": sum(entry["runs"] for entry in samples.values()),
            "pass_rate": 1.0,
            "mean_score": 0.9,
            "tokens": None,
            "cost_usd": None,
        },
        "samples": samples,
    }
