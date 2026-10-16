"""Checksum-validated PII detectors: one library for every PII consumer (specs/prK-hook-pack.md §E.5).

pii-prompt-guard (prompts), stop-diff-sweep's PII tier and ``playbook
scan-secrets --pii`` (files), local-audit-log (category counts) and
precompact-checkpoint (masking re-injected prompts) all call
:func:`scan_pii`, so they agree on what PII is. A regex alone flags too much,
so every detector confirms its candidate arithmetically:

- ``iban``: the ISO 13616 country length table plus the mod-97 check;
- ``card_pan``: Luhn, a known card grouping and a plausible IIN for the length;
- ``fr_nir``: the INSEE key (``97 - n mod 97``, Corsica's 2A/2B as 19/18);
- ``us_ssn``: the dashed form minus the never-issued areas, groups and serials.

The engine default is the library pair ``iban`` and ``card_pan``; an overlay
names more, and adds org identifiers as data: a regex plus one of the named
:data:`CHECKSUMS` (overlays ship no code). Published test values (``4111 1111
1111 1111``, the ISO example IBANs) never count. A :class:`PiiMatch` keeps its
value only for :func:`mask` and out of its ``repr``; every report shows the
category, offset and masked form. Large inputs are scanned in chunks whose
windows overlap, so a value straddling a chunk boundary is still found whole.
Stdlib ``re`` and integer arithmetic only (the checksums live in
:mod:`._pii_checksums`, re-exported here): no import beyond the stdlib at load.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.security._pii_checksums import (
    CHECKSUMS,
    IBAN_LENGTHS,
    compact,
    iban_valid,
    is_alnum,
    luhn_valid,
    mod97_valid,
    nir_valid,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    #: A detector: every validated match in ``text``, offsets relative to it.
    type Detector = Callable[[str], list[PiiMatch]]

__all__ = [
    "CHECKSUMS",
    "CHUNK_CHARS",
    "DEFAULT_DETECTORS",
    "DEFAULT_PII_CONFIG",
    "IBAN_LENGTHS",
    "OVERLAP_CHARS",
    "PII_DETECTORS",
    "TEST_VALUE_ALLOWLIST",
    "ExtraDetector",
    "PiiConfig",
    "PiiMatch",
    "category_counts",
    "iban_valid",
    "luhn_valid",
    "mask",
    "mod97_valid",
    "nir_valid",
    "pii_config",
    "scan_pii",
]

#: A scan reads at most this many characters per window (plus the overlaps).
CHUNK_CHARS: Final = 64 * 1024
#: Context on each side of a chunk: longer than any value a detector accepts,
#: so a value that crosses a chunk boundary lies whole inside one window.
OVERLAP_CHARS: Final = 256
#: The engine library proper; NIR, SSN and org identifiers are overlay choices.
DEFAULT_DETECTORS: Final = ("iban", "card_pan")
_MASK: Final = "*"
#: Masks keep the last two characters only of a value this long or longer.
_SHOWN_TAIL_MIN: Final = 8
_NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,39}")

#: Published test values, compacted (alphanumerics, upper case): card-network
#: sandbox PANs, the ISO 13616 example IBANs and SSNs famous for being invalid.
TEST_VALUE_ALLOWLIST: Final = frozenset(
    {
        "4111111111111111",
        "4242424242424242",
        "4012888888881881",
        "4000056655665556",
        "5555555555554444",
        "5105105105105100",
        "5200828282828210",
        "2223003122003222",
        "378282246310005",
        "371449635398431",
        "6011111111111117",
        "6011000990139424",
        "3530111333300000",
        "30569309025904",
        "38520000023237",
        "GB82WEST12345698765432",
        "DE89370400440532013000",
        "078051120",
        "219099999",
    }
)


@dataclass(frozen=True, slots=True)
class PiiMatch:
    """One validated PII value: which detector, where, how long.

    ``value`` exists only for :func:`mask` and the allowlist; it is out of
    ``repr``, and no report may print it.

    Example::

        >>> m = PiiMatch("us_ssn", 4, 15, "123-45-6789")
        >>> (m.length, mask(m))
        (11, '***-**-**89')
    """

    detector: str
    start: int
    end: int
    value: str = field(repr=False)

    @property
    def length(self) -> int:
        """The match's length in characters."""
        return self.end - self.start


