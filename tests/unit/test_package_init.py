"""The package root stays import-light: ``__version__`` is lazy (specs/prK-lifecycle-hooks.md P-D1).

``importlib.metadata`` used to cost 69-190 ms of every ``import
coding_agent_playbook``, which the hook runtime pays on each tool call. The
version is now computed on first access through a PEP 562 module
``__getattr__`` and cached in the module globals.
"""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING

import pytest

import coding_agent_playbook
from tests.import_probe import new_modules_after, run_python_probe

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

_DISTRIBUTION = "coding-agent-playbook"
_MISSING = object()


class FakeDistributionVersion:
    """Stands in for :func:`importlib.metadata.version`; ``None`` = not installed."""

    def __init__(self, result: str | None) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, distribution_name: str) -> str:
        self.calls.append(distribution_name)
        if self.result is None:
            raise importlib.metadata.PackageNotFoundError(distribution_name)
        return self.result


@pytest.fixture
def uncached_package() -> Iterator[ModuleType]:
    """The package with no cached ``__version__``; the original state is restored after."""
    namespace = vars(coding_agent_playbook)
    saved = namespace.pop("__version__", _MISSING)
    try:
        yield coding_agent_playbook
    finally:
        namespace.pop("__version__", None)
        if saved is not _MISSING:
            namespace["__version__"] = saved


def test_import_does_not_load_importlib_metadata() -> None:
    probe = "import sys, coding_agent_playbook; print('importlib.metadata' in sys.modules)"
    assert run_python_probe(probe) == "False"


def test_import_loads_the_package_and_nothing_heavy() -> None:
    loaded = new_modules_after("import coding_agent_playbook", baseline="pass")
    assert "coding_agent_playbook" in loaded
    assert not [name for name in loaded if name.startswith(("importlib.metadata", "jinja2"))]


def test_version_resolves_from_metadata_and_is_cached_in_globals(
    uncached_package: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDistributionVersion("9.9.9")
    monkeypatch.setattr(importlib.metadata, "version", fake)

    assert uncached_package.__version__ == "9.9.9"
    assert uncached_package.__version__ == "9.9.9"
    assert fake.calls == [_DISTRIBUTION]
    assert vars(uncached_package)["__version__"] == "9.9.9"


def test_version_falls_back_to_local_without_distribution(
    uncached_package: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(importlib.metadata, "version", FakeDistributionVersion(None))
    assert uncached_package.__version__ == "0.0.0+local"


def test_version_matches_the_installed_distribution(uncached_package: ModuleType) -> None:
    assert uncached_package.__version__ == importlib.metadata.version(_DISTRIBUTION)


def test_from_import_of_version_still_works() -> None:
    from coding_agent_playbook import __version__

    assert isinstance(__version__, str)
    assert __version__


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no_such_attribute"):
        getattr(coding_agent_playbook, "no_such_attribute")  # noqa: B009
    assert not hasattr(coding_agent_playbook, "no_such_attribute")
