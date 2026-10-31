"""In-process tests of the scoring suite's record plugin (pytester).

Why in-process: eval scoring loads the plugin into the suite's subprocess, which
the engine's ``--cov-fail-under`` does not measure. Each test points the plugin's
record path at ``tmp_path`` and runs an inner pytest with ``-p`` and the plugin.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading.execution_metrics import suite_record_plugin
from coding_agent_playbook.grading.execution_metrics.suite_record import (
    SUITE_RECORD_ENV,
    SUITE_RECORD_PLUGIN,
)

if TYPE_CHECKING:
    from pathlib import Path

pytest_plugins = ["pytester"]


@pytest.fixture
def record_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where the plugin writes, as if eval scoring had set ``PLAYBOOK_SUITE_RECORD``."""
    path = tmp_path / "record" / "session.json"
    path.parent.mkdir()
    monkeypatch.setattr(suite_record_plugin, "_RECORD_PATH", str(path))
    return path


def _run(pytester: pytest.Pytester, record_path: Path, *args: str) -> dict[str, Any]:
    """Run the inner pytest with the plugin and return the record it wrote."""
    pytester.runpytest("-p", SUITE_RECORD_PLUGIN, "-p", "no:cacheprovider", *args)
    record: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
    return record


def _outcomes(record: dict[str, Any]) -> dict[str, tuple[str, bool]]:
    """``{test name: (outcome, xfail_strict)}`` with the module prefix dropped."""
    return {
        nodeid.split("::", 1)[1]: (entry["outcome"], entry["xfail_strict"])
        for nodeid, entry in record["outcomes"].items()
    }


def test_the_plugin_names_the_record_variable_the_reader_sets() -> None:
    assert suite_record_plugin._RECORD_ENV == SUITE_RECORD_ENV


def test_each_outcome_is_recorded_with_its_xfail_strictness(
    pytester: pytest.Pytester, record_path: Path
) -> None:
    pytester.makepyfile(
        test_outcomes="""
        import pytest

        @pytest.fixture
        def broken():
            raise RuntimeError("setup")

        def test_pass(): pass
        def test_fail(): assert False
        def test_error(broken): pass
        def test_skip(): pytest.skip("no")
        @pytest.mark.xfail(strict=True)
        def test_strict(): assert False
        @pytest.mark.xfail(strict=False)
        def test_lenient(): assert False
        @pytest.mark.xfail(strict=True)
        def test_imperative(): pytest.xfail("later")
        @pytest.mark.xfail(strict=False)
        def test_xpass(): pass
        @pytest.mark.xfail(False, strict=True, reason="off")
        @pytest.mark.xfail(strict=False)
        def test_mixed(): assert False
        """
    )

    record = _run(pytester, record_path)

    assert _outcomes(record) == {
        "test_pass": ("passed", False),
        "test_fail": ("failed", False),
        "test_error": ("error", False),
        "test_skip": ("skipped", False),
        "test_strict": ("xfailed", True),
        "test_lenient": ("xfailed", False),
        "test_imperative": ("xfailed", False),
        "test_xpass": ("xpassed", False),
        "test_mixed": ("xfailed", False),
    }
    assert record["exitstatus"] == 1
    assert (record["pid"], record["ppid"]) == (os.getpid(), os.getppid())
    assert len(record["finished"]) == 9


def test_the_ini_default_decides_an_unmarked_strictness(
    pytester: pytest.Pytester, record_path: Path
) -> None:
    pytester.makeini("[pytest]\nxfail_strict = true\n")
    pytester.makepyfile("import pytest\n@pytest.mark.xfail\ndef test_x(): assert False\n")

    assert _outcomes(_run(pytester, record_path)) == {"test_x": ("xfailed", True)}


def test_a_teardown_error_turns_a_pass_into_an_error(
    pytester: pytest.Pytester, record_path: Path
) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def leaky():
            yield
            raise RuntimeError("teardown")

        def test_x(leaky): pass
        """
    )

    assert _outcomes(_run(pytester, record_path)) == {"test_x": ("error", False)}


def test_deselection_leaves_the_collected_tests_but_not_the_run_set(
    pytester: pytest.Pytester, record_path: Path
) -> None:
    pytester.makeconftest(
        "def pytest_collection_modifyitems(items):\n"
        "    items[:] = [i for i in items if 'hidden' not in i.name]\n"
    )
    pytester.makepyfile(
        test_sel="def test_kept(): pass\ndef test_hidden(): pass\ndef test_other(): pass\n"
    )

    record = _run(pytester, record_path, "-k", "not other")

    names = {entry["nodeid"].split("::")[1] for entry in record["collected"]}
    assert names == {"test_kept", "test_hidden", "test_other"}
    assert record["selected"] == [{"nodeid": "test_sel.py::test_kept", "path": "test_sel.py"}]


def test_collector_skips_and_collection_errors_are_recorded(
    pytester: pytest.Pytester, record_path: Path
) -> None:
    pytester.makepyfile(
        test_skipmod="import pytest\npytest.importorskip('no_such_module_xyz')\n",
        test_broken="def test_x(:\n",
    )

    record = _run(pytester, record_path)

    assert record["collector_skips"] == [{"nodeid": "test_skipmod.py", "path": "test_skipmod.py"}]
    assert record["collection_errors"] == ["test_broken.py"]
    assert (record["selected"], record["exitstatus"]) == ([], 2)


def test_the_record_is_written_once_and_never_overwritten(
    pytester: pytest.Pytester, record_path: Path
) -> None:
    record_path.write_text("planted", encoding="utf-8")
    pytester.makepyfile("def test_x(): pass\n")

    pytester.runpytest("-p", SUITE_RECORD_PLUGIN)

    assert record_path.read_text(encoding="utf-8") == "planted"


def test_another_process_never_writes_the_record(
    pytester: pytest.Pytester, record_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forked child inherits the plugin; only the process that imported it writes."""
    monkeypatch.setattr(suite_record_plugin, "_PID", os.getpid() + 1)
    pytester.makepyfile("def test_x(): pass\n")

    pytester.runpytest("-p", SUITE_RECORD_PLUGIN)

    assert not record_path.exists()


def test_without_a_record_path_the_plugin_is_inert(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(suite_record_plugin, "_RECORD_PATH", None)
    pytester.makepyfile("def test_x(): pass\n")

    result = pytester.runpytest("-p", SUITE_RECORD_PLUGIN)

    assert result.ret == 0
    assert not list(pytester.path.rglob("*.json"))


def test_import_pops_the_variable_and_appends_the_cwd_to_sys_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The candidate's code must not find the path, and its root imports after the toolchain."""
    monkeypatch.setenv(SUITE_RECORD_ENV, str(tmp_path / "session.json"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    try:
        importlib.reload(suite_record_plugin)
        assert SUITE_RECORD_ENV not in os.environ
        recorded = suite_record_plugin._RECORD_PATH
        assert recorded == str(tmp_path / "session.json")
        assert sys.path[-1] == str(tmp_path)
    finally:
        monkeypatch.delenv(SUITE_RECORD_ENV, raising=False)
        importlib.reload(suite_record_plugin)
    assert suite_record_plugin._RECORD_PATH is None
