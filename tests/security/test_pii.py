"""The PII detector library (specs/prK-hook-pack.md §E.5, ``security/pii.py``).

Table-driven over pure functions, no I/O: checksums (ISO 13616 length plus
mod-97, Luhn, the NIR key), the four named detectors and their sanity rules,
the published test-value allowlist, overlay ``extra_detectors`` with a named
checksum, the chunked scan's boundary overlap, and masks that never hold the
value. Check digits are computed here with independent arithmetic, so no
fixture value depends on the code under test.
"""

from __future__ import annotations

import re
import sys

import pytest

from coding_agent_playbook.security.pii import (
    CHECKSUMS,
    DEFAULT_PII_CONFIG,
    PII_DETECTORS,
    PiiConfig,
    PiiMatch,
    category_counts,
    iban_valid,
    luhn_valid,
    mask,
    nir_valid,
    pii_config,
    scan_pii,
)
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after

ALL_NAMED = PiiConfig(detectors=tuple(PII_DETECTORS))


def _iban(country: str, bban: str) -> str:
    """A valid IBAN for ``bban``: ISO 13616 check digits, ``98 - n mod 97``."""
    digits = "".join(str(int(ch, 36)) for ch in f"{bban}{country}00")
    return f"{country}{98 - int(digits) % 97:02d}{bban}"


def _luhn_digit(body: str) -> str:
    """The Luhn check digit that completes ``body``."""
    total = 0
    for index, ch in enumerate(reversed(body)):
        value = int(ch) * (2 if index % 2 == 0 else 1)
        total += value - 9 if value > 9 else value
    return str((10 - total % 10) % 10)


def _grouped(value: str, sizes: tuple[int, ...], sep: str = " ") -> str:
    parts, start = [], 0
    for size in sizes:
        parts.append(value[start : start + size])
        start += size
    return sep.join(parts)


FR_IBAN = _iban("FR", "30006000011234567890189")
VISA = "453914880343646" + _luhn_digit("453914880343646")
AMEX = "37612345678901" + _luhn_digit("37612345678901")
NIR_BODY = "1840275123456"
NIR = f"{NIR_BODY}{97 - int(NIR_BODY) % 97:02d}"


def _found(text: str, cfg: PiiConfig = ALL_NAMED) -> list[tuple[str, str]]:
    return [(m.detector, text[m.start : m.end]) for m in scan_pii(text, cfg)]


# --- checksums ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("iban", "valid"),
    [
        ("GB82WEST12345698765432", True),
        ("GB82 WEST 1234 5698 7654 32", True),
        ("DE89370400440532013000", True),
        (FR_IBAN, True),
        (FR_IBAN.lower(), True),
        ("GB83WEST12345698765432", False),  # check digits off by one
        ("DE893704004405320130001", False),  # one character too long for DE (22)
        (_iban("ZZ", "1234567890123"), False),  # no such country in ISO 13616
        ("GB82-WEST-1234-5698-7654-32", False),  # only spaces may group an IBAN
        ("", False),
    ],
)
def test_iban_mod97_and_country_length(iban: str, valid: bool) -> None:
    assert iban_valid(iban) is valid


@pytest.mark.parametrize(
    ("digits", "valid"),
    [
        ("4111111111111111", True),
        ("79927398713", True),
        (VISA, True),
        ("4111111111111112", False),
        ("7992739871", False),
        ("12a4", False),
        ("4", False),
        ("", False),
    ],
)
def test_luhn_valid_and_invalid(digits: str, valid: bool) -> None:
    assert luhn_valid(digits) is valid


def test_nir_key_and_corsican_departments() -> None:
    corsica = "184022A123456"
    key = 97 - int(corsica.replace("2A", "19")) % 97

    assert nir_valid(NIR)
    assert nir_valid(f"{corsica}{key:02d}")
    assert not nir_valid(f"{NIR[:-2]}{(int(NIR[-2:]) % 97) + 1:02d}")
    assert not nir_valid(NIR[:-1])


