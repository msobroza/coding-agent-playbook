"""The rules of the module-path rewrite script (specs/prT-package-layout.md 5.4.4).

Each rule runs on a small ``tmp_path`` repository in the target layout, with a
move map and files that still name the old layout (``module_moves_samples``).
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.architecture._module_moves_text import line_regions
from tests.architecture.module_moves import APPLY_HINT, MAP_DIR, apply, check, load_map
from tests.architecture.module_moves_samples import (
    AH1_NEW,
    AH1_OLD,
    AH1_TREE,
    FROZEN_ENTRIES,
    MIGRATION_RECORD_ROWS,
    N1_MAP,
    N2_MAP,
    N2_TREE,
    N3_N4_MAP,
    N3_N4_TREE,
    N12_MAP,
    N12_TREE,
    FakeFormatter,
    load_test_map,
    map_entry,
    read,
    repo_with,
)

if TYPE_CHECKING:
    from tests.architecture._module_moves_text import Line

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WRITER = {"src/coding_agent_playbook/toml_writer.py": "def dumps() -> str: ...\n"}


def test_import_rewrites_the_module_part(tmp_path: Path) -> None:
    source = """
        from coding_agent_playbook._toml import dumps  # the writer
        import coding_agent_playbook._toml as toml
    """
    repo = repo_with(tmp_path, {**_WRITER, "tests/test_a.py": source})
    formatter = FakeFormatter()

    changed = apply(repo, load_test_map(tmp_path, n01=N1_MAP), formatter=formatter)

    assert read(repo, "tests/test_a.py") == (
        "from coding_agent_playbook.toml_writer import dumps  # the writer\n"
        "import coding_agent_playbook.toml_writer as toml\n"
    )
    assert changed == [repo / "tests/test_a.py"]
    assert formatter.calls == [changed]


def test_from_import_splits_by_destination_and_keeps_aliases(tmp_path: Path) -> None:
    source = "from coding_agent_playbook.config import Config, ConfigError as CE\n"
    repo = repo_with(tmp_path, {**N2_TREE, "tests/test_a.py": source})
    moves = load_test_map(tmp_path, n02=N2_MAP)

    assert check(repo, moves) == [
        f"tests/test_a.py:1: {source.strip()} -> from coding_agent_playbook.config.model import"
        " Config; from coding_agent_playbook.config.schema import ConfigError as CE"
    ]
    apply(repo, moves, formatter=FakeFormatter())

    assert read(repo, "tests/test_a.py") == (
        "from coding_agent_playbook.config.model import Config\n"
        "from coding_agent_playbook.config.schema import ConfigError as CE\n"
    )


def test_submodule_import_keeps_the_local_name(tmp_path: Path) -> None:
    source = """
        from coding_agent_playbook import _toml
        from coding_agent_playbook import _toml as writer
        from coding_agent_playbook.harness import models
    """
    repo = repo_with(tmp_path, {**N12_TREE, **_WRITER, "tests/test_a.py": source})

    apply(repo, load_test_map(tmp_path, n01=N1_MAP, n12=N12_MAP), formatter=FakeFormatter())

    assert read(repo, "tests/test_a.py") == (
        "from coding_agent_playbook import toml_writer as _toml\n"
        "from coding_agent_playbook import toml_writer as writer\n"
        "from coding_agent_playbook.agent_harness import models\n"
    )


def test_type_checking_and_function_level_imports_keep_their_indentation(tmp_path: Path) -> None:
    source = """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from coding_agent_playbook.config import Config, ConfigError


        def load() -> None:
            from coding_agent_playbook.config import (
                Config,  # the model
            )
    """
    repo = repo_with(tmp_path, {**N2_TREE, "src/coding_agent_playbook/load.py": source})

    apply(repo, load_test_map(tmp_path, n02=N2_MAP), formatter=FakeFormatter())

    assert read(repo, "src/coding_agent_playbook/load.py") == textwrap.dedent(
        """\
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from coding_agent_playbook.config.model import Config
            from coding_agent_playbook.config.schema import ConfigError


        def load() -> None:
            from coding_agent_playbook.config.model import (
                Config,  # the model
            )
        """
    )


def test_relative_import_is_refused(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, {"src/coding_agent_playbook/a.py": "from ._toml import dumps\n"})

    with pytest.raises(ValueError, match=r"playbook/a\.py: line 1: relative import 'from \._toml"):
        check(repo, load_test_map(tmp_path, n01=N1_MAP))


def test_string_rewrites_module_attr_and_colon_forms(tmp_path: Path) -> None:
    writer = "import subprocess\n\n\ndef dumps() -> str: ...\n"
    source = """
        MODULE = "coding_agent_playbook._toml"
        TARGET = 'coding_agent_playbook._toml.subprocess.run'
        ENTRY = "coding_agent_playbook._toml:dumps"
        BUILT = f"coding_agent_playbook._toml.{MODULE}"
        PROSE = "see coding_agent_playbook._toml"
    """
    tree = {"src/coding_agent_playbook/toml_writer.py": writer, "tests/test_a.py": source}
    repo = repo_with(tmp_path, tree)

    apply(repo, load_test_map(tmp_path, n01=N1_MAP), formatter=FakeFormatter())

    assert read(repo, "tests/test_a.py") == textwrap.dedent(
        """\
        MODULE = "coding_agent_playbook.toml_writer"
        TARGET = 'coding_agent_playbook.toml_writer.subprocess.run'
        ENTRY = "coding_agent_playbook.toml_writer:dumps"
        BUILT = f"coding_agent_playbook._toml.{MODULE}"
        PROSE = "see coding_agent_playbook._toml"
        """
    )


def test_current_names_are_never_rewritten(tmp_path: Path) -> None:
    source = """
        from coding_agent_playbook.config import schema
        from coding_agent_playbook.config.schema import ConfigError

        SCHEMA = "coding_agent_playbook.config.schema"
        MODEL = "coding_agent_playbook.config.model.Config"
    """
    repo = repo_with(tmp_path, {**N2_TREE, "tests/test_a.py": source})
    moves = load_test_map(tmp_path, n02=N2_MAP)

    assert check(repo, moves) == []
    assert apply(repo, moves, formatter=FakeFormatter()) == []


def test_same_name_conversion_rewrites_stale_attributes(tmp_path: Path) -> None:
    source = """
        from coding_agent_playbook.config import Config

        PATCHED = "coding_agent_playbook.config.Config"
    """
    repo = repo_with(tmp_path, {**N2_TREE, "tests/test_a.py": source})

    lines = check(repo, load_test_map(tmp_path, n02=N2_MAP))

    assert lines == [
        "tests/test_a.py:1: coding_agent_playbook.config -> coding_agent_playbook.config.model",
        "tests/test_a.py:3: coding_agent_playbook.config.Config"
        " -> coding_agent_playbook.config.model.Config",
    ]


def test_same_name_conversion_rewrites_module_object_imports(tmp_path: Path) -> None:
    source = """
        from coding_agent_playbook import catalog
        import coding_agent_playbook.detector as detector

        catalog._PACKAGE_DIR
        detector.detect()
    """
    repo = repo_with(tmp_path, {**N3_N4_TREE, "tests/test_a.py": source})
    moves = load_test_map(tmp_path, n03=N3_N4_MAP)

    apply(repo, moves, formatter=FakeFormatter())

    assert read(repo, "tests/test_a.py") == textwrap.dedent(
        """\
        from coding_agent_playbook.catalog import roots as catalog
        from coding_agent_playbook.detector import facts as detector

        catalog._PACKAGE_DIR
        detector.detect()
        """
    )
    assert check(repo, moves) == []


def test_pyproject_rewrites_values_never_group_names(tmp_path: Path) -> None:
    pyproject = f"""
        [project.scripts]
        playbook = "coding_agent_playbook.cli:main"

        [project.entry-points."coding_agent_playbook.adapters"]
        agent_harness = "{AH1_OLD}:AgentHarnessAdapter"

        [tool.ruff]
        src = ["{AH1_OLD}"]

        [[tool.importlinter.contracts]]
        layers = ["agent_harness_adapter"]
        ignore_imports = ["{AH1_OLD} -> coding_agent_playbook.cli"]
    """
    tree = {
        **AH1_TREE,
        "src/coding_agent_playbook/cli.py": "def main() -> int: ...\n",
        "pyproject.toml": pyproject,
    }
    repo = repo_with(tmp_path, tree)

    lines = check(repo, load_test_map(tmp_path, ah1=map_entry("module", AH1_OLD, AH1_NEW)))

    # Line 4 (the group header), line 8 ([tool.ruff]) and line 11 (layers) stay.
    assert lines == [
        f"pyproject.toml:5: {AH1_OLD}:AgentHarnessAdapter -> {AH1_NEW}:AgentHarnessAdapter",
        f"pyproject.toml:12: {AH1_OLD} -> {AH1_NEW}",
    ]


@pytest.mark.parametrize(
    ("entry", "frozen"),
    [case[1:] for case in FROZEN_ENTRIES],
    ids=[case[0] for case in FROZEN_ENTRIES],
)
def test_frozen_names_are_refused(tmp_path: Path, entry: str, frozen: str) -> None:
    with pytest.raises(ValueError, match=r"frozen .*" + re.escape(frozen)):
        load_test_map(tmp_path, t01=entry)


def test_doc_rewrites_prefixed_forms_and_keeps_line_suffixes(tmp_path: Path) -> None:
    spec = """
        Uses `coding_agent_playbook._toml` (:mod:`coding_agent_playbook._toml`, `src/coding_agent_playbook/_toml.py:30`).
        Plain coding_agent_playbook._toml:dumps and coding_agent_playbook/_toml.py too.
        Renders in commands/_sync_render.py:12-20; the pack tests live in `tests/hooks/test_x.py`.
    """
    python = '''
        """Writes TOML (see `coding_agent_playbook._toml`)."""

        X = 1  # mirrors src/coding_agent_playbook/_toml.py
    '''
    sync_moves = """
        [[module]]
        pr = "A6"
        old = "coding_agent_playbook.commands._sync_render"
        new = "coding_agent_playbook.sync.render"

        [[path]]
        pr = "A13"
        old = "tests/hooks/"
        new = "tests/hook_runtime/handlers/"
    """
    tree = {
        **_WRITER,
        "src/coding_agent_playbook/sync/render.py": "",
        "tests/hook_runtime/handlers/test_x.py": "",
        "SPEC.md": spec,
        "src/coding_agent_playbook/a.py": python,
        ".github/workflows/ci.yml": "run: x  # see coding_agent_playbook._toml\nname: coding_agent_playbook._toml\n",
    }
    repo = repo_with(tmp_path, tree)

    apply(repo, load_test_map(tmp_path, n01=N1_MAP, a06=sync_moves), formatter=FakeFormatter())

    assert read(repo, "SPEC.md") == textwrap.dedent(
        """\
        Uses `coding_agent_playbook.toml_writer` (:mod:`coding_agent_playbook.toml_writer`, `src/coding_agent_playbook/toml_writer.py:30`).
        Plain coding_agent_playbook.toml_writer:dumps and coding_agent_playbook/toml_writer.py too.
        Renders in sync/render.py:12-20; the pack tests live in `tests/hook_runtime/handlers/test_x.py`.
        """
    )
    assert read(repo, "src/coding_agent_playbook/a.py") == textwrap.dedent(
        '''\
        """Writes TOML (see `coding_agent_playbook.toml_writer`)."""

        X = 1  # mirrors src/coding_agent_playbook/toml_writer.py
        '''
    )
    assert read(repo, ".github/workflows/ci.yml") == (
        "run: x  # see coding_agent_playbook.toml_writer\nname: coding_agent_playbook._toml\n"
    )


def test_doc_skips_keep_markers(tmp_path: Path) -> None:
    spec = """
        Use `coding_agent_playbook._toml`.
        <!-- module-moves: keep -->
        | Before | After |
        | `coding_agent_playbook._toml` | `src/coding_agent_playbook/_toml.py` |
        <!-- module-moves: end-keep -->
    """
    repo = repo_with(tmp_path, {**_WRITER, "SPEC.md": spec})
    moves = load_test_map(tmp_path, n01=N1_MAP)

    lines = check(repo, moves)

    assert lines == ["SPEC.md:1: coding_agent_playbook._toml -> coding_agent_playbook.toml_writer"]
    (repo / "SPEC.md").write_text("<!-- module-moves: keep -->\n_toml\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"SPEC\.md: line 1: a keep marker is never closed"):
        check(repo, moves)


def _real_lines(name: str) -> list[Line]:
    return line_regions((_REPO_ROOT / name).read_text(encoding="utf-8"))


def test_spec_history_has_keep_markers() -> None:
    spec = _real_lines("SPEC.md")
    top_list = [line for line in spec if line.text.startswith(("**Changelog**", "- **0."))]
    appendix = spec[next(line.number for line in spec if line.text == "## Changelog") - 1 :]
    rows = [
        line
        for line in _real_lines("MIGRATION.md")
        if any(row in line.text for row in MIGRATION_RECORD_ROWS)
    ]

    assert [line.text for line in top_list if line.region != "keep"] == []
    assert [line.text for line in appendix if line.region not in ("keep", "marker")] == [""]
    assert len(rows) == len(MIGRATION_RECORD_ROWS)
    assert [line.text for line in rows if line.region != "keep"] == []


def test_hook_runtime_harness_and_adapter_ids_stay(tmp_path: Path) -> None:
    # Line 3 is the SPEC §5.1 tree, where the bare `harness/` is hook_runtime's: a bare
    # one-segment directory cannot be placed, so it is reported, never rewritten.
    spec = """
        `coding_agent_playbook.harness.parser` and `src/coding_agent_playbook/harness/parser.py` moved.
        `coding_agent_playbook.hook_runtime.harness`, `hook_runtime/harness/`, the `agent_harness` adapter and `evals/` stay.
        │   │   ├── harness/                # per-harness payload parsers
    """
    tree = {
        **N12_TREE,
        "src/coding_agent_playbook/hook_runtime/__init__.py": "",
        "src/coding_agent_playbook/hook_runtime/harness/__init__.py": "",
        "src/coding_agent_playbook/evals/__init__.py": "",
        "tests/test_a.py": 'WIRE = "coding_agent_playbook.hook_runtime.harness"\n',
        "SPEC.md": spec,
    }
    repo = repo_with(tmp_path, tree)

    lines = check(repo, load_test_map(tmp_path, n12=N12_MAP))

    assert lines == [
        "SPEC.md:1: coding_agent_playbook.harness.parser -> coding_agent_playbook.agent_harness.parser",
        "SPEC.md:1: src/coding_agent_playbook/harness/parser.py"
        " -> src/coding_agent_playbook/agent_harness/parser.py",
        "review: SPEC.md:3: bare 'harness/'",
    ]


def test_bare_filenames_are_reported_not_rewritten(tmp_path: Path) -> None:
    rs1 = map_entry(
        "module", "coding_agent_playbook.renderer", "coding_agent_playbook.rendering.formats"
    )
    tree = {
        "src/coding_agent_playbook/rendering/__init__.py": "",
        "src/coding_agent_playbook/rendering/formats.py": "",
        "SPEC.md": "The renderer.py module (renderer.py:12), not rendering/renderer.pyi.\n",
        "tests/test_a.py": 'SAMPLE = "renderer.py"\n',
    }
    repo = repo_with(tmp_path, tree)
    moves = load_test_map(tmp_path, rs1=rs1)

    assert check(repo, moves) == [
        "review: SPEC.md:1: bare 'renderer.py'",
        "review: SPEC.md:1: bare 'renderer.py'",
        "review: tests/test_a.py:1: bare 'renderer.py'",
    ]
    assert apply(repo, moves, formatter=FakeFormatter()) == []


def test_apply_is_idempotent(tmp_path: Path) -> None:
    source = """
        from coding_agent_playbook import _toml
        from coding_agent_playbook.config import Config, ConfigError
        from coding_agent_playbook.harness.models import HarnessTree

        TARGET = "coding_agent_playbook.config.Config"
    """
    spec = "`coding_agent_playbook.harness.models` and `harness/models.py`\n"
    repo = repo_with(
        tmp_path, {**N2_TREE, **N12_TREE, **_WRITER, "tests/test_a.py": source, "SPEC.md": spec}
    )
    moves = load_test_map(tmp_path, n01=N1_MAP, n02=N2_MAP, n12=N12_MAP)
    formatter = FakeFormatter()

    first = apply(repo, moves, formatter=formatter)
    rewritten = {path: path.read_text(encoding="utf-8") for path in first}
    second = apply(repo, moves, formatter=formatter)

    assert first == [repo / "SPEC.md", repo / "tests/test_a.py"]
    assert second == []
    assert {path: path.read_text(encoding="utf-8") for path in first} == rewritten
    assert formatter.calls == [first]
    assert check(repo, moves) == []


def test_chained_moves_compose(tmp_path: Path) -> None:
    later = map_entry(
        "module",
        "coding_agent_playbook.agent_harness.models",
        "coding_agent_playbook.agent_harness.tree",
    )
    tree = {
        **AH1_TREE,
        "src/coding_agent_playbook/agent_harness/tree.py": "class HarnessTree: ...\n",
    }
    source = f"""
        from {AH1_OLD} import AgentHarnessAdapter
        from coding_agent_playbook.harness.models import HarnessTree
    """
    repo = repo_with(tmp_path, {**tree, "tests/test_a.py": source})
    # ah-1.toml sorts before n12.toml and x1.toml: resolution follows names, not file order,
    # and harness.models takes two hops (N12, then X1).
    ah1 = map_entry("module", AH1_OLD, AH1_NEW)
    moves = load_test_map(tmp_path, **{"ah-1": ah1, "n12": N12_MAP, "x1": later})

    apply(repo, moves, formatter=FakeFormatter())

    assert read(repo, "tests/test_a.py") == (
        "from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter\n"
        "from coding_agent_playbook.agent_harness.tree import HarnessTree\n"
    )


def test_migration_section_lists_public_moves(tmp_path: Path) -> None:
    unlisted = """
        [[module]]
        pr = "N3"
        old = "coding_agent_playbook.sources._hook_walk"
        new = "coding_agent_playbook.catalog._hook_walk"

        [[names]]
        pr = "N2"
        old = "coding_agent_playbook.config"
        new = "coding_agent_playbook.config.schema"
        names = ["_private_helper"]

        [[module]]
        pr = "A13"
        old = "tests.hooks"
        new = "tests.hook_runtime.handlers"
        package = true
    """
    migration = "# Migration guide\n\n<!-- module-moves:start -->\nold\n<!-- module-moves:end -->\n"
    repo = repo_with(tmp_path, {**N2_TREE, **_WRITER, "MIGRATION.md": migration})
    # N1's old path `_toml` is private, so out-of-tree code never imported it: no row.
    moves = load_test_map(tmp_path, n01=N1_MAP, n02=N2_MAP, x=unlisted)

    assert check(repo, moves) == [
        "MIGRATION.md:4: the module paths section -> regenerated from the move map"
    ]
    apply(repo, moves, formatter=FakeFormatter())

    assert read(repo, "MIGRATION.md") == (
        "# Migration guide\n\n<!-- module-moves:start -->\n"
        "<!-- Generated by `python -m tests.architecture.module_moves apply` from the move map"
        " in tests/architecture/move_map/: edit the map, not this table. -->\n"
        "| Old module path | New module path | Moved by |\n"
        "| --- | --- | --- |\n"
        "| `coding_agent_playbook.config` | `coding_agent_playbook.config.model` | N2 |\n"
        "| `coding_agent_playbook.config.ConfigError`"
        " | `coding_agent_playbook.config.schema.ConfigError` | N2 |\n"
        "<!-- module-moves:end -->\n"
    )
    assert check(repo, moves) == []


def test_tree_has_no_stale_module_paths() -> None:
    lines = check(_REPO_ROOT, load_map(_REPO_ROOT / MAP_DIR))

    stale = [line for line in lines if not line.startswith("review: ")]
    assert stale == [], "\n".join([*stale, APPLY_HINT])
