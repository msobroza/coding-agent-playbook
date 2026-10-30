"""The release metrics file's schema, version 1, and its validator (spec #281 ticket 07).

One file holds one release's scores on one Eval target
(``catalog/releases/<version>/metrics/<target>.json``). Version 1 is::

    {
      "schema_version": 1,
      "release": "<engine version>", "previous": null, "commit": "<sha>" | null,
      "target": {"name", "harness", "harness_version", "model", "reported_model",
                 "label", "endpoint": {"name", "fingerprint"} | null,
                 "price": {"input", "output"} | null, "judge_model", "runs",
                 "isolated"?},
      "summary": {"samples", "runs", "pass_rate", "mean_score", "tokens", "cost_usd",
                  "rerun"?, "carried"?, "rejudged"?},
      "samples": {"<sample id>": {"prompt_id", "graded", "prompt_digest", "sample_digest",
                  "passes", "runs", "mean_score", "stdev", "checks": {"<check id>": score},
                  "duration_seconds_mean", "tokens_mean", "cost_usd_mean",
                  "inputs_digest"?, "measured_in"?: {"release", "commit", "target"?},
                  "rejudged_from"?: {"release", "commit", "judge": {<judge part>: value}},
                  "judged_in"?: {"release", "commit", "target"?}}},
      "controls": {"<sample id>": {the same keys, "graded": "<edition tag>"}},
      "setup_digest"?: "<sha256>",
      "setup"?: {"harness", "harness_version", "model", "endpoint_fingerprint",
                 "small_model", "runs", "judge_model", "judge_endpoint_fingerprint",
                 "judge_samples", "judge_version", "fail_fast", "isolated",
                 "scoring_digest"},
      "judge_change"?: {"from": [{<judge part>: value}, ...], "to": {<judge part>: value},
                        "runs", "pass_agreement", "mean_abs_score_diff",
                        "tasks": {"<task>": {"runs", "pass_agreement", "mean_abs_score_diff"}}}
    }

``controls`` (#281 ticket 15) holds the pinned samples' runs on their frozen
editions; each pinned sample is in ``samples`` too, graded on the current text.
A control that moves between releases while its edition stayed fixed points at a
model or harness drift, not at the guidance. It is optional, so a file written
before it still validates, and the summary counts ``samples`` only.

``inputs_digest`` (#329 ticket 03) is the sha256 of what the agent received:
the strict render of the prompt the entry ran (the current text for ``samples``,
the edition's for ``controls``) together with ``sample_digest``. It is optional,
so a file written before it still validates; when present it is a string.

``target.isolated`` (#329 ticket 02) is ``true`` when the harness and the judge
ran with an empty config directory, without the user's personal settings
(``evals.record_isolation``). It is optional too; when present it is a bool.

``setup_digest`` (#329 ticket 04) is the sha256 of everything outside the
samples that decides scores, and ``setup`` holds its named parts
(``evals.setup_digest.SetupParts``), so a later record can name the part that
differs. Both are optional, so a file written before them still validates; when
present, the digest is a string and every part is present and typed.

``measured_in`` and the summary's ``rerun`` and ``carried`` counts (#329 ticket
05, ``evals.release_carry``) come with ``playbook eval --record --carry-from``:
a carried entry is copied from the baseline file, and its ``measured_in`` names
the release and commit that measured it, plus the source file's ``target`` when
it was carried through the result index (``evals.result_index``); ``rerun`` counts the entries this
record measured and ``carried`` the copied ones. The regression check
(``evals.release_regression``) also writes both counts on every file it
annotates; in a full record every entry counts as rerun and ``carried`` is 0.
All are optional, so a file written without them still validates; when present
they are typed. A re-judged entry (spec D9) adds ``rejudged_from``: the file whose
stored answers this record's judge re-graded, with that file's judge parts; the
summary's ``rejudged`` counts those entries. A re-judged entry carried on
records ``judged_in``: the release (and target) whose answers file holds the
lines its current judge graded. All three are optional too. An entry is
*re-judged in this file* (:func:`rejudged_here`) when it has ``rejudged_from``
and no ``judged_in``; one carried after a re-judge is a carried entry.

``judge_change`` (spec D10, ``evals.judge_agreement``) is written only by a
record that re-judged runs: how closely the new judge (``to``) agrees with the
old ones (``from``, each distinct judge's parts) on the same answers, overall and
per task. It is optional; when present, every key is present and typed.

``previous`` is ``null`` until the regression check compares the file with the
previous release; that check may add comparison keys (``vs_previous`` per
sample, regression counts in the summary) without a new version, because a
reader ignores keys it does not know. Removing or retyping a key here needs a
new :data:`SCHEMA_VERSION`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The version of the file shape this module writes and validates.
SCHEMA_VERSION: Final = 1
#: The optional key of the pinned samples' runs on their editions.
CONTROLS_KEY: Final = "controls"
#: The optional per-entry key of the digest of what the agent received.
INPUTS_DIGEST_KEY: Final = "inputs_digest"
#: The optional target key saying the run was isolated from personal settings.
ISOLATED_KEY: Final = "isolated"
#: The optional top-level key of the setup digest (#329 ticket 04).
SETUP_DIGEST_KEY: Final = "setup_digest"
#: The optional top-level key of the setup digest's named parts.
SETUP_KEY: Final = "setup"
#: The optional per-entry key naming the release and commit that measured a carried entry.
MEASURED_IN_KEY: Final = "measured_in"
#: The optional per-entry key of a re-judged entry (spec D9): the re-graded file and its judge.
REJUDGED_FROM_KEY: Final = "rejudged_from"
#: The optional per-entry key naming whose answers file holds the current judge's lines (D9).
JUDGED_IN_KEY: Final = "judged_in"
#: The optional top-level key of the old and new judges' agreement (spec D10).
JUDGE_CHANGE_KEY: Final = "judge_change"

_STR: Final = (str,)
_OPT_STR: Final = (str, type(None))
_INT: Final = (int,)
_OPT_INT: Final = (int, type(None))
_OPT_BOOL: Final = (bool, type(None))
_NUM: Final = (int, float)
_OPT_NUM: Final = (int, float, type(None))
_OPT_OBJ: Final = (dict, type(None))

type _Fields = Mapping[str, tuple[type, ...]]

_TOP: Final[_Fields] = {
    "schema_version": _INT,
    "release": _STR,
    "previous": _OPT_STR,
    "commit": _OPT_STR,
    "target": (dict,),
    "summary": (dict,),
    "samples": (dict,),
}
#: Top-level keys added under version 1: absent in older files, typed when present.
_OPTIONAL_TOP: Final[_Fields] = {
    SETUP_DIGEST_KEY: _STR,
    SETUP_KEY: (dict,),
    JUDGE_CHANGE_KEY: (dict,),
}
#: The setup digest's parts (``evals.setup_digest.SetupParts``), all present when ``setup`` is.
SETUP_PART_TYPES: Final[_Fields] = {
    "harness": _STR,
    "harness_version": _OPT_STR,
    "model": _OPT_STR,
    "endpoint_fingerprint": _OPT_STR,
    "small_model": _OPT_STR,
    "runs": _INT,
    "judge_model": _OPT_STR,
    "judge_endpoint_fingerprint": _OPT_STR,
    "judge_samples": _OPT_INT,
    "judge_version": _OPT_STR,
    "fail_fast": (bool,),
    "isolated": _OPT_BOOL,
    "scoring_digest": _STR,
}
#: A setup part recorded only when set, so files recorded before it existed stay valid.
JUDGE_REASONING_EFFORT_PART: Final = "judge_reasoning_effort"
OPTIONAL_SETUP_PART_TYPES: Final[_Fields] = {JUDGE_REASONING_EFFORT_PART: _OPT_STR}
_TARGET: Final[_Fields] = {
    "name": _STR,
    "harness": _STR,
    "harness_version": _OPT_STR,
    "model": _STR,
    "reported_model": _OPT_STR,
    "label": _OPT_STR,
    "endpoint": _OPT_OBJ,
    "price": _OPT_OBJ,
    "judge_model": _OPT_STR,
    "runs": _INT,
}
#: Target keys added under version 1: absent in older files, typed when present.
_OPTIONAL_TARGET: Final[_Fields] = {ISOLATED_KEY: (bool,)}
_ENDPOINT: Final[_Fields] = {"name": _STR, "fingerprint": _STR}
_PRICE: Final[_Fields] = {"input": _NUM, "output": _NUM}
_SUMMARY: Final[_Fields] = {
    "samples": _INT,
    "runs": _INT,
    "pass_rate": _NUM,
    "mean_score": _OPT_NUM,
    "tokens": (int, type(None)),
    "cost_usd": _OPT_NUM,
}
#: Summary keys added under version 1 (#329 ticket 05): absent in older files, typed when present.
_OPTIONAL_SUMMARY: Final[_Fields] = {"rerun": _INT, "carried": _INT, "rejudged": _INT}
_SAMPLE: Final[_Fields] = {
    "prompt_id": _STR,
    "graded": _STR,
    "prompt_digest": _OPT_STR,
    "sample_digest": _STR,
    "passes": _INT,
    "runs": _INT,
    "mean_score": _NUM,
    "stdev": _NUM,
    "checks": (dict,),
    "duration_seconds_mean": _NUM,
    "tokens_mean": _OPT_NUM,
    "cost_usd_mean": _OPT_NUM,
}
#: Entry keys added under version 1: absent in older files, typed when present.
_OPTIONAL_SAMPLE: Final[_Fields] = {
    INPUTS_DIGEST_KEY: _STR,
    MEASURED_IN_KEY: (dict,),
    REJUDGED_FROM_KEY: (dict,),
    JUDGED_IN_KEY: (dict,),
}
_MEASURED_IN: Final[_Fields] = {"release": _STR, "commit": _OPT_STR}
#: The source file's target, recorded by an entry carried through ``evals.result_index``.
_OPTIONAL_MEASURED_IN: Final[_Fields] = {"target": _STR}
_REJUDGED_FROM: Final[_Fields] = {"release": _STR, "commit": _OPT_STR, "judge": (dict,)}
_AGREEMENT: Final[_Fields] = {"runs": _INT, "pass_agreement": _NUM, "mean_abs_score_diff": _NUM}
_JUDGE_CHANGE: Final[_Fields] = {"from": (list,), "to": (dict,), **_AGREEMENT, "tasks": (dict,)}


class ReleaseMetricsError(ExitTwoError):
    """A release metrics file that does not match :data:`SCHEMA_VERSION`; lists every problem.

    Example::

        >>> str(ReleaseMetricsError("schema_version: expected 1, got 2"))
        'schema_version: expected 1, got 2'
    """


def validate_release_metrics(data: object) -> None:
    """Raise :class:`ReleaseMetricsError` naming each key whose value does not fit the schema.

    Example::

        >>> validate_release_metrics({"schema_version": 1})  # doctest: +SKIP
        Traceback (most recent call last):
        ReleaseMetricsError: release: missing; ...
    """
    problems = _problems(data)
    if problems:
        raise ReleaseMetricsError("release metrics file: " + "; ".join(problems))


def rejudged_here(entry: Mapping[str, object]) -> bool:
    """Whether ``entry`` was re-judged in its own file: ``rejudged_from`` without ``judged_in``.

    An entry carried after a re-judge keeps ``rejudged_from`` and gains
    ``judged_in`` (``evals.release_carry.carried_entry``): it is a carried entry.

    Example::

        >>> rejudged_here({"rejudged_from": {}, "judged_in": {"release": "9.9.2"}})
        False
    """
    return REJUDGED_FROM_KEY in entry and JUDGED_IN_KEY not in entry


def _problems(data: object) -> list[str]:
    if not isinstance(data, dict):
        return [f"expected a JSON object, got {type(data).__name__}"]
    problems = _check_fields(data, _TOP, "")
    if data.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"schema_version: expected {SCHEMA_VERSION}, got {data.get('schema_version')!r}"
        )
    problems += _nested(data, "target", _TARGET)
    problems += _nested(data, "summary", _SUMMARY)
    summary = data.get("summary")
    if isinstance(summary, dict):
        problems += _check_fields(summary, _OPTIONAL_SUMMARY, "summary.", optional=True)
    problems += _check_fields(data, _OPTIONAL_TOP, "", optional=True)
    problems += _nested(data, SETUP_KEY, SETUP_PART_TYPES)
    problems += _judge_change_problems(data.get(JUDGE_CHANGE_KEY))
    setup = data.get(SETUP_KEY)
    if isinstance(setup, dict):
        problems += _check_fields(setup, OPTIONAL_SETUP_PART_TYPES, f"{SETUP_KEY}.", optional=True)
    target = data.get("target")
    if isinstance(target, dict):
        problems += _check_fields(target, _OPTIONAL_TARGET, "target.", optional=True)
        problems += _nested(target, "endpoint", _ENDPOINT, prefix="target.")
        problems += _nested(target, "price", _PRICE, prefix="target.")
    controls = data.get(CONTROLS_KEY, {})
    if not isinstance(controls, dict):
        problems.append(f"{CONTROLS_KEY}: expected dict, got {controls!r}")
    for key, entries in (("samples", data.get("samples")), (CONTROLS_KEY, controls)):
        if isinstance(entries, dict):
            for sample_id, entry in entries.items():
                problems += _sample_problems(f"{key}.{sample_id}", entry)
    return problems


def _sample_problems(label: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{label}: expected an object, got {type(entry).__name__}"]
    problems = _check_fields(entry, _SAMPLE, f"{label}.")
    problems += _check_fields(entry, _OPTIONAL_SAMPLE, f"{label}.", optional=True)
    problems += _nested(entry, REJUDGED_FROM_KEY, _REJUDGED_FROM, prefix=f"{label}.")
    for key in (MEASURED_IN_KEY, JUDGED_IN_KEY):
        problems += _place_problems(f"{label}.", key, entry.get(key))
    checks = entry.get("checks")
    if isinstance(checks, dict):
        problems += [
            f"{label}.checks.{name}: expected a number, got {score!r}"
            for name, score in checks.items()
            if not _fits(score, _NUM)
        ]
    return problems


def _judge_change_problems(change: object) -> list[str]:
    """The problems of a ``judge_change`` object: its keys, each old judge, each task."""
    if not isinstance(change, dict):
        return []
    prefix = f"{JUDGE_CHANGE_KEY}."
    problems = _check_fields(change, _JUDGE_CHANGE, prefix)
    olds = change.get("from")
    if isinstance(olds, list):
        problems += [
            f"{prefix}from[{index}]: expected dict, got {parts!r}"
            for index, parts in enumerate(olds)
            if not isinstance(parts, dict)
        ]
    tasks = change.get("tasks")
    if isinstance(tasks, dict):
        for task, agreement in tasks.items():
            problems += _nested(tasks, task, _AGREEMENT, prefix=f"{prefix}tasks.")
            if not isinstance(agreement, dict):
                problems.append(f"{prefix}tasks.{task}: expected dict, got {agreement!r}")
    return problems


def _place_problems(prefix: str, key: str, place: object) -> list[str]:
    """The problems of a ``measured_in`` or ``judged_in`` object: release, commit, target?."""
    if not isinstance(place, dict):
        return []
    problems = _check_fields(place, _MEASURED_IN, f"{prefix}{key}.")
    return problems + _check_fields(place, _OPTIONAL_MEASURED_IN, f"{prefix}{key}.", optional=True)


def _nested(parent: Mapping[str, object], key: str, fields: _Fields, prefix: str = "") -> list[str]:
    """The problems of ``parent[key]`` when it is an object (absent and ``null`` are checked above)."""
    value = parent.get(key)
    return _check_fields(value, fields, f"{prefix}{key}.") if isinstance(value, dict) else []


def _check_fields(
    table: Mapping[str, object], fields: _Fields, prefix: str, *, optional: bool = False
) -> list[str]:
    """The problems of ``fields`` in ``table``; an ``optional`` field may be absent."""
    problems: list[str] = []
    for key, types in fields.items():
        if key not in table:
            if not optional:
                problems.append(f"{prefix}{key}: missing")
        elif not _fits(table[key], types):
            expected = " or ".join(_type_name(t) for t in types)
            problems.append(f"{prefix}{key}: expected {expected}, got {table[key]!r}")
    return problems


def _fits(value: object, types: tuple[type, ...]) -> bool:
    """``isinstance``, except that a bool is never a number (JSON keeps them apart)."""
    if isinstance(value, bool):
        return bool in types
    return isinstance(value, types)


def _type_name(kind: type) -> str:
    return "null" if kind is type(None) else kind.__name__