# --- the named detectors --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "found"),
    [
        (f"card {_grouped(VISA, (4, 4, 4, 4))} exp", [("card_pan", _grouped(VISA, (4, 4, 4, 4)))]),
        (f"card {VISA}.", [("card_pan", VISA)]),
        (
            f"card {_grouped(VISA, (4, 4, 4, 4), '-')}",
            [("card_pan", _grouped(VISA, (4,) * 4, "-"))],
        ),
        (f"amex {_grouped(AMEX, (4, 6, 5))}", [("card_pan", _grouped(AMEX, (4, 6, 5)))]),
        (f"odd {_grouped(VISA, (5, 5, 5, 1))}", []),  # no card is grouped 5-5-5-1
        (f"mixed {VISA[:4]} {VISA[4:8]}-{VISA[8:12]} {VISA[12:]}", []),  # two separators
        (f"bad {VISA[:-1]}{(int(VISA[-1]) + 1) % 10}", []),  # Luhn fails
        ("iin 9" + "12345678901234" + _luhn_digit("912345678901234"), []),  # no 9-prefix network
        ("visa15 4" + "1234567890123" + _luhn_digit("41234567890123"), []),  # Visa is 13/16/19
        (f"long {VISA}1234", []),  # a 20-digit run is not a card
    ],
)
def test_card_pan_requires_luhn_grouping_and_iin(text: str, found: list[tuple[str, str]]) -> None:
    assert _found(text) == found


def test_iban_detector_takes_its_country_length_and_stops() -> None:
    spaced = _grouped(FR_IBAN, (4, 4, 4, 4, 4, 4, 3))
    text = f"wire to {spaced} PLEASE, or GB82WEST12345698765433 today"

    assert _found(text, PiiConfig(detectors=("iban",))) == [("iban", spaced)]


def test_fr_nir_and_us_ssn_detectors() -> None:
    spaced_nir = f"{NIR[0]} {NIR[1:3]} {NIR[3:5]} {NIR[5:7]} {NIR[7:10]} {NIR[10:13]} {NIR[13:]}"
    text = (
        f"nir {spaced_nir}; ssn 123-45-6789; not 000-12-3456, 666-12-3456, "
        "900-12-3456, 123-00-4567 or 123-45-0000; famous 078-05-1120"
    )

    assert _found(text) == [("fr_nir", spaced_nir), ("us_ssn", "123-45-6789")]


def test_published_test_values_allowlisted() -> None:
    published = (
        "4111 1111 1111 1111, 4242424242424242, 5555-5555-5555-4444, "
        "GB82 WEST 1234 5698 7654 32 and DE89370400440532013000"
    )
    assert _found(published) == []

    config = pii_config({"detectors": ["iban"], "test_value_allowlist": [FR_IBAN.lower()]})
    assert _found(f"sandbox {FR_IBAN}", config) == []
    assert _found(f"sandbox {FR_IBAN}", PiiConfig(detectors=("iban",))) == [("iban", FR_IBAN)]


def test_default_config_is_the_engine_library_pair() -> None:
    assert DEFAULT_PII_CONFIG.detectors == ("iban", "card_pan")
    assert pii_config({}).detectors == ("iban", "card_pan")
    assert pii_config({"detectors": []}).detectors == ()
    assert scan_pii(f"{FR_IBAN} {VISA}", pii_config({"detectors": []})) == []


# --- overlay rows ---------------------------------------------------------------------------


def test_extra_detector_uses_named_checksum() -> None:
    valid_id = 97 * 12345678 + 1  # ISO 7064 MOD 97-10: the number is 1 mod 97
    config = pii_config(
        {
            "detectors": [],
            "extra_detectors": [
                {"name": "bank_customer_id", "pattern": r"\bBNP-(\d{10})\b", "checksum": "mod97"},
                {"name": "loyalty_card", "pattern": r"\bLC(\d{12})\b", "checksum": "luhn"},
                {"name": "desk_code", "pattern": r"\bDESK-[0-9]{3}\b", "checksum": "none"},
            ],
        }
    )
    loyalty = "79927398713" + "0"
    loyalty = loyalty[:-1] + _luhn_digit(loyalty[:-1])
    text = (
        f"BNP-{valid_id} BNP-{valid_id + 1} LC{loyalty} "
        f"LC{loyalty[:-1]}{(int(loyalty[-1]) + 1) % 10} DESK-042"
    )

    found = _found(text, config)

    # The checksum applies to the first group, which is also what is masked.
    assert found == [
        ("bank_customer_id", str(valid_id)),
        ("loyalty_card", loyalty),
        ("desk_code", "DESK-042"),
    ]
    assert set(CHECKSUMS) == {"luhn", "mod97", "nir", "none"}


