"""A judge CLI for the engine's ``LLMJudge``: one grading prompt in, Opus's answer out.

``LLMJudge`` shells out to a command with the grading prompt as its last
argument and parses stdout as one ``0-1`` number. This script is that command
for Opus 5.5 at medium effort through OpenRouter, for when the Anthropic API
key cannot be used. A failed call exits non-zero so ``LLMJudge`` retries it.
When ``JUDGE_USAGE_LOG`` is set, each call's token usage and cost is appended
there as one JSON line.

Usage::

    OPENROUTER_API_KEY=... python benchmarks/judge_openrouter.py "<grading prompt>"
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench

_URL = "https://openrouter.ai/api/v1/chat/completions"
_ATTEMPTS = 3
_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})


def _request_body(prompt: str) -> bytes:
    body = {
        "model": _bench.JUDGE_MODEL_OPENROUTER,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning": {"effort": _bench.JUDGE_EFFORT, "exclude": True},
        "max_tokens": 4000,
        "usage": {"include": True},
    }
    return json.dumps(body).encode("utf-8")


def _post(prompt: str) -> dict[str, object]:
    """POST one completion; retries throttling/5xx with backoff, raises otherwise."""
    headers = {
        "Authorization": f"Bearer {_bench.require_env('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
    }
    for attempt in range(_ATTEMPTS):
        request = urllib.request.Request(_URL, data=_request_body(prompt), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=_bench.JUDGE_TIMEOUT_S) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRY_STATUSES or attempt == _ATTEMPTS - 1:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == _ATTEMPTS - 1:
                raise RuntimeError(f"OpenRouter unreachable: {exc}") from exc
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _log_usage(payload: dict[str, object]) -> None:
    log_path = os.environ.get("JUDGE_USAGE_LOG")
    if not log_path:
        return
    usage = payload.get("usage") or {}
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"model": payload.get("model"), "usage": usage}) + "\n")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(f"usage: judge_openrouter.py <prompt>, got {len(argv)} args", file=sys.stderr)
        return 2
    try:
        payload = _post(argv[0])
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _log_usage(payload)
    choices = payload.get("choices") or []
    if not choices:
        print(f"no choices in response: {str(payload)[:300]}", file=sys.stderr)
        return 1
    print((choices[0].get("message") or {}).get("content") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
