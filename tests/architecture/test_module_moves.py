"""Module-move contracts exercised through the public rewrite API (PR T0.0)."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.architecture.module_moves import (
    ModuleMove,
    MoveMap,
    NameMove,
    PathMove,
    apply,
    check,
    load_map,
)


class FakeFormatter:
    """Record the formatting boundary without changing the rewrite under test."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, paths: list[Path]) -> None:
        self.paths.extend(paths)


def write(repo: Path, name: str, source: str) -> Path:
    """Create one fixture file; for example write(repo, 'README.md', 'Guide')."""
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_import_rewrites_the_module_part(tmp_path: Path) -> None:
    write(tmp_path, "src/sample/new_writer.py", "dump = 1\n")
    source = write(tmp_path, "tests/use.py", "import sample.old_writer as writer\n")
    moves = MoveMap((ModuleMove("N1", "sample.old_writer", "sample.new_writer"),), ())
    assert check(tmp_path, moves) == ["tests/use.py:1: sample.old_writer -> sample.new_writer"]
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == [source]
    assert source.read_text() == "import sample.new_writer as writer\n"
    assert check(tmp_path, moves) == []


def test_empty_map_loads_and_changes_nothing(tmp_path: Path) -> None:
    map_dir = tmp_path / "tests/architecture/move_map"
    map_dir.mkdir(parents=True)
    moves = load_map(map_dir)
    assert moves.modules == ()
    assert moves.names == ()
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == []
    assert check(tmp_path, moves) == []


def test_chained_moves_compose(tmp_path: Path) -> None:
    write(
        tmp_path,
        "map/z.toml",
        '[[module]]\npr="first"\nold="sample.old"\nnew="sample.middle"\npackage=true\n',
    )
    write(
        tmp_path,
        "map/a.toml",
        '[[module]]\npr="second"\nold="sample.middle"\nnew="sample.final"\npackage=true\n',
    )
    moves = load_map(tmp_path / "map")
    assert moves.resolve("sample.old.leaf.Name", tmp_path) == "sample.final.leaf.Name"
    assert moves.resolve("sample.final.leaf.Name", tmp_path) is None


@pytest.mark.parametrize(
    "old",
    [
        "coding_agent_playbook.hook_runtime",
        "coding_agent_playbook.hook_runtime.cli",
        "coding_agent_playbook.cli",
        "coding_agent_playbook.adapters.base",
    ],
)
def test_frozen_names_are_refused(tmp_path: Path, old: str) -> None:
    write(tmp_path, "map/one.toml", f'[[module]]\npr="bad"\nold="{old}"\nnew="sample.new"\n')
    with pytest.raises(ValueError, match=old):
        load_map(tmp_path / "map")


@pytest.mark.parametrize(
    "entries",
    [
        '[[module]]\npr="bad"\nold="sample.old"\nnew="sample.old.new"\npackage=true\n',
        '[[module]]\npr="one"\nold="sample.old"\nnew="sample.new"\n[[module]]\npr="two"\nold="sample.old"\nnew="sample.other"\n',
        '[[module]]\npr="one"\nold="sample.old"\nnew="sample.new"\n[[module]]\npr="two"\nold="sample.new"\nnew="sample.old"\n',
    ],
)
def test_map_rejects_ambiguous_or_non_idempotent_entries(tmp_path: Path, entries: str) -> None:
    write(tmp_path, "map/one.toml", entries)
    with pytest.raises(ValueError, match="sample"):
        load_map(tmp_path / "map")


def test_current_names_are_never_rewritten(tmp_path: Path) -> None:
    write(tmp_path, "src/sample/config/__init__.py", '"""Config package."""\n')
    write(tmp_path, "src/sample/config/schema.py", "class Config: pass\n")
    moves = MoveMap((ModuleMove("N2", "sample.config", "sample.config.schema"),), ())
    assert moves.resolve("sample.config.schema", tmp_path) is None
    assert moves.resolve("sample.config.schema.Config", tmp_path) is None


def test_same_name_conversion_rewrites_stale_attributes(tmp_path: Path) -> None:
    write(tmp_path, "src/sample/config/__init__.py", '"""Config package."""\n')
    write(tmp_path, "src/sample/config/schema.py", "class Config: pass\n")
    moves = MoveMap((), (NameMove("N2", "sample.config", "sample.config.schema", ("Config",)),))
    assert moves.resolve("sample.config.Config", tmp_path) == "sample.config.schema.Config"