@pytest.mark.parametrize(
    ("table", "needle"),
    [
        (
            {"extra_detectors": [{"name": "acct", "pattern": r"\d+", "checksum": "crc32"}]},
            "'crc32'",
        ),
        ({"detectors": ["email"]}, "'email'"),
        ({"detectors": "iban"}, "'iban'"),
        ({"extra_detectors": [{"name": "Bad Name", "pattern": "x", "checksum": "none"}]}, "Bad"),
        ({"extra_detectors": [{"name": "iban", "pattern": "x", "checksum": "none"}]}, "'iban'"),
        ({"extra_detectors": [{"name": "nest", "pattern": "(a+)+$", "checksum": "none"}]}, "(a+)+"),
        ({"extra_detectors": ["BNP-\\d+"]}, "BNP"),
        ({"test_value_allowlist": [4111]}, "4111"),
    ],
)
def test_unknown_checksum_name_is_rejected_with_value(
    table: dict[str, object], needle: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(needle)):
        pii_config(table)


# --- the chunked scan -----------------------------------------------------------------------


def test_chunked_scan_finds_match_spanning_chunk_boundary() -> None:
    chunk = 1024
    spaced = _grouped(VISA, (4, 4, 4, 4))
    head = "x " * ((chunk - 8) // 2)
    text = f"{head}{spaced} tail " + "y " * chunk + f"{FR_IBAN}"

    matches = scan_pii(text, DEFAULT_PII_CONFIG, chunk_chars=chunk)

    assert [(m.detector, m.start) for m in matches] == [
        ("card_pan", len(head)),
        ("iban", len(text) - len(FR_IBAN)),
    ]
    assert matches[0].start < chunk < matches[0].end  # it straddles the boundary
    assert scan_pii(text, DEFAULT_PII_CONFIG) == matches  # one chunk: the same answer


def test_chunk_boundary_inside_a_digit_run_finds_no_card() -> None:
    """A window that starts mid-run must not read the run's tail as a card.

    The second chunk's window opens 256 characters before 1024, exactly where
    the card digits start: alone they are a valid card, but the run began earlier.
    """
    text = "z" * 700 + "9" * 68 + VISA + " " + "w" * 400

    assert scan_pii(text, DEFAULT_PII_CONFIG, chunk_chars=1024) == []
    assert scan_pii(text, DEFAULT_PII_CONFIG) == []


def test_chunk_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="0"):
        scan_pii("x", DEFAULT_PII_CONFIG, chunk_chars=0)


# --- masks and counts -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (FR_IBAN, "FR" + "*" * 23 + FR_IBAN[-2:]),
        (_grouped(VISA, (4, 4, 4, 4)), "**** **** **** **" + VISA[-2:]),
        (NIR, "*" * 13 + NIR[-2:]),
        ("123-45-6789", "***-**-**89"),
    ],
)
def test_masked_form_never_contains_value(text: str, shown: str) -> None:
    (match,) = scan_pii(text, ALL_NAMED)

    masked = mask(match)

    assert masked == shown
    assert match.value not in masked
    assert "".join(ch for ch in match.value if ch.isalnum()) not in masked
    assert match.value not in repr(match)


def test_short_extra_value_is_masked_entirely() -> None:
    match = PiiMatch("desk_code", 0, 7, "DESK-42")

    assert mask(match) == "****-**"


def test_category_counts_are_sorted_per_detector() -> None:
    text = f"{VISA} {FR_IBAN} {VISA[:-1]}{VISA[-1]}"

    assert category_counts(scan_pii(text)) == {"card_pan": 2, "iban": 1}


def test_pii_module_is_import_light() -> None:
    loaded = new_modules_after("import coding_agent_playbook.security.pii")

    foreign = [
        name
        for name in loaded
        if not name.startswith(engine_module("coding_agent_playbook.security"))
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    assert not {"jinja2", "yaml", "tomllib", "json"} & set(loaded)
    assert [name for name in loaded if name.startswith("coding_agent_playbook")] == [
        "coding_agent_playbook.security",
        "coding_agent_playbook.security._pii_checksums",
        "coding_agent_playbook.security.pii",
    ]
