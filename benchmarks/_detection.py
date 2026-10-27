"""CRBugBench-style detection: the judge's question, its verdict, and the rates built from it.

CRBugBench scores a review by one question: did it catch this specific known
defect? The judge answers ``yes`` (the same faulty behaviour and cause, at the
right code), ``partial`` (the right code or a related symptom, not the defect
itself) or ``no``, and splits the review into its separate comments, marking the
ones that report the defect. From that:

- **strict** detection is the share of ``yes`` verdicts;
- **lenient** detection counts ``yes`` as 1 and ``partial`` as 0.5;
- the **first match** is the 1-based position of the first comment that reports
  the defect, and a **top-5** hit is a ``yes`` whose first match is among the
  review's first five comments.

The judge prompt here is written for this benchmark; CRBugBench's own prompt is
not copied (its repository carries no license). Stdlib only, so both
``detect_runs.py`` (engine side) and ``plot_results.py`` (matplotlib side) import it.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Final

LEVEL_SCORE: Final = {"yes": 1.0, "partial": 0.5, "no": 0.0}
TOP_K: Final = 5

_PROMPT: Final = """You are checking whether a code review caught one known defect.

The reviewer saw only the change under review. The defect below was not shown to
them; use it only to know what the real defect is.

KNOWN DEFECT:
{description}
{location}
REVIEW TO CHECK (it may end with the agent's tool log: lines such as "-> Read file",
"$ command" and their output, or a "> build" banner. That log is not part of the
review; ignore it):
<<<REVIEW
{review}
REVIEW

Answer three things.
1. detected: "yes" if the review clearly reports this same defect (the same faulty
   behaviour and cause, at the right code); "partial" if it points at the right
   code or a related symptom but not the defect itself; "no" if it never reports
   it. Judge the substance, not the wording. Other issues the review raises do
   not count.
2. review_items: the review's separate findings or comments, one short line each,
   in the order the review gives them.
3. item_matches: for each review item, in the same order, 1 if that item reports
   the known defect, else 0. When detected is "no", every entry is 0.

Reply with one JSON object and nothing else:
{{"detected": "yes" | "partial" | "no", "evidence_quote": "<the review sentence that reports the defect, verbatim, or empty>", "justification": "<one to three sentences>", "review_items": ["..."], "item_matches": [0, 1]}}"""


class VerdictError(ValueError):
    """The judge's answer is not a usable detection verdict."""


@dataclass(frozen=True)
class Defect:
    """The known defect a review is checked against."""

    description: str
    location: str | None = None


@dataclass(frozen=True)
class Verdict:
    """One judge verdict on one review."""

    detected: str
    review_items: list[str]
    item_matches: list[int]
    evidence_quote: str = ""
    justification: str = ""

    @property
    def first_match(self) -> int | None:
        """1-based position of the first comment reporting the defect (None if none does).

        Example::

            >>> Verdict("yes", ["a", "b"], [0, 1]).first_match
            2
        """
        if self.detected == "no":
            return None
        return next((i + 1 for i, hit in enumerate(self.item_matches) if hit), None)


def detection_prompt(defect: Defect, review: str) -> str:
    """The judge prompt asking whether ``review`` caught ``defect``.

    Example::

        >>> "KNOWN DEFECT" in detection_prompt(Defect("x() drops the last item"), "LGTM")
        True
    """
    location = f"WHERE: {defect.location}\n" if defect.location else ""
    return _PROMPT.format(description=defect.description, location=location, review=review)


def parse_verdict(text: str) -> Verdict:
    """The verdict in the judge's ``text``: one JSON object, possibly fenced.

    Raises :class:`VerdictError` (naming what was wrong) on anything else.

    Example::

        >>> parse_verdict('{"detected": "Yes", "review_items": ["a"], "item_matches": [1]}').detected
        'yes'
    """
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise VerdictError(f"no JSON object in the answer: {text[:200]!r}")
    try:
        raw: dict[str, Any] = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise VerdictError(
            f"answer is not valid JSON ({exc}): {text[start : start + 200]!r}"
        ) from exc
    level = str(raw.get("detected", "")).strip().lower()
    if level not in LEVEL_SCORE:
        raise VerdictError(f"detected must be yes, partial or no, got {raw.get('detected')!r}")
    items, matches = raw.get("review_items"), raw.get("item_matches")
    if not isinstance(items, list) or not isinstance(matches, list) or len(items) != len(matches):
        raise VerdictError(
            f"review_items and item_matches must be lists of one length, got {items!r} / {matches!r}"
        )
    return Verdict(
        detected=level,
        review_items=[str(item) for item in items],
        item_matches=[1 if m in (1, "1", True) else 0 for m in matches],
        evidence_quote=str(raw.get("evidence_quote") or ""),
        justification=str(raw.get("justification") or ""),
    )


def summarize_votes(votes: list[Verdict]) -> dict[str, Any]:
    """One run's detection from its judge votes (several votes average, like a panel).

    Example::

        >>> summarize_votes([Verdict("yes", ["a"], [1]), Verdict("partial", ["a"], [0])])["lenient"]
        0.75
    """
    if not votes:
        raise ValueError("summarize_votes needs at least one verdict")
    firsts = [v.first_match for v in votes if v.first_match is not None]
    return {
        "detected": votes[0].detected
        if len(votes) == 1
        else _majority([v.detected for v in votes]),
        "strict": statistics.fmean(1.0 if v.detected == "yes" else 0.0 for v in votes),
        "lenient": statistics.fmean(LEVEL_SCORE[v.detected] for v in votes),
        "top5": statistics.fmean(1.0 if _top_k_hit(v) else 0.0 for v in votes),
        "first_match": int(statistics.median(firsts)) if firsts else None,
        "n_items": int(statistics.median(len(v.review_items) for v in votes)),
        "votes": [asdict(v) for v in votes],
    }


def _top_k_hit(verdict: Verdict) -> bool:
    first = verdict.first_match
    return verdict.detected == "yes" and first is not None and first <= TOP_K


def _majority(levels: list[str]) -> str:
    """The most common level; ties go to the lower one (the stricter reading)."""
    order = ["no", "partial", "yes"]
    return max(order, key=lambda level: (levels.count(level), -order.index(level)))
