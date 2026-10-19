"""The one ruff seam of the post-edit hooks (specs/prK-hook-pack.md §E.3).

Every ruff call of the §E.3 pipeline goes through :class:`RuffRunner`: the
``machine.json`` pin (never ``uv run``, never ``PATH``; L8), ``ctx.proc``
(``FakeRuff`` in tests) and a 2 s timeout per call. What it owns:

- :func:`ruff_pin`: the pin check. A missing pin or a program whose stat
  signature changed since sync (the agent overwrote ``.venv/bin/ruff``) runs
  nothing;
- the argv of each call: M1 (safe fixes, ``F401``/``F841``/``F811`` never
  fixed) and M2 (format), both over the edited file's bytes on stdin (the
  caller compares them before and after: review finding #5), the HEAD
  format-clean check and D1, the **one**
  diagnostics call, ``--extend-select`` so the project's own ``select``,
  ``ignore``, ``per-file-ignores`` and ``# noqa`` win (plus the quality
  bucket's ``--config`` thresholds, and one ``--preview`` call for the codes
  only ruff's preview has, §F.2.2);
- :func:`ruff_diagnostics_for`: D1 memoized per ``(path, content sha256)`` on
  the event's memo, so whichever post-edit hook asks first runs it;
- :func:`changed_lines`: the lines an edit inserted or replaced, so legacy
  code is never flooded;
- :func:`selector_matches`: ruff's prefix-aware selector semantics (``I``
  selects ``I001``, never ``INP001``).

Stdlib only; ``difflib`` loads on the Python-edit branch alone (§D.1).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.dispatch.proc import ProcTimeout

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_runtime.config.pin import MachinePins
    from coding_agent_playbook.hook_runtime.dispatch.deps import ProcPort
    from coding_agent_playbook.hook_runtime.dispatch.event_memo import EventMemo
    from coding_agent_playbook.hook_runtime.dispatch.proc import ProcResult

__all__ = [
    "NEVER_FIX",
    "RUFF_TIMEOUT_S",
    "PinProblem",
    "RuffDiagnostic",
    "RuffFailure",
    "RuffPin",
    "RuffRunner",
    "changed_lines",
    "d1_args",
    "fix_args",
    "format_args",
    "format_check_args",
    "intersect_selectors",
    "parse_diagnostics",
    "preview_args",
    "rewritten",
    "ruff_diagnostics_for",
    "ruff_pin",
    "selector_matches",
]

#: Per ruff call (§E.3 budget): a hook never waits on a hung ruff.
RUFF_TIMEOUT_S: Final = 2.0
#: Unused import / variable / redefinition: the agent adds an import in one Edit and its
#: first use in the next, and a fix in between would delete it. Never fixed (§E.3).
NEVER_FIX: Final = ("F401", "F841", "F811")
#: How ruff names a parse failure: ``code: null`` before 0.17, ``invalid-syntax`` since.
_SYNTAX_CODES: Final = frozenset({"invalid-syntax", "syntax-error", "E999"})
_SYNTAX_LABEL: Final = "syntax-error"
_LETTERS: Final = re.compile(r"[A-Z]*")
#: Pylint's codes carry a category letter after the linter prefix (``PLR0911``).
_PYLINT: Final = "PL"

type PinProblem = Literal["missing", "changed"]
type FailureKind = Literal["timeout", "missing", "error"]


# --- selectors ------------------------------------------------------------------------------


def selector_matches(selector: str, code: str) -> bool:
    """Whether ruff selector ``selector`` selects ``code`` (or the narrower selector ``code``).

    A selector is a linter prefix plus optional code digits; ``I`` selects
    ``I001`` but not ``INP001``, ``PL`` selects ``PLR0911``, ``ALL`` everything.

    Example::

        >>> selector_matches("UP", "UP006"), selector_matches("I", "INP001")
        (True, False)
    """
    if selector == "ALL":
        return True
    if not code.startswith(selector):
        return False
    mine, theirs = _letters(selector), _letters(code)
    if mine == theirs:
        return True
    return mine == _PYLINT and len(theirs) == len(_PYLINT) + 1 and theirs.startswith(_PYLINT)


def _letters(text: str) -> str:
    found = _LETTERS.match(text)
    return found.group(0) if found else ""


def intersect_selectors(allowed: Iterable[str], selected: Iterable[str]) -> list[str]:
    """The selectors in both ``allowed`` and ``selected``, prefix-aware, sorted.

    An ``allowed`` prefix a broader ``selected`` selector covers is kept
    whole; a ``selected`` selector narrower than an ``allowed`` one is kept.

    Example::

        >>> intersect_selectors(["I", "UP"], ["E", "F", "I", "UP006"])
        ['I', 'UP006']
    """
    chosen = set(selected)
    kept: set[str] = set()
    for prefix in allowed:
        if any(selector_matches(s, prefix) for s in chosen):
            kept.add(prefix)
        else:
            kept.update(s for s in chosen if selector_matches(prefix, s))
    return sorted(kept)


# --- the pin and the runner ---------------------------------------------------------------


class RuffFailure(Exception):
    """A ruff call that did not give a usable answer; the pipeline skips (``on_error: open``).

    Example::

        >>> str(RuffFailure("timeout", "ruff check"))
        'ruff check: timeout'
    """

    def __init__(self, kind: FailureKind, what: str) -> None:
        super().__init__(f"{what}: {kind}")
        self.kind: FailureKind = kind


@dataclass(frozen=True, slots=True)
class RuffPin:
    """The pinned ruff argv and the codes its version cannot run (``machine.json``, §D.8.3)."""

    argv: tuple[str, ...]
    drop: frozenset[str] = frozenset()


def ruff_pin(pins: MachinePins | None) -> RuffPin | PinProblem:
    """The usable ruff pin, or ``"missing"`` / ``"changed"`` (its signature moved since sync).

    Example::

        >>> ruff_pin(None)
        'missing'
    """
    pin = None if pins is None else pins.tool("ruff")
    if pin is None:
        return "missing"
    if not pin.unchanged():
        return "changed"
    return RuffPin(pin.argv, pin.drop)


@dataclass(frozen=True, slots=True)
class RuffRunner:
    """Runs the pinned ruff in the worktree through the dispatch's ``ProcPort``.

    Example::

        >>> RuffRunner(ctx.proc, pin, cwd=repo.worktree_root).run(["--version"]).ok  # doctest: +SKIP
        True
    """

    proc: ProcPort
    pin: RuffPin
    cwd: str

    def run(
        self, args: Sequence[str], *, stdin: bytes | None = None, timeout_s: float = RUFF_TIMEOUT_S
    ) -> ProcResult:
        """``<ruff> <args>``; a non-zero exit is returned, a timeout or missing program raises."""
        what = f"ruff {args[0] if args else ''}".rstrip()
        try:
            return self.proc.run(
                [*self.pin.argv, *args], timeout=timeout_s, input=stdin, cwd=self.cwd
            )
        except ProcTimeout:
            raise RuffFailure("timeout", what) from None
        except OSError:  # the pinned program vanished between the stat and the spawn
            raise RuffFailure("missing", what) from None


# --- argv ------------------------------------------------------------------------------------


def d1_args(
    path: str, codes: Iterable[str], drop: Iterable[str] = (), config: Iterable[str] = ()
) -> list[str]:
    """D1, the one diagnostics call: report-only, JSON, project config plus ``codes``.

    ``drop`` (codes the pinned ruff does not know or has only in preview)
    never reaches ``--extend-select``, where ruff would reject the whole call.
    ``config`` are per-invocation ``--config`` overrides (``key=value``).

    Example::

        >>> d1_args("/r/a.py", ["UP045", "B006"], drop=["UP045"])[-4:]
        ['--extend-select', 'B006', '--', '/r/a.py']
    """
    dropped = set(drop)
    extend = sorted(set(codes) - dropped)
    args = ["check", "--no-fix", "--exit-zero", "--force-exclude", "--output-format", "json"]
    if extend:
        args += ["--extend-select", ",".join(extend)]
    for flag in config:
        args += ["--config", flag]
    return [*args, "--", path]


def preview_args(path: str, codes: Iterable[str], config: Iterable[str] = ()) -> list[str]:
    """The separate call for codes only ruff's preview has (PLR1702): ``--preview`` here only.

    Preview is never enabled globally (addendum D-Q1), and ``--select`` keeps
    this call to exactly those codes.

    Example::

        >>> preview_args("/r/a.py", ["PLR1702"])[-5:]
        ['--preview', '--select', 'PLR1702', '--', '/r/a.py']
    """
    args = ["check", "--no-fix", "--exit-zero", "--force-exclude", "--output-format", "json"]
    for flag in config:
        args += ["--config", flag]
    return [*args, "--preview", "--select", ",".join(sorted(set(codes))), "--", path]


def fix_args(rel: str, select: Sequence[str], ignore: Sequence[str] = ()) -> list[str]:
    """M1: safe fixes of ``select`` only, of the text on stdin judged as ``rel``.

    ``ignore`` re-applies the project's narrower ignores: a CLI ``--select``
    resets the config's ``ignore``. The fixed text is printed on stdout.

    Example::

        >>> fix_args("src/a.py", ["I"])[-3:]
        ['--stdin-filename', 'src/a.py', '-']
    """
    args = ["check", "--fix-only", "--force-exclude", "--no-unsafe-fixes"]
    args += ["--select", ",".join(select)]
    if ignore:
        args += ["--ignore", ",".join(ignore)]
    return [*args, "--unfixable", ",".join(NEVER_FIX), "--stdin-filename", rel, "-"]


def format_args(rel: str) -> list[str]:
    """M2: format the text on stdin judged as ``rel`` (after M1: the formatter has the last word).

    Example::

        >>> format_args("src/a.py")
        ['format', '--force-exclude', '--stdin-filename', 'src/a.py', '-']
    """
    return ["format", "--force-exclude", "--stdin-filename", rel, "-"]


def rewritten(done: ProcResult, text: bytes) -> bytes:
    """What an M1/M2 stdin call made of ``text``; ``text`` itself unless it ran cleanly.

    A parse error (exit 2) or an empty answer to a non-empty text keeps the
    text: the file is never replaced by an error or by nothing.

    Example::

        >>> rewritten(ProcResult(("ruff",), 2), b"x=1\\n")
        b'x=1\\n'
    """
    if done.returncode != 0 or (text and not done.stdout):
        return text
    return done.stdout


def format_check_args(rel: str) -> list[str]:
    """Is the HEAD text (fed on stdin) format-clean, judged as ``rel`` under the project config.

    Example::

        >>> format_check_args("src/a.py")[-2:]
        ['src/a.py', '-']
    """
    return ["format", "--check", "--force-exclude", "--stdin-filename", rel, "-"]


# --- diagnostics -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuffDiagnostic:
    """One D1 diagnostic: its code (``None`` or ``invalid-syntax`` for a parse error), line, text.

    Example::

        >>> RuffDiagnostic(None, 3, "Expected ')'").label
        'syntax-error'
    """

    code: str | None
    row: int
    message: str

    @property
    def is_syntax_error(self) -> bool:
        """A parse failure: CI fails on it whatever the project selects."""
        return self.code is None or self.code in _SYNTAX_CODES

    @property
    def label(self) -> str:
        """The code as shown to the model."""
        return _SYNTAX_LABEL if self.code is None else self.code


def parse_diagnostics(stdout: bytes) -> list[RuffDiagnostic]:
    """D1's ``--output-format json`` as diagnostics; raises :class:`RuffFailure` when malformed.

    Example::

        >>> parse_diagnostics(b'[{"code": "F401", "location": {"row": 1}, "message": "x"}]')
        [RuffDiagnostic(code='F401', row=1, message='x')]
    """
    try:
        rows = json.loads(stdout or b"[]")
    except ValueError:
        raise RuffFailure("error", "ruff check output") from None
    if not isinstance(rows, list):
        raise RuffFailure("error", "ruff check output")
    return [_diagnostic(row) for row in rows]


def _diagnostic(row: object) -> RuffDiagnostic:
    location = row.get("location") if isinstance(row, dict) else None
    line = location.get("row") if isinstance(location, dict) else None
    if not isinstance(row, dict) or type(line) is not int:
        raise RuffFailure("error", "ruff check output")
    code, message = row.get("code"), row.get("message")
    return RuffDiagnostic(
        code if isinstance(code, str) else None, line, message if isinstance(message, str) else ""
    )


def ruff_diagnostics_for(
    runner: RuffRunner,
    memo: EventMemo,
    path: str,
    content: bytes,
    codes: Iterable[str],
    *,
    config: Sequence[str] = (),
    preview: Iterable[str] = (),
) -> list[RuffDiagnostic]:
    """D1 on ``path`` (whose bytes are ``content``), run at most once per event per content.

    Every post-edit consumer computes the same ``codes``, ``config`` and
    ``preview`` for a path, so the key is ``(path, sha256(content))``: a changed
    file (after M1/M2) is a new key. ``preview`` codes get their own
    ``--preview`` call, its diagnostics added to D1's.

    Example::

        >>> ruff_diagnostics_for(runner, ctx.memo, "/r/a.py", data, ["B006"])  # doctest: +SKIP
        [RuffDiagnostic(code='B006', row=4, message='...')]
    """
    key = ("ruff-d1", path, hashlib.sha256(content).hexdigest())
    calls = [d1_args(path, codes, runner.pin.drop, config)]
    previewed = sorted(set(preview))
    if previewed:
        calls.append(preview_args(path, previewed, config))

    def run() -> list[RuffDiagnostic]:
        found: list[RuffDiagnostic] = []
        for args in calls:
            done = runner.run(args)
            if not done.ok:
                raise RuffFailure("error", "ruff check")
            found.extend(parse_diagnostics(done.stdout))
        return found

    return list(memo.get_or_compute(key, run))


# --- changed lines ---------------------------------------------------------------------------


def changed_lines(head_text: str | None, new_text: str) -> set[int]:
    """The 1-based lines of ``new_text`` an edit inserted or replaced relative to ``head_text``.

    ``None`` (no HEAD blob: a new or untracked file) means every line changed.

    Example::

        >>> sorted(changed_lines("a\\nb\\n", "a\\nB\\nc\\n"))
        [2, 3]
    """
    new_lines = new_text.splitlines()
    if head_text is None:
        return set(range(1, len(new_lines) + 1))
    import difflib  # the Python-edit branch only (§D.1)

    matcher = difflib.SequenceMatcher(None, head_text.splitlines(), new_lines, autojunk=False)
    return {
        line + 1
        for tag, _, _, start, end in matcher.get_opcodes()
        if tag in ("replace", "insert")
        for line in range(start, end)
    }
