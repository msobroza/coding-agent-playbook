"""PEP 503 names and dependency-name extraction (``_pep503``, specs/prK-hook-pack.md §E.4).

The detector, dependency-allowlist-guard and ``playbook check-deps`` compare
package names; one normalization makes ``Foo_Bar``, ``foo.bar`` and
``FOO-bar`` the same project everywhere. The pyproject tables themselves are
``_pyproject_deps``'s (``tests/unit/test_pyproject_deps.py``).
"""

from __future__ import annotations

import pytest

from coding_agent_playbook._pep503 import (
    canonical_name,
    requirement_name,
    requirement_names,
    split_requirement,
)


@pytest.mark.parametrize("name", ["Foo_Bar", "foo.bar", "FOO-bar", "foo__bar", "Foo-_.Bar"])
def test_canonical_name(name: str) -> None:
    assert canonical_name(name) == "foo-bar"


@pytest.mark.parametrize(
    "spec",
    [
        "foo-bar @ https://x/y.whl",
        "Foo.Bar[extra]>=1; python_version<'3.13'",
        "  foo_bar (>=1.0)",
        "FOO-BAR",
        "foo_bar~=2.1,!=2.1.3",
    ],
)
def test_requirement_name(spec: str) -> None:
    assert requirement_name(spec) == "foo-bar"


@pytest.mark.parametrize(
    "spec", ["", "   ", "git+https://example.com/x.git", "./local/pkg", "-e ."]
)
def test_requirement_name_is_empty_when_there_is_no_name(spec: str) -> None:
    assert requirement_name(spec) == ""


def test_split_requirement_keeps_the_raw_tail() -> None:
    assert split_requirement("Foo_Bar>=1.0") == ("foo-bar", ">=1.0")
    assert split_requirement("numpy [x] ; os_name == 'nt'") == ("numpy", " [x] ; os_name == 'nt'")


def test_requirement_names_handles_r_lines_and_wheel_filenames() -> None:
    text = """\
# pinned for CI
-r base.txt
--constraint constraints.txt
--index-url https://pypi.example/simple
Flask==3.0.0 \\
    --hash=sha256:abc
requests[socks]>=2  # inline comment
-e git+https://example.com/repo.git#egg=My_Tool
./dist/Local_Pkg-1.2.0-py3-none-any.whl
https://files.example/sdist/Other.Pkg-0.4.tar.gz
-e .
"""

    assert requirement_names(text) == frozenset(
        {"flask", "requests", "my-tool", "local-pkg", "other-pkg"}
    )
