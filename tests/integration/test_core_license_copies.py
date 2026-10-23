"""CI gate: the vendored sources' MIT notices ship byte-identical, and only where they belong (D19).

Each core skill holding a source's text ships that source's notice as
``references/LICENSE.<source>``; whether a skill must ship one is the ATTRIBUTIONS
gate's job (``test_core_attributions.py``). This gate pins the bytes, and fails a
copy anywhere else under ``catalog/core/``: by its name, or by its content under
another name.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from tests._attributions import LICENSE_SHA256, license_copy_errors, write_tree
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_NOTICE = b"MIT License\n\nCopyright (c) 2026 Somebody\n"
_PINS = {"up-source": hashlib.sha256(_NOTICE).hexdigest()}


def _errors(tmp_path: Path, tree: dict[str, bytes]) -> list[str]:
    write_tree(tmp_path, tree)
    return license_copy_errors(tmp_path, _PINS)


def test_the_license_pins_are_d19s() -> None:
    assert dict(LICENSE_SHA256) == {
        "python-best-practices": "5f2aed106f011d7f40db3a248ada7456350188c72a2e3aa8768ef251415fdc5c",
        "python-clean-architecture": (
            "80c4860b8cedcb4efa41ef98e33e3e79a43314442444b3470c3d68cae66025f8"
        ),
        "simple-agent-api": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    }


def test_shipped_license_copies_are_byte_identical_and_in_place() -> None:
    errors = license_copy_errors(CORE_ROOT)
    assert errors == [], "\n".join(errors)


def test_a_copy_in_a_skill_references_dir_passes(tmp_path: Path) -> None:
    assert _errors(tmp_path, {"skills/s/references/LICENSE.up-source": _NOTICE}) == []


def test_a_changed_copy_fails(tmp_path: Path) -> None:
    tree = {"skills/s/references/LICENSE.up-source": _NOTICE.replace(b"2026", b"2027")}
    assert _errors(tmp_path, tree) == [
        "skills/s/references/LICENSE.up-source: not byte-identical to up-source's license"
    ]


@pytest.mark.parametrize(
    "rel",
    [
        "skills/s/LICENSE.up-source",
        "skills/s/references/deeper/LICENSE.up-source",
        "skills/s/rules/LICENSE.up-source",
        "prompts/LICENSE.up-source",
        "LICENSE.up-source",
    ],
)
def test_a_copy_anywhere_else_fails(tmp_path: Path, rel: str) -> None:
    assert _errors(tmp_path, {rel: _NOTICE}) == [
        f"{rel}: up-source's license copy belongs only at skills/<skill>/references/"
        "LICENSE.up-source"
    ]


def test_the_notice_under_another_name_fails(tmp_path: Path) -> None:
    tree = {"skills/s/references/LICENSE": _NOTICE, "skills/s/references/notice.md": _NOTICE}
    assert _errors(tmp_path, tree) == [
        "skills/s/references/LICENSE: up-source's license copy belongs only at "
        "skills/<skill>/references/LICENSE.up-source",
        "skills/s/references/notice.md: up-source's license copy belongs only at "
        "skills/<skill>/references/LICENSE.up-source",
    ]
