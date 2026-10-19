"""import-linter contract type: an underscore module is imported only from inside its own package.

ADR 0002 rule 2. A module is private to the package above its first underscore
segment: ``coding_agent_playbook.adapters._where_guidance`` is private to
``coding_agent_playbook.adapters``, and ``coding_agent_playbook.hook_runtime.handlers._shared.paths``
to ``coding_agent_playbook.hook_runtime.handlers``. Any module inside that package,
at any depth, may import it; nothing else may. Dunder names (``__init__``,
``__main__``) are not private. A root-level underscore module is private to the
engine as a whole, so every engine module may import it.

import-linter's built-in ``protected`` contract takes one fixed allow-list per
contract, so "its own package" would need one contract per package, kept in step
with every move by hand. This type derives the owner from the name instead.
pyproject.toml registers it as ``private_modules``;
tests/architecture/test_import_contracts.py runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from importlinter import Contract, ContractCheck, fields, output
from importlinter.application import contract_utils

if TYPE_CHECKING:
    from collections.abc import Iterable

    from grimp import ImportGraph
    from importlinter.domain.imports import ImportExpression, Module


@dataclass(frozen=True)
class PrivateImport:
    """One direct import of a private module from outside the package that owns it."""

    importer: str
    imported: str
    owner: str
    line_numbers: tuple[int, ...]


def _is_private_segment(segment: str) -> bool:
    is_dunder = segment.startswith("__") and segment.endswith("__")
    return segment.startswith("_") and not is_dunder


def private_owner(module: str) -> str | None:
    """The package ``module`` is private to, or ``None`` when no segment is private.

    Example::

        >>> private_owner("pkg.adapters._skill_writer.plan")
        'pkg.adapters'
        >>> private_owner("pkg.hook_runtime.__main__") is None
        True
    """
    segments = module.split(".")
    for index, segment in enumerate(segments[1:], start=1):
        if _is_private_segment(segment):
            return ".".join(segments[:index])
    return None


def is_inside(module: str, package: str) -> bool:
    """Whether ``module`` is ``package`` itself or one of its descendants.

    Example::

        >>> is_inside("pkg.adapters.base", "pkg.adapters"), is_inside("pkg.adapters_x", "pkg.adapters")
        (True, False)
    """
    return module == package or module.startswith(f"{package}.")


def _leaks_of(graph: ImportGraph, imported: str, owner: str) -> list[PrivateImport]:
    importers = graph.find_modules_that_directly_import(imported)
    leaks = []
    for importer in sorted(m for m in importers if not is_inside(m, owner)):
        details = graph.get_import_details(importer=importer, imported=imported)
        lines = tuple(sorted({detail["line_number"] for detail in details}))
        leaks.append(PrivateImport(importer, imported, owner, lines))
    return leaks


def find_private_imports(graph: ImportGraph, containers: Iterable[str]) -> list[PrivateImport]:
    """Every direct import, into a private module under ``containers``, from outside its owner.

    Example::

        >>> import grimp
        >>> graph = grimp.ImportGraph()
        >>> graph.add_import(importer="pkg.cli", imported="pkg.commands._helper")
        >>> [leak.importer for leak in find_private_imports(graph, ["pkg"])]
        ['pkg.cli']
    """
    roots = tuple(containers)
    leaks: list[PrivateImport] = []
    for imported in sorted(graph.modules):
        owner = private_owner(imported)
        if owner is not None and any(is_inside(imported, root) for root in roots):
            leaks.extend(_leaks_of(graph, imported, owner))
    return leaks


class PrivateModulesContract(Contract):
    """Underscore modules under ``containers`` are imported only from inside their owner.

    Options: ``containers`` (the packages whose private modules are checked), and
    ``ignore_imports`` / ``unmatched_ignore_imports_alerting`` /
    ``broken_contract_guidance`` with the built-in contracts' meaning: an ignored
    import that matches nothing fails by default.
    """

    containers = fields.ListField(subfield=fields.ModuleField())
    ignore_imports = fields.SetField(subfield=fields.ImportExpressionField(), required=False)
    unmatched_ignore_imports_alerting = fields.EnumField(
        contract_utils.AlertLevel, default=contract_utils.AlertLevel.ERROR
    )
    broken_contract_guidance = fields.TextField(required=False)

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        ignored = cast("set[ImportExpression] | None", self.ignore_imports)
        removal = contract_utils.remove_ignored_imports_and_report(
            graph=graph,
            ignore_imports=sorted(ignored or (), key=str),
            unmatched_alerting=cast(
                "contract_utils.AlertLevel", self.unmatched_ignore_imports_alerting
            ),
        )
        containers = cast("list[Module]", self.containers)
        leaks = find_private_imports(graph, (module.name for module in containers))
        output.verbose_print(
            verbose, f"{len(leaks)} private-module imports from outside their owner"
        )
        return ContractCheck(
            kept=not leaks,
            warnings=list(removal.warnings),
            ignored_import_count=removal.ignored_import_count,
            metadata={"leaks": leaks},
        )

    def render_broken_contract(self, check: ContractCheck) -> None:
        leaks = cast("list[PrivateImport]", check.metadata["leaks"])
        for leak in leaks:
            lines = ", ".join(map(str, leak.line_numbers))
            message = f"- {leak.importer} -> {leak.imported} (l.{lines}): private to {leak.owner}"
            output.print_error(message, bold=False)
        output.new_line()
        guidance = cast("str | None", self.broken_contract_guidance)
        contract_utils.render_broken_contract_guidance(guidance)
