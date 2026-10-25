"""Trees of every symlink shape ``os.path.realpath`` treats specially, for path-resolution tests.

``build_link_zoo`` lays out a symlinked leaf and parent, a chain, dangling links,
loops (a file linking to itself too), ``..`` inside and after a link, odd slashes,
links to the root and to ``.``/``..``; ``random_link_tree`` adds seeded random
trees. ``link_zoo_queries`` spells each entry several ways: as is, case-swapped
(the default macOS filesystem ignores case), below a missing parent, through
``..`` and through links. The characterization tests of every batch-resolving
call site compare against the old per-path implementation over these paths;
``relinkable_outputs`` and ``relink_directory`` stage a write between two calls,
which proves each call's batch memo dies with it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

#: link name -> target, every shape ``realpath`` treats specially.
ZOO_LINKS: dict[str, str] = {
    "file_link": "d1/d2/d3/file.txt",  # symlinked leaf, relative target
    "dir_link": "d1/d2",  # symlinked parent directory
    "chain1": "chain2",  # a chain of links
    "chain2": "chain3",
    "chain3": "d1",
    "dangling": "missing/target",
    "loop_a": "loop_b",  # a two-link loop
    "loop_b": "loop_a",
    "self": "self",  # a file linking to itself
    "into_loop": "loop_a/x",
    "up_link": "d1/d2/..",  # ".." inside a target
    "d1/back": "../..",  # a link to an ancestor
    "d1/d2/sib": "../../dir_link/d3",  # a link through another link
    "odd_slashes": "d1//d2/",
    "loop_dotdot": "loop_dotdot/../d1",  # realpath's lexical ".." after a loop
    "loop_slashes": "loop_slashes///",
    "to_root": "/",
    "dot": ".",
    "dotdot": "..",
    "file_parent": "d1/d2/d3/file.txt/x",  # ENOTDIR inside a target
}

#: Appended to every entry: missing leaves and parents, "..", and walks through links.
SUFFIXES: tuple[str, ...] = (
    "missing",
    "missing/deeper",
    "..",
    "../d1",
    "x/../y",
    "d2",
    "d2/d3/file.txt",
    "d3/deep/er/leaf.md",
    "file.txt",
)


def build_link_zoo(root: Path) -> None:
    """Lay out real dirs and files under ``root`` plus one link of each :data:`ZOO_LINKS` shape.

    Example: ``build_link_zoo(tmp_path)`` then ``tmp_path / "dir_link" / "d3"`` reaches
    ``tmp_path / "d1" / "d2" / "d3"``.
    """
    deep = root / "d1" / "d2" / "d3"
    (deep / "deep" / "er").mkdir(parents=True)
    (deep / "file.txt").write_text("x", encoding="utf-8")
    (deep / "deep" / "er" / "leaf.md").write_text("x", encoding="utf-8")
    (root / "Upper").mkdir()
    (root / "Upper" / "Mixed.md").write_text("x", encoding="utf-8")
    for name, target in ZOO_LINKS.items():
        (root / name).symlink_to(target)
    (root / "abs_link").symlink_to(deep / "file.txt")  # symlinked leaf, absolute target
    (root / "abs_dotdot").symlink_to(root / "dir_link" / ".." / "d1")  # ".." after a link


def tree_entries(root: Path) -> list[Path]:
    """``root`` and everything below it, links listed but never followed.

    Example: ``tree_entries(tmp_path)[0] == tmp_path``.
    """
    found = [root]
    for dirpath, dirnames, filenames in os.walk(root):
        found.extend(Path(dirpath, name) for name in [*dirnames, *filenames])
    return found


def path_variants(entry: Path) -> list[Path]:
    """``entry``, its case-swapped spelling, and ``entry`` joined with every :data:`SUFFIXES`.

    Example: ``path_variants(Path("/r/Ab"))[1] == Path("/r/aB")``.
    """
    swapped = entry.with_name(entry.name.swapcase()) if entry.name else entry
    return [entry, swapped, *(entry / suffix for suffix in SUFFIXES)]


def link_zoo_queries(root: Path) -> list[Path]:
    """Every spelling a resolution test asks for: each entry's variants, plus paths outside ``root``.

    Example: ``link_zoo_queries(tmp_path)`` includes ``tmp_path / "self" / "missing"``.
    """
    queries = [variant for entry in tree_entries(root) for variant in path_variants(entry)]
    outside = [Path("/"), Path("//"), Path("//tmp"), Path("/.."), Path("/tmp/x")]
    return [*queries, *outside, Path(tempfile.gettempdir()) / "x"]


def relinkable_outputs(root: Path) -> list[Path]:
    """Paths below ``root/out`` (two files and a missing leaf), each file twinned below ``root/other``.

    :func:`relink_directory` then turns ``out`` into a link to ``other``.
    Example: ``relinkable_outputs(tmp_path)[0] == tmp_path / "out" / "g.md"``.
    """
    for top in ("out", "other"):
        (root / top / "a" / "b").mkdir(parents=True)
        for name in ("g.md", "a/b/f.md"):
            (root / top / name).write_text(top, encoding="utf-8")
    return [root / "out" / name for name in ("g.md", "a/b/f.md", "a/missing.md")]


def relink_directory(directory: Path, target: Path) -> None:
    """Move ``directory`` aside and make its name a link to ``target``, as a user relinking it.

    Done between two batch-resolving calls, it is the filesystem write no batch
    memo may span: a memo kept from the first call would still resolve paths
    below ``directory`` into the moved directory. Example:
    ``relink_directory(tmp_path / "out", tmp_path / "other")``.
    """
    directory.rename(directory.with_name(f"{directory.name}.moved"))
    directory.symlink_to(target, target_is_directory=True)


def _random_target(rng: random.Random, link: Path, nodes: list[Path]) -> str:
    """A target ``realpath`` must follow: a node (relative or absolute), a miss, or a jumble."""
    node = rng.choice(nodes)
    jumble = "/".join(rng.choice(["..", ".", "", "n1", "n3", "n7", "x"]) for _ in range(4))
    choices = [
        os.path.relpath(node, link.parent),
        str(node),
        f"{os.path.relpath(node, link.parent)}/missing",
        jumble.strip("/") or "..",
        link.name,
    ]
    return rng.choice(choices)


def random_link_tree(root: Path, rng: random.Random) -> list[Path]:
    """Thirty random nodes under ``root``: directories, files, and links with random targets.

    Returns ``root`` and the nodes in creation order. Example:
    ``random_link_tree(tmp_path, random.Random(3))``.
    """
    dirs, nodes = [root], [root]
    for index in range(30):
        path = rng.choice(dirs) / f"n{index}"
        kind = rng.choice(("dir", "dir", "file", "link", "link", "link"))
        if kind == "dir":
            path.mkdir()
            dirs.append(path)
        elif kind == "file":
            path.write_text("", encoding="utf-8")
        else:
            path.symlink_to(_random_target(rng, path, nodes))
        nodes.append(path)
    return nodes


def random_tree_queries(nodes: list[Path], rng: random.Random) -> list[Path]:
    """Each node's :func:`path_variants`, plus each node joined with two random node names.

    Example: ``random_tree_queries(random_link_tree(tmp_path, rng), rng)``.
    """
    names = [node.name for node in nodes if node.name]
    queries = [variant for node in nodes for variant in path_variants(node)]
    return [*queries, *(node / rng.choice(names) / rng.choice(names) for node in nodes)]