# --- the named detectors --------------------------------------------------------------------

_IBAN_START: Final = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}")
_PAN: Final = re.compile(r"(?<![0-9])[0-9](?:[ -]?[0-9]){12,18}(?![0-9])")
_PAN_SEPARATORS: Final = re.compile(r"[ -]")
#: Group sizes a printed card uses (4-4-4-4[-n], Amex 4-6-5, Diners 4-6-4).
_PAN_GROUPINGS: Final = frozenset(
    {
        (4, 4, 4, 1),
        (4, 4, 4, 3),
        (4, 4, 4, 4),
        (4, 4, 4, 4, 1),
        (4, 4, 4, 4, 2),
        (4, 4, 4, 4, 3),
        (4, 6, 5),
        (4, 6, 4),
    }
)
_ANY_LENGTH: Final = frozenset(range(14, 20))
_LONG: Final = frozenset(range(16, 20))
#: (prefix digits, lowest, highest, card lengths) per network: Visa, Mastercard,
#: Amex, Diners, JCB, Discover, UnionPay. Anything else is not a card.
_IIN_RANGES: Final = (
    (1, 4, 4, frozenset({13, 16, 19})),
    (2, 51, 55, frozenset({16})),
    (4, 2221, 2720, frozenset({16})),
    (2, 34, 34, frozenset({15})),
    (2, 37, 37, frozenset({15})),
    (3, 300, 305, _ANY_LENGTH),
    (2, 36, 36, _ANY_LENGTH),
    (2, 38, 39, _ANY_LENGTH),
    (4, 3528, 3589, _LONG),
    (4, 6011, 6011, _LONG),
    (3, 644, 649, _LONG),
    (2, 65, 65, _LONG),
    (2, 62, 62, _LONG),
)
_NIR: Final = re.compile(
    r"(?<![0-9A-Za-z])[12] ?[0-9]{2} ?(?:0[1-9]|1[0-2]|[2-9][0-9]) ?(?:[0-9]{2}|2[ABab])"
    r" ?[0-9]{3} ?[0-9]{3} ?[0-9]{2}(?![0-9A-Za-z])"
)
_SSN: Final = re.compile(r"(?<![0-9-])([0-9]{3})-([0-9]{2})-([0-9]{4})(?![0-9-])")


def _ibans(text: str) -> list[PiiMatch]:
    """IBANs: a country code and check digits, then exactly that country's length."""
    found = []
    for start in (m.start() for m in _IBAN_START.finditer(text)):
        length = IBAN_LENGTHS.get(text[start : start + 2])
        end = None if length is None else _alnum_run_end(text, start, length)
        if end is not None and iban_valid(text[start:end]):
            found.append(PiiMatch("iban", start, end, text[start:end]))
    return found


def _alnum_run_end(text: str, start: int, count: int) -> int | None:
    """Where ``count`` alphanumerics from ``start`` end (single inner spaces allowed).

    ``None`` when the run is shorter, or goes on without a space after them.
    """
    index, taken, size = start, 0, len(text)
    while taken < count:
        if index < size and is_alnum(text[index]):
            taken += 1
        elif not (text[index : index + 1] == " " and is_alnum(text[index + 1 : index + 2])):
            return None
        index += 1
    return None if is_alnum(text[index : index + 1]) else index


def _pan_ok(candidate: str) -> bool:
    digits = "".join(ch for ch in candidate if ch.isdigit())
    return _grouped(candidate) and _iin_ok(digits) and luhn_valid(digits)


def _grouped(candidate: str) -> bool:
    """One separator kind at most, in a grouping real cards are printed with."""
    if len(set(_PAN_SEPARATORS.findall(candidate))) > 1:
        return False
    groups = tuple(len(group) for group in _PAN_SEPARATORS.split(candidate))
    return len(groups) == 1 or groups in _PAN_GROUPINGS


def _iin_ok(digits: str) -> bool:
    return any(
        low <= int(digits[:width]) <= high and len(digits) in lengths
        for width, low, high, lengths in _IIN_RANGES
    )