def test_from_import_splits_by_destination_and_keeps_aliases(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tests/use.py",
        "from sample.old import (\n    First as One,  # keep first\n    Second,  # keep second\n)  # keep trailing\n",
    )
    moves = MoveMap(
        (),
        (
            NameMove("one", "sample.old", "sample.first", ("First",)),
            NameMove("two", "sample.old", "sample.second", ("Second",)),
        ),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    result = source.read_text()
    assert "from sample.first import" in result and "First as One" in result
    assert "from sample.second import" in result and "Second" in result
    for comment in ("# keep first", "# keep second", "# keep trailing"):
        assert result.count(comment) == 1


def test_submodule_import_keeps_the_local_name(tmp_path: Path) -> None:
    source = write(
        tmp_path, "tests/use.py", "from sample import old\nfrom sample import old as writer\n"
    )
    write(tmp_path, "src/sample/new.py", "value = 1\n")
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert source.read_text() == "from sample import new as old\nfrom sample import new as writer\n"


def test_type_checking_and_function_level_imports_keep_their_indentation(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tests/use.py",
        "if TYPE_CHECKING:\n    from sample.old import First, Second\ndef load():\n    from sample.old import First, Second\n",
    )
    moves = MoveMap(
        (),
        (
            NameMove("one", "sample.old", "sample.first", ("First",)),
            NameMove("two", "sample.old", "sample.second", ("Second",)),
        ),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        source.read_text()
        == "if TYPE_CHECKING:\n    from sample.first import First\n    from sample.second import Second\ndef load():\n    from sample.first import First\n    from sample.second import Second\n"
    )


def test_relative_import_is_refused(tmp_path: Path) -> None:
    source = write(tmp_path, "tests/use.py", "from .module import Name\n")
    with pytest.raises(ValueError, match="relative import"):
        apply(tmp_path, MoveMap((), ()), formatter=FakeFormatter())
    assert source.read_text() == "from .module import Name\n"


def test_same_name_conversion_rewrites_module_object_imports(tmp_path: Path) -> None:
    write(tmp_path, "src/sample/catalog/__init__.py", '"""Catalog."""\n')
    write(tmp_path, "src/sample/catalog/roots.py", "VALUE = 1\n")
    source = write(
        tmp_path, "tests/use.py", "from sample import catalog\nimport sample.catalog as catalog\n"
    )
    moves = MoveMap((ModuleMove("one", "sample.catalog", "sample.catalog.roots"),), ())
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        source.read_text()
        == "from sample.catalog import roots as catalog\nfrom sample.catalog import roots as catalog\n"
    )
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == []


def test_string_rewrites_module_attr_and_colon_forms(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tests/use.py",
        'module = "sample.old"\nattr = "sample.old.Name"\nentry = "sample.old:Name"\n',
    )
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        source.read_text()
        == 'module = "sample.new"\nattr = "sample.new.Name"\nentry = "sample.new:Name"\n'
    )


def test_nonliteral_strings_stay(tmp_path: Path) -> None:
    text = 'a = f"sample.old{suffix}"\nb = "sample.old" + suffix\nc = "sample." "old"\n'
    source = write(tmp_path, "tests/use.py", text)
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == []
    assert source.read_text() == text


def test_pyproject_rewrites_values_never_group_names(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "pyproject.toml",
        '[project.entry-points."sample.old"]\ncustom = "sample.old:Name"\n[tool.importlinter]\nsource_modules = ["sample.old"]\nignore_imports = ["sample.old -> sample.old.child.**"]\nlayers = ["sample.old"]\n[unrelated]\nvalue = "sample.old"\n',
    )
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new", True),), ())
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        source.read_text()
        == '[project.entry-points."sample.old"]\ncustom = "sample.new:Name"\n[tool.importlinter]\nsource_modules = ["sample.new"]\nignore_imports = ["sample.new -> sample.new.child.**"]\nlayers = ["sample.old"]\n[unrelated]\nvalue = "sample.old"\n'
    )


def test_doc_rewrites_prefixed_forms_and_keeps_line_suffixes(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "README.md",
        "See :mod:`coding_agent_playbook.legacy_demo` and `src/coding_agent_playbook/legacy_demo.py:3-8`, `old_area/file.py:12`, `tests/old_area/`.\n",
    )
    moves = MoveMap(
        (ModuleMove("one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"),),
        (),
        (
            PathMove("one", "old_area/file.py", "new_area/file.py"),
            PathMove("one", "tests/old_area/", "tests/new_area/"),
        ),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        source.read_text()
        == "See :mod:`coding_agent_playbook.new_demo` and `src/coding_agent_playbook/new_demo.py:3-8`, `new_area/file.py:12`, `tests/new_area/`.\n"
    )


