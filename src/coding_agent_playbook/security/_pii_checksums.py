"""The arithmetic behind the PII detectors: Luhn, ISO 7064 mod-97, IBAN, NIR (specs/prK-hook-pack.md §E.5).

Pure integer arithmetic over strings, split out of :mod:`.pii` (which
re-exports every public name) so each module stays one read. An overlay's
``extra_detectors`` row names one of :data:`CHECKSUMS`; overlays ship data,
never code.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "CHECKSUMS",
    "IBAN_LENGTHS",
    "compact",
    "iban_valid",
    "is_alnum",
    "luhn_valid",
    "mod97_valid",
    "nir_valid",
]

#: ISO 13616 (SWIFT IBAN registry): country code -> IBAN length.
IBAN_LENGTHS: Final[Mapping[str, int]] = MappingProxyType(
    {
        **dict.fromkeys(("NO",), 15),
        **dict.fromkeys(("BE",), 16),
        **dict.fromkeys(("DK", "FI", "FK", "FO", "GL", "NL", "SD"), 18),
        **dict.fromkeys(("MK", "SI"), 19),
        **dict.fromkeys(("AT", "BA", "EE", "KZ", "LT", "LU", "MN", "XK"), 20),
        **dict.fromkeys(("CH", "HR", "LI", "LV"), 21),
        **dict.fromkeys(("BG", "BH", "CR", "DE", "GB", "GE", "IE", "ME", "RS", "VA"), 22),
        **dict.fromkeys(("AE", "GI", "IL", "IQ", "OM", "SO", "TL"), 23),
        **dict.fromkeys(("AD", "CZ", "ES", "MD", "PK", "RO", "SA", "SE", "SK", "TN", "VG"), 24),
        **dict.fromkeys(("LY", "PT", "ST"), 25),
        **dict.fromkeys(("IS", "TR"), 26),
        **dict.fromkeys(("BI", "DJ", "FR", "GR", "IT", "MC", "MR", "SM"), 27),
        **dict.fromkeys(
            ("AL", "AZ", "BY", "CY", "DO", "GT", "HN", "HU", "LB", "NI", "PL", "SV"), 28
        ),
        **dict.fromkeys(("BR", "EG", "PS", "QA", "UA"), 29),
        **dict.fromkeys(("JO", "KW", "MU", "YE"), 30),
        **dict.fromkeys(("MT", "SC"), 31),
        **dict.fromkeys(("LC",), 32),
        **dict.fromkeys(("RU",), 33),
    }
)


def luhn_valid(digits: str) -> bool:
    """Whether ``digits`` (ASCII digits only, at least two) passes the Luhn check.

    Example::

        >>> luhn_valid("79927398713"), luhn_valid("79927398710")
        (True, False)
    """
    if len(digits) < 2 or not (digits.isascii() and digits.isdigit()):
        return False
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def mod97_valid(text: str) -> bool:
    """ISO 7064 MOD 97-10 over ``text``'s alphanumerics (letters count as 10-35).

    Example::

        >>> mod97_valid("BNP-1197530767"), mod97_valid("1197530767")
        (False, True)
    """
    packed = compact(text)
    return bool(packed) and _mod97(packed) == 1


def iban_valid(s: str) -> bool:
    """Whether ``s`` (spaces allowed) is an IBAN: known country, its length, mod-97 of 1.

    Example::

        >>> iban_valid("GB82 WEST 1234 5698 7654 32"), iban_valid("GB83WEST12345698765432")
        (True, False)
    """
    packed = s.replace(" ", "").upper()
    if not (packed.isascii() and packed.isalnum()) or not packed[2:4].isdigit():
        return False
    if IBAN_LENGTHS.get(packed[:2]) != len(packed):
        return False
    return _mod97(packed[4:] + packed[:4]) == 1


def nir_valid(s: str) -> bool:
    """Whether ``s`` is a French NIR whose two-digit key is ``97 - (first 13 mod 97)``.

    Corsican departments ``2A`` / ``2B`` count as ``19`` / ``18`` (INSEE).

    Example::

        >>> nir_valid("1 84 02 75 123 456 74")
        True
    """
    packed = compact(s)
    if len(packed) != 15:
        return False
    department = {"2A": "19", "2B": "18"}.get(packed[5:7], packed[5:7])
    body, key = packed[:5] + department + packed[7:13], packed[13:]
    if not (body.isdigit() and key.isdigit()):
        return False
    return 1 <= int(key) <= 97 and int(key) == 97 - int(body) % 97


def _luhn_text(text: str) -> bool:
    return luhn_valid("".join(ch for ch in text if ch.isascii() and ch.isdigit()))


def _no_checksum(_text: str) -> bool:
    return True


#: The checksums an overlay ``extra_detectors`` row may name (data, never code).
CHECKSUMS: Final[Mapping[str, Callable[[str], bool]]] = MappingProxyType(
    {"luhn": _luhn_text, "mod97": mod97_valid, "nir": nir_valid, "none": _no_checksum}
)


def _mod97(alnum: str) -> int:
    """``alnum`` (ASCII alphanumerics) as an ISO 7064 number, mod 97."""
    return int("".join(str(int(ch, 36)) for ch in alnum)) % 97


def compact(value: str) -> str:
    """``value``'s ASCII alphanumerics, upper case: the form allowlists hold.

    Example::

        >>> compact("4111 1111-1111 1111"), compact("fr76 3000")
        ('4111111111111111', 'FR763000')
    """
    return "".join(ch for ch in value if is_alnum(ch)).upper()


def is_alnum(ch: str) -> bool:
    """Whether ``ch`` is one ASCII letter or digit (``str.isalnum`` alone takes ``²``).

    Example::

        >>> is_alnum("a"), is_alnum("²"), is_alnum("")
        (True, False, False)
    """
    return ch.isascii() and ch.isalnum()