def _ssn_ok(candidate: str) -> bool:
    area, group, serial = candidate.split("-")
    return area not in ("000", "666") and area[0] != "9" and group != "00" and serial != "0000"


def _regex_detector(name: str, regex: re.Pattern[str], valid: Callable[[str], bool]) -> Detector:
    def find(text: str) -> list[PiiMatch]:
        return [
            PiiMatch(name, m.start(), m.end(), m.group())
            for m in regex.finditer(text)
            if valid(m.group())
        ]

    return find


#: The engine's named detectors; overlays pick from these by name.
PII_DETECTORS: Final[Mapping[str, Detector]] = MappingProxyType(
    {
        "iban": _ibans,
        "card_pan": _regex_detector("card_pan", _PAN, _pan_ok),
        "fr_nir": _regex_detector("fr_nir", _NIR, nir_valid),
        "us_ssn": _regex_detector("us_ssn", _SSN, _ssn_ok),
    }
)


# --- configuration --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtraDetector:
    """An overlay data row: ``name``, a regex and a named checksum.

    The checksum applies to the pattern's first group when it has one (also
    the span reported and masked), else to the whole match.

    Example::

        >>> row = ExtraDetector("acct", re.compile(r"ACCT-(\\d{10})"), "mod97")
        >>> [m.value for m in row.find("ACCT-1197530767")]
        ['1197530767']
    """

    name: str
    regex: re.Pattern[str]
    checksum: str

    def find(self, text: str) -> list[PiiMatch]:
        """Every match of the row in ``text`` whose checksum holds."""
        valid = CHECKSUMS[self.checksum]
        group = 1 if self.regex.groups else 0
        found = []
        for m in self.regex.finditer(text):
            start, end = m.span(group)
            if 0 <= start < end and valid(text[start:end]):
                found.append(PiiMatch(self.name, start, end, text[start:end]))
        return found


@dataclass(frozen=True, slots=True)
class PiiConfig:
    """Which detectors run and which extra values are test data.

    ``allowlist`` holds compacted values (see :data:`TEST_VALUE_ALLOWLIST`,
    which always applies). Raises ``ValueError`` naming an unknown detector.

    Example::

        >>> PiiConfig(detectors=("iban", "fr_nir")).detectors
        ('iban', 'fr_nir')
    """

    detectors: tuple[str, ...] = DEFAULT_DETECTORS
    extra: tuple[ExtraDetector, ...] = ()
    allowlist: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        unknown = [name for name in self.detectors if name not in PII_DETECTORS]
        if unknown:
            raise ValueError(
                f"unknown PII detector {unknown[0]!r}; known: {', '.join(PII_DETECTORS)}"
            )

    def finders(self) -> list[Detector]:
        """The detector functions to run, named ones first."""
        return [*(PII_DETECTORS[name] for name in self.detectors), *(x.find for x in self.extra)]


DEFAULT_PII_CONFIG: Final = PiiConfig()


def pii_config(table: Mapping[str, object]) -> PiiConfig:
    """A :class:`PiiConfig` from a hook's config table (``detectors``, ``extra_detectors``,
    ``test_value_allowlist``); an absent ``detectors`` is the engine pair.

    Raises ``ValueError`` carrying the offending value: an unknown detector or
    checksum, a bad row, or a regex ``security.secrets.screen_regex`` rejects.

    Example::

        >>> pii_config({"detectors": ["iban"], "test_value_allowlist": ["FR76..."]}).detectors
        ('iban',)
    """
    names = _strings(table.get("detectors", list(DEFAULT_DETECTORS)), "detectors")
    rows = table.get("extra_detectors", [])
    if not isinstance(rows, list | tuple):
        raise ValueError(f"extra_detectors must be a list of rows, got {rows!r}")
    allow = _strings(table.get("test_value_allowlist", []), "test_value_allowlist")
    return PiiConfig(
        detectors=tuple(names),
        extra=tuple(_extra_detector(index, row) for index, row in enumerate(rows)),
        allowlist=frozenset(compact(value) for value in allow),
    )


def _strings(value: object, key: str) -> list[str]:
    if not isinstance(value, list | tuple) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{key} must be a list of strings, got {value!r}")
    return list(value)


