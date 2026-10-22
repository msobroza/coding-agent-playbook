#!/usr/bin/env python3
"""Sort a Python project's modules into layers and flag imports that point the wrong way.

Usage:
    python3 layer_map.py [ROOT] [--layer NAME=DIR1,DIR2 ...] [--allow NAME=DEP1,DEP2 ...]
                         [--root-module NAME ...] [--json]

Scans ROOT (default ".", or ROOT/src when that holds Python files) with ast; nothing is
imported or run. Hidden directories, __pycache__, venv, node_modules, site-packages and
test code (tests/, test/, test_*.py, *_test.py, conftest.py) are skipped.

A module's layer is the first (outermost) part of its dotted path that names a layer,
so shop/routers/carts.py and shop/routers.py are both interface code. A module that
matches nothing is unlayered and never checked. The defaults, and what each layer may
import besides itself:

    interface       api routers routes endpoints views cli      -> application, domain
    application     services operations use_cases usecases application   -> domain
    domain          domain models entities                      -> nothing
    infrastructure  db repositories adapters infrastructure infra persistence storage
                                                                -> application, domain

One exception: a container package is a name, not a layer. That is a package named
like a layer that holds packages or modules named after at least two other layers,
while no package beside it names another layer: a project packaged as api/ with
api/services/ and api/db/ inside, or the services/ package that encloses
ROOT=services/billing when that holds domain/ and db/.
Its own name is skipped, so api/db/session.py is infrastructure and api/config.py is
unlayered. Layer-first packages side by side (api/, services/, db/) stay layers. A
name with "/" is never a container, so adding api/models to a layer overrules one.

--layer NAME=DIR1,DIR2 replaces one layer's names or adds a layer (a name with "/",
such as shop/http, matches that run of path parts). --allow NAME=DEP1,DEP2 replaces
what one layer may import; a layer added without --allow may import only itself.
Repeat either flag once per layer.

Composition roots may import any layer: main.py, app.py, __main__.py, deps.py,
dependencies.py, container.py, bootstrap.py, wiring.py, cli.py, and each --root-module NAME
(a dotted module, a trailing part of one, or the path of a scanned file, absolute or
relative to the working directory, ROOT or the scanned directory). Only interface
modules may import a composition root (the provider module's aliases); any other
layered module that imports one is a rule violation, a service locator.

Absolute and relative imports are resolved to scanned modules; all others are ignored.
Imports under "if TYPE_CHECKING:" never fail the run; the ones that would break a rule
are listed under type_only. A cycle is a group of modules that import one another at
import time: module-level runtime imports, without type-only imports or imports made
inside a function body.

Output is text by default. --json prints one object: layers {module: layer}, flows
[[from_layer, to_layer, module_pairs]], violations [{importer, imported, from_layer,
to_layer, file, line}] (to_layer is null for an unlayered composition root), cycles
[[module, ...]], type_only (shaped like violations), plus scanned, rules,
composition_roots, container_packages and unlayered. Flows count distinct module
pairs between two different layers, composition roots left out.

Exit status: 0 nothing found, 1 a rule violation or an import cycle, 2 usage error,
including a --root-module that matches no scanned module and a ROOT with no module
to scan. Unreadable or unparseable files are reported on stderr and skipped. Findings
are candidates, not verdicts: layers are guessed from names, so confirm each one.

Examples:
    python3 layer_map.py
    python3 layer_map.py services/billing --json
    python3 layer_map.py . --layer interface=http,cli --allow infrastructure=domain
    python3 layer_map.py . --root-module shop.wiring

Standard library only; Python 3.10 or newer. The helper modules beside this script hold
its records and defaults (_layer_model.py), the file walk and import reading
(_layer_imports.py), the layer rules (_layer_rules.py) and the cycle search
(_layer_cycles.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# The helper modules sit beside this script: find them even under ``python -I`` (no script dir),
# and write no __pycache__ into the synced skill directory.
sys.dont_write_bytecode = True
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _layer_cycles import find_cycles, import_time_graph  # noqa: E402
from _layer_imports import collect_edges, discover_modules, scan_base  # noqa: E402
from _layer_model import UsageError  # noqa: E402
from _layer_rules import (  # noqa: E402
    breaks_rule,
    build_rules,
    classify,
    container_packages,
    find_roots,
    layer_flows,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from _layer_model import ImportEdge, LayerRules


@dataclass(frozen=True)
class LayerReport:
    """Everything the text and JSON renderers print."""

    scanned: Path
    rules: LayerRules
    paths: dict[str, Path]
    layers: dict[str, str]
    roots: tuple[str, ...]
    containers: tuple[str, ...]
    unlayered: tuple[str, ...]
    flows: tuple[tuple[str, str, int], ...]
    violations: tuple[ImportEdge, ...]
    type_only: tuple[ImportEdge, ...]
    cycles: tuple[tuple[str, ...], ...]

    @property
    def found_problems(self) -> bool:
        """True when the run should exit 1: a rule violation or an import cycle."""
        return bool(self.violations or self.cycles)


# --- the report ---------------------------------------------------------------------


def build_report(root: Path, rules: LayerRules) -> LayerReport:
    """Scan ROOT (or ROOT/src) and check every import against RULES.

    Raises UsageError when nothing is left to scan or a --root-module matches nothing.
    """
    scanned = scan_base(root)
    modules = discover_modules(scanned)
    if not modules:
        raise UsageError(
            f"found no Python module to scan under {scanned.as_posix()} (test code, hidden "
            "and vendored directories are skipped); pass the project or package directory"
        )
    roots = find_roots(modules, rules, root, scanned)
    containers = container_packages(modules, rules)
    layers = {n: layer for n in sorted(modules) if (layer := classify(n, rules, containers))}
    edges = collect_edges(modules)
    crossing = [edge for edge in edges if breaks_rule(edge, layers, roots, rules)]
    paths = {name: module.path for name, module in modules.items()}
    return LayerReport(
        scanned=scanned,
        rules=rules,
        paths=paths,
        layers=layers,
        roots=tuple(sorted(roots)),
        containers=tuple(sorted(".".join(package) for package in containers)),
        unlayered=tuple(sorted(set(modules) - set(layers))),
        flows=layer_flows(edges, layers, roots, rules),
        violations=_by_location([edge for edge in crossing if not edge.type_only], paths),
        type_only=_by_location([edge for edge in crossing if edge.type_only], paths),
        cycles=find_cycles(import_time_graph(modules, edges)),
    )


def _by_location(edges: list[ImportEdge], paths: dict[str, Path]) -> tuple[ImportEdge, ...]:
    return tuple(sorted(edges, key=lambda e: (paths[e.importer].as_posix(), e.line, e.imported)))


def to_json(report: LayerReport) -> dict[str, object]:
    """The --json payload; see the module docstring for its keys."""
    return {
        "scanned": report.scanned.as_posix(),
        "layers": report.layers,
        "flows": [list(flow) for flow in report.flows],
        "violations": [_edge_json(edge, report) for edge in report.violations],
        "cycles": [list(group) for group in report.cycles],
        "type_only": [_edge_json(edge, report) for edge in report.type_only],
        "rules": {
            layer: sorted(deps, key=report.rules.order)
            for layer, deps in report.rules.allowed.items()
        },
        "composition_roots": list(report.roots),
        "container_packages": list(report.containers),
        "unlayered": list(report.unlayered),
    }


def _edge_json(edge: ImportEdge, report: LayerReport) -> dict[str, object]:
    return {
        "importer": edge.importer,
        "imported": edge.imported,
        "from_layer": report.layers.get(edge.importer),
        "to_layer": report.layers.get(edge.imported),
        "file": report.paths[edge.importer].as_posix(),
        "line": edge.line,
    }


def render_text(report: LayerReport) -> str:
    """The human-readable report printed without --json."""
    sections = (
        _summary_text(report),
        _rules_text(report.rules),
        _layers_text(report),
        _flows_text(report),
        _edges_text("Rule violations", report.violations, report),
        _cycles_text(report.cycles),
        _edges_text(
            "Type-only imports (TYPE_CHECKING) that would break a rule, not failing",
            report.type_only,
            report,
        ),
        _closing_text(report),
    )
    return "\n\n".join(sections)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _summary_text(report: LayerReport) -> str:
    return (
        f"Layer map of {report.scanned.as_posix()}: {_plural(len(report.paths), 'module')}, "
        f"{len(report.layers)} layered, {len(report.unlayered)} unlayered, "
        f"{_plural(len(report.roots), 'composition root')}"
    )


def _rules_text(rules: LayerRules) -> str:
    width = max((len(layer) for layer in rules.patterns), default=0)
    lines = ["Rules (every layer may also import itself)"]
    for layer in rules.patterns:
        deps = sorted(rules.allowed.get(layer, frozenset()), key=rules.order)
        lines.append(f"  {layer.ljust(width)} -> {', '.join(deps) or 'nothing'}")
    return "\n".join(lines)


def _layers_text(report: LayerReport) -> str:
    lines = ["Layers"]
    for layer, patterns in report.rules.patterns.items():
        members = [module for module, name in report.layers.items() if name == layer]
        names = ", ".join("/".join(pattern) for pattern in patterns) or "no names"
        lines.append(f"  {layer} ({names}): {_plural(len(members), 'module')}")
        lines.extend(f"    {member}" for member in members)
    lines.append(f"  unlayered, not checked: {_plural(len(report.unlayered), 'module')}")
    lines.append(f"  composition roots, may import any layer: {', '.join(report.roots) or 'none'}")
    if report.containers:
        names = ", ".join(report.containers)
        lines.append(f"  container packages (named like a layer, holding other layers): {names}")
    return "\n".join(lines)


def _flows_text(report: LayerReport) -> str:
    lines = ["Flows between layers (distinct module pairs, composition roots left out)"]
    for source, target, count in report.flows:
        note = "" if report.rules.permits(source, target) else "  (breaks a rule)"
        lines.append(f"  {source} -> {target}: {count}{note}")
    if not report.flows:
        lines.append("  none")
    return "\n".join(lines)


def _edges_text(title: str, edges: Sequence[ImportEdge], report: LayerReport) -> str:
    lines = [f"{title}: {len(edges)}"]
    for edge in edges:
        where = f"{report.paths[edge.importer].as_posix()}:{edge.line}"
        source, target = report.layers[edge.importer], _target_label(edge.imported, report)
        lines.append(f"  {where}  {edge.importer} [{source}] imports {edge.imported} [{target}]")
    return "\n".join(lines)


def _target_label(module: str, report: LayerReport) -> str:
    # An imported composition root may have no layer of its own (a top-level deps.py).
    layer = report.layers.get(module)
    if module not in report.roots:
        return layer or "unlayered"
    return f"{layer}, composition root" if layer else "composition root"


def _cycles_text(cycles: Sequence[tuple[str, ...]]) -> str:
    lines = [f"Import cycles (modules that import one another at import time): {len(cycles)}"]
    lines.extend(f"  {', '.join(group)}" for group in cycles)
    return "\n".join(lines)


def _closing_text(report: LayerReport) -> str:
    if not report.found_problems:
        return "No rule violations or import cycles found."
    return (
        f"Found {_plural(len(report.violations), 'rule violation')} and "
        f"{_plural(len(report.cycles), 'import cycle')}. These are candidates: the layer map "
        "is inferred from directory names, so confirm each one, or describe the project "
        "with --layer, --allow and --root-module."
    )


# --- command line -------------------------------------------------------------------


def _existing_dir(text: str) -> Path:
    path = Path(text)
    if path.is_dir():
        return path
    hint = " (repeat --layer/--allow once per NAME=VALUE pair)" if "=" in text else ""
    raise UsageError(f"ROOT must be a directory, got {text!r}{hint}")


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface described in the module docstring."""
    parser = argparse.ArgumentParser(
        prog="layer_map.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("root", nargs="?", default=".", metavar="ROOT")
    parser.add_argument("--layer", action="append", default=[], metavar="NAME=DIR1,DIR2")
    parser.add_argument("--allow", action="append", default=[], metavar="NAME=DEP1,DEP2")
    parser.add_argument("--root-module", action="append", default=[], metavar="NAME")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; return 0 (clean) or 1 (violation or cycle). Usage errors exit 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = _existing_dir(args.root)
        rules = build_rules(args.layer, args.allow, args.root_module)
        report = build_report(root, rules)
    except UsageError as error:
        parser.error(str(error))
    print(json.dumps(to_json(report), indent=2) if args.json else render_text(report))
    return 1 if report.found_problems else 0


if __name__ == "__main__":
    sys.exit(main())
