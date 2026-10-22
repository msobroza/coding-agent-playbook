"""``detect_smells.py`` on exception handlers: bare and swallowed excepts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.design_patterns._scripts import hits_of, line_of, scan_smells

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

EXCEPT_HANDLERS = """
    import builtins


    def load():
        try:
            return read()
        except:  # bare
            pass


    def quiet():
        try:
            risky()
        except Exception:  # pass-body
            pass


    def drain(items):
        for item in items:
            try:
                risky(item)
            except (ValueError, BaseException):  # continue-body
                continue


    def dotted():
        try:
            risky()
        except builtins.Exception:  # ellipsis-body
            ...


    def logged():
        try:
            risky()
        except Exception:
            log.warning("failed")


    def narrow():
        try:
            risky()
        except ValueError:
            pass
"""


def test_bare_except(detect: ModuleType, tmp_path: Path) -> None:
    found = hits_of(scan_smells(detect, tmp_path, EXCEPT_HANDLERS), "bare-except")
    assert found == [
        (
            line_of(EXCEPT_HANDLERS, "bare"),
            "bare 'except:' also catches KeyboardInterrupt and SystemExit",
        )
    ]


def test_swallowed_exception_only_for_broad_silent_handlers(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = hits_of(scan_smells(detect, tmp_path, EXCEPT_HANDLERS), "swallowed-exception")
    assert found == [
        (
            line_of(EXCEPT_HANDLERS, "pass-body"),
            "'except Exception' discards the error (body: pass)",
        ),
        (
            line_of(EXCEPT_HANDLERS, "continue-body"),
            "'except (ValueError, BaseException)' discards the error (body: continue)",
        ),
        (
            line_of(EXCEPT_HANDLERS, "ellipsis-body"),
            "'except builtins.Exception' discards the error (body: ...)",
        ),
    ]