def _extra_detector(index: int, row: object) -> ExtraDetector:
    where = f"extra_detectors[{index}]"
    if not isinstance(row, dict):
        raise ValueError(f"{where} must be a {{name, pattern, checksum}} table, got {row!r}")
    name, pattern, checksum = row.get("name"), row.get("pattern"), row.get("checksum", "none")
    if not isinstance(name, str) or not _NAME.fullmatch(name) or name in PII_DETECTORS:
        raise ValueError(f"{where}.name must be a new snake_case category, got {name!r}")
    if checksum not in CHECKSUMS:
        known = ", ".join(sorted(CHECKSUMS))
        raise ValueError(f"{where} {name!r}: unknown checksum {checksum!r}; known: {known}")
    if not isinstance(pattern, str):
        raise ValueError(f"{where} {name!r}: pattern must be a string, got {pattern!r}")
    from coding_agent_playbook.security.secrets import screen_regex  # only overlay rows pay

    problem = screen_regex(pattern)
    if problem is not None:
        raise ValueError(f"{where} {name!r}: {problem}")
    return ExtraDetector(name, re.compile(pattern), checksum)


# --- scanning -------------------------------------------------------------------------------


def scan_pii(
    text: str, cfg: PiiConfig = DEFAULT_PII_CONFIG, *, chunk_chars: int = CHUNK_CHARS
) -> list[PiiMatch]:
    """Every PII value ``cfg`` detects in ``text``, minus test values, in text order.

    The text is read in ``chunk_chars`` windows that overlap by
    :data:`OVERLAP_CHARS` on each side; a match is kept by the chunk it starts
    in, so none is lost at a boundary or reported twice.

    Example::

        >>> [m.detector for m in scan_pii("pay GB33BUKB20201555555555")]
        ['iban']
    """
    if chunk_chars <= 0:
        raise ValueError(f"chunk_chars must be positive, got {chunk_chars}")
    finders = cfg.finders()
    allowed = TEST_VALUE_ALLOWLIST | cfg.allowlist
    found: dict[tuple[int, int, str], PiiMatch] = {}
    for low in range(0, len(text), chunk_chars) if finders else ():
        for match in _chunk_matches(text, low, low + chunk_chars, finders):
            if compact(match.value) not in allowed:
                found.setdefault((match.start, match.end, match.detector), match)
    return sorted(found.values(), key=lambda m: (m.start, m.end, m.detector))


def _chunk_matches(
    text: str, low: int, high: int, finders: Sequence[Detector]
) -> Iterator[PiiMatch]:
    """Matches starting in ``[low, high)``, found in the chunk's overlapping window."""
    window_low, window_high = max(0, low - OVERLAP_CHARS), min(len(text), high + OVERLAP_CHARS)
    window = text[window_low:window_high]
    for find in finders:
        for match in find(window):
            start, end = match.start + window_low, match.end + window_low
            truncated = end == window_high < len(text)  # it may run past the window
            if low <= start < high and not truncated:
                yield PiiMatch(match.detector, start, end, match.value)


def mask(match: PiiMatch) -> str:
    """``match``'s value with its alphanumerics starred; separators stay.

    Only the last two characters of a value of eight or more remain, plus an
    IBAN's country code, so a mask never contains the value.

    Example::

        >>> mask(PiiMatch("card_pan", 0, 19, "4539 1488 0343 6467"))
        '**** **** **** **67'
    """
    value = match.value
    positions = [index for index, ch in enumerate(value) if is_alnum(ch)]
    kept = set(positions[-2:]) if len(positions) >= _SHOWN_TAIL_MIN else set()
    if match.detector == "iban":
        kept.update(positions[:2])
    return "".join(
        ch if index in kept or not is_alnum(ch) else _MASK for index, ch in enumerate(value)
    )


def category_counts(matches: Iterable[PiiMatch]) -> dict[str, int]:
    """How many matches each detector produced, by detector name.

    Example::

        >>> category_counts(scan_pii("GB33BUKB20201555555555"))
        {'iban': 1}
    """
    counts: dict[str, int] = {}
    for match in matches:
        counts[match.detector] = counts.get(match.detector, 0) + 1
    return dict(sorted(counts.items()))
