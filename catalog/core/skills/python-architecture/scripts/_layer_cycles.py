"""Find the import cycles ``layer_map.py`` reports; not run on its own.

Standard library only, Python 3.10 or later, like the script that imports it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from _layer_model import ImportEdge


def import_time_graph(modules: Iterable[str], edges: Iterable[ImportEdge]) -> dict[str, set[str]]:
    """Adjacency sets of the imports that run while a module is being imported."""
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for edge in edges:
        if edge.at_import_time:
            graph[edge.importer].add(edge.imported)
    return graph


def find_cycles(graph: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    """Return every group of two or more modules that reach one another, each sorted.

    Kosaraju's strongly connected components, iterative so deep graphs cannot overflow.

    >>> find_cycles({"a": {"b"}, "b": {"a"}, "c": {"a"}})
    (('a', 'b'),)
    """
    reverse = _reverse(graph)
    assigned: set[str] = set()
    groups: list[tuple[str, ...]] = []
    for node in reversed(_finish_order(graph)):
        if node in assigned:
            continue
        group = _reachable(node, reverse, assigned)
        assigned |= group
        if len(group) > 1:
            groups.append(tuple(sorted(group)))
    return tuple(sorted(groups))


def _reverse(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {node: set() for node in graph}
    for node, targets in graph.items():
        for target in targets:
            reverse[target].add(node)
    return reverse


def _finish_order(graph: dict[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for start in sorted(graph):
        if start not in seen:
            seen.add(start)
            _depth_first(start, graph, seen, order)
    return order


def _depth_first(start: str, graph: dict[str, set[str]], seen: set[str], order: list[str]) -> None:
    stack: list[tuple[str, Iterator[str]]] = [(start, iter(sorted(graph[start])))]
    while stack:
        node, children = stack[-1]
        child = next((name for name in children if name not in seen), None)
        if child is None:
            stack.pop()
            order.append(node)
            continue
        seen.add(child)
        stack.append((child, iter(sorted(graph[child]))))


def _reachable(start: str, graph: dict[str, set[str]], excluded: set[str]) -> set[str]:
    found = {start}
    stack = [start]
    while stack:
        fresh = graph[stack.pop()] - found - excluded
        found |= fresh
        stack.extend(fresh)
    return found