def test_doc_skips_keep_markers(tmp_path: Path) -> None:
    text = "<!-- module-moves: keep -->\ncoding_agent_playbook.legacy_demo\n<!-- module-moves: keep -->\n"
    source = write(tmp_path, "README.md", text + "coding_agent_playbook.legacy_demo\n")
    moves = MoveMap(
        (ModuleMove("one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"),),
        (),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert source.read_text() == text + "coding_agent_playbook.new_demo\n"


def test_hook_runtime_harness_and_adapter_ids_stay(tmp_path: Path) -> None:
    engine = "coding_agent_playbook"
    text = "coding_agent_playbook.hook_runtime.harness, agent_harness, evals/\n"
    source = write(tmp_path, "README.md", text + "coding_agent_playbook.harness\n")
    moves = MoveMap(
        (ModuleMove("N12", f"{engine}.harness", f"{engine}.agent_harness", True),),
        (),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert source.read_text() == text + "coding_agent_playbook.agent_harness\n"


def test_bare_filenames_are_reported_not_rewritten(tmp_path: Path) -> None:
    source = write(tmp_path, "README.md", "Look at `legacy_demo.py`.\n")
    moves = MoveMap(
        (ModuleMove("one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"),),
        (),
    )
    assert check(tmp_path, moves) == ["review: README.md:1: bare 'legacy_demo.py'"]
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == []
    assert source.read_text() == "Look at `legacy_demo.py`.\n"


def test_migration_section_lists_public_moves(tmp_path: Path) -> None:
    source = write(tmp_path, "MIGRATION.md", "# Migration\n")
    moves = MoveMap(
        (
            ModuleMove(
                "one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.middle_demo"
            ),
            ModuleMove(
                "two", "coding_agent_playbook.middle_demo", "coding_agent_playbook.new_demo"
            ),
            ModuleMove(
                "three",
                "coding_agent_playbook._private_demo",
                "coding_agent_playbook._new_private_demo",
            ),
        ),
        (),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        "| `coding_agent_playbook.legacy_demo` | `coding_agent_playbook.new_demo` |"
        in source.read_text()
    )
    assert "_private_demo" not in source.read_text()
    assert "<!-- module-moves:start -->" in source.read_text()
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == []
    assert check(tmp_path, moves) == []


def test_never_opened_paths_are_pruned(tmp_path: Path) -> None:
    untouched = [
        write(tmp_path, path, "from .must_not_open import value\n")
        for path in (
            "tests/fixtures/broken.py",
            "tests/__pycache__/broken.py",
            "tests/.venv/broken.py",
            "tests/shared_skills/broken.py",
            "src/shared_skills/broken.py",
            "catalog/core/broken.py",
            "specs/broken.md",
            "AGENTS.md",
        )
    ]
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    assert apply(tmp_path, moves, formatter=FakeFormatter()) == []
    assert all(path.read_text() == "from .must_not_open import value\n" for path in untouched)


def test_python_prose_and_ci_comments_are_rewritten(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tests/use.py",
        '"""See coding_agent_playbook.legacy_demo:6."""\n# See src/coding_agent_playbook/legacy_demo.py:9\nsample = "See coding_agent_playbook.legacy_demo"\n',
    )
    workflow = write(
        tmp_path,
        ".github/workflows/ci.yml",
        "# src/coding_agent_playbook/legacy_demo.py:5\nrun: echo coding_agent_playbook.legacy_demo\n",
    )
    moves = MoveMap(
        (ModuleMove("one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"),),
        (),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert (
        source.read_text()
        == '"""See coding_agent_playbook.new_demo:6."""\n# See src/coding_agent_playbook/new_demo.py:9\nsample = "See coding_agent_playbook.legacy_demo"\n'
    )
    assert (
        workflow.read_text()
        == "# src/coding_agent_playbook/new_demo.py:5\nrun: echo coding_agent_playbook.legacy_demo\n"
    )


def test_apply_is_idempotent(tmp_path: Path) -> None:
    write(tmp_path, "tests/use.py", 'from sample.old import First\npin = "sample.old:First"\n')
    write(tmp_path, "README.md", "coding_agent_playbook.legacy_demo\n")
    moves = MoveMap(
        (
            ModuleMove("one", "sample.old", "sample.new"),
            ModuleMove(
                "two", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"
            ),
        ),
        (),
    )
    formatter = FakeFormatter()
    changed = apply(repo_root=tmp_path, moves=moves, formatter=formatter)
    assert len(changed) == 2
    assert formatter.paths == changed
    assert apply(tmp_path, moves, formatter=formatter) == []
    assert check(repo_root=tmp_path, moves=moves) == []


def test_spec_history_has_keep_markers() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = (root / "SPEC.md").read_text()
    history = spec.split("<!-- module-moves: keep -->")[1::2]
    assert len(history) == 2
    assert "**Changelog**" in history[0] and "- **0.7**" in history[0]
    assert "## Changelog" in history[1] and "- Initial draft." in history[1]
    migration = (root / "MIGRATION.md").read_text()
    records = "\n".join(migration.split("<!-- module-moves: keep -->")[1::2])
    for marker in (
        "coding_agent_playbook.bundled_content",
        "src/coding_agent_playbook/resources/precommit/config.yaml.j2",
        "from coding_agent_playbook.evaluators.registry import Evaluator",
        '[project.entry-points."coding_agent_playbook.evaluators"]',
        "from coding_agent_playbook.evaluators.grade import grade",
        "evals/task.py::evaluators_for_task",
    ):
        assert marker in records
    assert "Their replacements" not in records


def test_tree_has_no_stale_module_paths() -> None:
    root = Path(__file__).resolve().parents[2]
    findings = check(root, load_map(root / "tests/architecture/move_map"))
    stale = [line for line in findings if not line.startswith("review:")]
    assert stale == [], "\n".join(stale) + "\nRun python -m tests.architecture.module_moves apply"


def test_cli_empty_map_is_silent() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "tests.architecture.module_moves", "check"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
