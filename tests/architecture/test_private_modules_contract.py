"""The ``private_modules`` import-linter contract type (ADR 0002 rule 2), on in-memory graphs."""

from __future__ import annotations

import grimp
import pytest
from importlinter.domain.helpers import MissingImport

from tests.architecture.private_modules_contract import (
    PrivateImport,
    PrivateModulesContract,
    find_private_imports,
    is_inside,
    private_owner,
)


def _graph(*imports: tuple[str, str]) -> grimp.ImportGraph:
    graph = grimp.ImportGraph()
    for importer, imported in imports:
        graph.add_import(importer=importer, imported=imported, line_number=1, line_contents="")
    return graph


def _contract(**options: object) -> PrivateModulesContract:
    return PrivateModulesContract(
        name="private", session_options={}, contract_options={"containers": ["pkg"], **options}
    )


@pytest.mark.parametrize(
    ("module", "owner"),
    [
        ("pkg._toml", "pkg"),
        ("pkg.adapters._skill_writer", "pkg.adapters"),
        ("pkg.hook_runtime.handlers._shared.paths", "pkg.hook_runtime.handlers"),
        ("pkg.adapters.base", None),
        ("pkg.hook_runtime.__main__", None),
    ],
)
def test_private_owner_is_the_package_above_the_first_underscore(
    module: str, owner: str | None
) -> None:
    assert private_owner(module) == owner


def test_is_inside_matches_whole_segments_only() -> None:
    assert is_inside("pkg.adapters", "pkg.adapters")
    assert is_inside("pkg.adapters.claude.paths", "pkg.adapters")
    assert not is_inside("pkg.adapters_extra", "pkg.adapters")


def test_an_import_from_inside_the_owner_is_kept() -> None:
    graph = _graph(
        ("pkg.adapters.claude.paths", "pkg.adapters._json_edits"), ("pkg.x", "pkg._toml")
    )

    assert find_private_imports(graph, ["pkg"]) == []


def test_an_import_from_outside_the_owner_is_reported_with_its_lines() -> None:
    graph = _graph(("pkg.commands.sync", "pkg.adapters._skill_writer"))

    assert find_private_imports(graph, ["pkg"]) == [
        PrivateImport("pkg.commands.sync", "pkg.adapters._skill_writer", "pkg.adapters", (1,))
    ]


def test_a_sibling_subpackage_is_outside_the_owner() -> None:
    graph = _graph(("pkg.hook_runtime.dispatch", "pkg.hook_runtime.harness._payload"))

    [leak] = find_private_imports(graph, ["pkg"])

    assert leak.owner == "pkg.hook_runtime.harness"


def test_a_private_module_outside_the_containers_is_not_checked() -> None:
    graph = _graph(("pkg.cli", "other._private"))

    assert find_private_imports(graph, ["pkg"]) == []


def test_the_contract_breaks_on_a_leak_and_keeps_once_it_is_ignored() -> None:
    def check(**options: object) -> bool:
        graph = _graph(("pkg.cli", "pkg.commands._init_adapters"))
        return _contract(**options).check(graph, verbose=False).kept

    assert not check()
    assert check(ignore_imports=["pkg.cli -> pkg.commands._init_adapters"])


def test_the_check_counts_the_ignored_imports() -> None:
    graph = _graph(("pkg.cli", "pkg.commands._a"), ("pkg.cli", "pkg.commands._b"))

    check = _contract(ignore_imports=["pkg.cli -> pkg.commands.*"]).check(graph, verbose=False)

    assert (check.kept, check.ignored_import_count) == (True, 2)


def test_an_ignored_import_that_matches_nothing_fails() -> None:
    graph = _graph(("pkg.cli", "pkg.commands.sync"))

    with pytest.raises(MissingImport, match="No matches for ignored import"):
        _contract(ignore_imports=["pkg.cli -> pkg.commands._gone"]).check(graph, verbose=False)


def test_render_names_each_leak_and_the_guidance(capsys: pytest.CaptureFixture[str]) -> None:
    contract = _contract(broken_contract_guidance="Import a public module instead.")
    check = contract.check(_graph(("pkg.cli", "pkg.commands._init_adapters")), verbose=False)

    contract.render_broken_contract(check)

    out = capsys.readouterr().out
    assert "pkg.cli -> pkg.commands._init_adapters (l.1): private to pkg.commands" in out
    assert "Import a public module instead." in out
