"""Boundary regressions for replaying module moves safely."""

import ast
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
    main,
)
from tests.architecture.test_module_moves import FakeFormatter, write


def test_split_preserves_standalone_import_comments(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "tests/use.py",
        "from sample.old import (\n    First,\n    # rationale for second\n    Second,\n    # trailing rationale\n)\n",
    )
    moves = MoveMap(
        (),
        (
            NameMove("one", "sample.old", "sample.first", ("First",)),
            NameMove("two", "sample.old", "sample.second", ("Second",)),
        ),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert source.read_text().count("# rationale for second") == 1
    assert source.read_text().count("# trailing rationale") == 1


def test_split_keeps_inline_imports_in_their_suite(tmp_path: Path) -> None:
    source = write(
        tmp_path, "tests/use.py", "if TYPE_CHECKING: from sample.old import First, Second\n"
    )
    moves = MoveMap(
        (),
        (
            NameMove("one", "sample.old", "sample.first", ("First",)),
            NameMove("two", "sample.old", "sample.second", ("Second",)),
        ),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    tree = ast.parse(source.read_text())
    assert len(tree.body) == 1
    assert isinstance(tree.body[0], ast.If)
    assert len(tree.body[0].body) == 2


def test_doc_paths_keep_sentence_punctuation(tmp_path: Path) -> None:
    source = write(tmp_path, "README.md", "See legacy/mod.py.\n")
    apply(
        tmp_path,
        MoveMap((), (), (PathMove("one", "legacy/mod.py", "current/mod.py"),)),
        formatter=FakeFormatter(),
    )
    assert source.read_text() == "See current/mod.py.\n"


def test_conditional_exports_are_current_but_function_locals_are_not(tmp_path: Path) -> None:
    write(
        tmp_path,
        "src/sample/old.py",
        "try:\n    import optional\nexcept ImportError:\n    from fallback import Value\ndef factory():\n    class Local: pass\n",
    )
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    assert moves.resolve("sample.old.Value", tmp_path) is None
    assert moves.resolve("sample.old.Local", tmp_path) == "sample.new.Local"


def test_path_cycles_are_refused_when_loading(tmp_path: Path) -> None:
    write(
        tmp_path,
        "map/one.toml",
        '[[path]]\npr="one"\nold="legacy/"\nnew="current/"\n[[path]]\npr="two"\nold="current/"\nnew="legacy/"\n',
    )
    with pytest.raises(ValueError, match=r"legacy|current"):
        load_map(tmp_path / "map")


def test_cli_check_fails_for_stale_and_succeeds_for_reviews(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        tmp_path,
        "tests/architecture/move_map/one.toml",
        '[[module]]\npr="one"\nold="coding_agent_playbook.legacy_demo"\nnew="coding_agent_playbook.new_demo"\n',
    )
    readme = write(tmp_path, "README.md", "coding_agent_playbook.legacy_demo\n")
    assert main(["check"], root=tmp_path) == 1
    assert "README.md:1:" in capsys.readouterr().out
    readme.write_text("legacy_demo.py\n")
    assert main(["check"], root=tmp_path) == 0
    assert capsys.readouterr().out == "review: README.md:1: bare 'legacy_demo.py'\n"


def test_real_formatter_and_cli_apply(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(
        tmp_path,
        "tests/architecture/move_map/one.toml",
        '[[module]]\npr="one"\nold="sample.old"\nnew="sample.new"\n',
    )
    source = write(tmp_path, "tests/use.py", "import sample.old as writer\nx=1\n")
    assert main(["apply"], root=tmp_path) == 0
    assert "tests/use.py" in capsys.readouterr().out
    assert "import sample.new as writer" in source.read_text()
    assert "x = 1" in source.read_text()
    assert main(["check"], root=tmp_path) == 0


def test_discovery_never_follows_parent_symlinks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    readme = write(outside, "README.md", "coding_agent_playbook.legacy_demo\n")
    script = write(outside, "use.py", "import sample.old\n")
    (repo / "catalog").symlink_to(outside, target_is_directory=True)
    (repo / "src").symlink_to(outside, target_is_directory=True)
    moves = MoveMap(
        (
            ModuleMove("one", "sample.old", "sample.new"),
            ModuleMove(
                "two", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"
            ),
        ),
        (),
    )
    assert apply(repo, moves, formatter=FakeFormatter()) == []
    assert readme.read_text() == "coding_agent_playbook.legacy_demo\n"
    assert script.read_text() == "import sample.old\n"


def test_from_import_keeps_explicit_line_continuation(tmp_path: Path) -> None:
    source = write(tmp_path, "tests/use.py", "from \\\n    sample.old import Name\n")
    moves = MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ())
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert source.read_text() == "from \\\n    sample.new import Name\n"
    ast.parse(source.read_text())


def test_unicode_before_a_literal_keeps_offsets(tmp_path: Path) -> None:
    source = write(tmp_path, "tests/use.py", 'label = "été"; target = "sample.old:Name"\n')
    apply(
        tmp_path,
        MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ()),
        formatter=FakeFormatter(),
    )
    assert source.read_text() == 'label = "été"; target = "sample.new:Name"\n'


def test_longest_package_move_wins(tmp_path: Path) -> None:
    moves = MoveMap(
        (
            ModuleMove("one", "sample.old", "sample.new", True),
            ModuleMove("two", "sample.old.special", "sample.other", True),
        ),
        (),
    )
    assert moves.resolve("sample.old.special.Child", tmp_path) == "sample.other.Child"
    assert moves.resolve("sample.old.sibling.Child", tmp_path) == "sample.new.sibling.Child"


def test_apply_refuses_all_writes_if_a_later_file_is_invalid(tmp_path: Path) -> None:
    source = write(tmp_path, "src/sample/first.py", "import sample.old\n")
    write(tmp_path, "tests/z.py", "from .relative import Name\n")
    with pytest.raises(ValueError, match="relative import"):
        apply(
            tmp_path,
            MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ()),
            formatter=FakeFormatter(),
        )
    assert source.read_text() == "import sample.old\n"


def test_frozen_parent_package_and_entrypoint_group_are_refused(tmp_path: Path) -> None:
    for old in ("coding_agent_playbook", "coding_agent_playbook.runners"):
        write(
            tmp_path,
            "map/one.toml",
            f'[[module]]\npr="bad"\nold="{old}"\nnew="sample.new"\npackage=true\n',
        )
        with pytest.raises(ValueError, match=old):
            load_map(tmp_path / "map")


def test_toml_quoted_keys_comments_and_table_comments_stay(tmp_path: Path) -> None:
    source = write(
        tmp_path,
        "pyproject.toml",
        '[project.scripts] # Public commands\n"sample.old" = "sample.old:Name" # "sample.old"\n[tool.importlinter]\n"layers" = ["sample.old"]\n"modules" = [\n    "sample.old", # "sample.old"\n]\n',
    )
    apply(
        tmp_path,
        MoveMap((ModuleMove("one", "sample.old", "sample.new"),), ()),
        formatter=FakeFormatter(),
    )
    assert (
        source.read_text()
        == '[project.scripts] # Public commands\n"sample.old" = "sample.new:Name" # "sample.old"\n[tool.importlinter]\n"layers" = ["sample.old"]\n"modules" = [\n    "sample.new", # "sample.old"\n]\n'
    )


@pytest.mark.parametrize("filename", ["tests/use.py", ".github/workflows/ci.yml"])
def test_keep_markers_span_comments(tmp_path: Path, filename: str) -> None:
    history = "# <!-- module-moves: keep -->\n# coding_agent_playbook.legacy_demo\n# <!-- module-moves: keep -->\n"
    source = write(tmp_path, filename, history + "# coding_agent_playbook.legacy_demo\n")
    apply(
        tmp_path,
        MoveMap(
            (
                ModuleMove(
                    "one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"
                ),
            ),
            (),
        ),
        formatter=FakeFormatter(),
    )
    assert source.read_text() == history + "# coding_agent_playbook.new_demo\n"


def test_inline_workflow_comment_and_concatenated_docstring(tmp_path: Path) -> None:
    workflow = write(
        tmp_path, ".github/workflows/ci.yml", "run: pytest -q # coding_agent_playbook.legacy_demo\n"
    )
    source = write(
        tmp_path,
        "tests/use.py",
        '("""See documentation\n"""\n "coding_agent_playbook.legacy_demo")\n',
    )
    moves = MoveMap(
        (ModuleMove("one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"),),
        (),
    )
    apply(tmp_path, moves, formatter=FakeFormatter())
    assert workflow.read_text() == "run: pytest -q # coding_agent_playbook.new_demo\n"
    docstring = ast.get_docstring(ast.parse(source.read_text()))
    assert docstring is not None
    assert "coding_agent_playbook.new_demo" in docstring


def test_first_pilot_move_introduces_one_public_migration_row(tmp_path: Path) -> None:
    engine = "coding_agent_playbook"
    migration = write(tmp_path, "MIGRATION.md", "# Migration\n")
    moves = MoveMap((ModuleMove("N1", f"{engine}._toml", f"{engine}.toml_writer"),), ())
    apply(tmp_path, moves, formatter=FakeFormatter())
    rows = [line for line in migration.read_text().splitlines() if line.startswith("| `")]
    assert rows == [f"| `{engine}._toml` | `{engine}.toml_writer` |"]


@pytest.mark.parametrize("protected", [False, True])
def test_exact_dotted_docstring_respects_keep_markers(tmp_path: Path, protected: bool) -> None:
    marker = "# <!-- module-moves: keep -->\n" if protected else ""
    original = marker + '"""coding_agent_playbook.legacy_demo"""\n' + marker
    source = write(tmp_path, "tests/use.py", original)
    moves = MoveMap(
        (ModuleMove("one", "coding_agent_playbook.legacy_demo", "coding_agent_playbook.new_demo"),),
        (),
    )
    assert bool(check(tmp_path, moves)) is not protected
    apply(tmp_path, moves, formatter=FakeFormatter())
    expected = original if protected else original.replace("legacy_demo", "new_demo")
    assert source.read_text() == expected
    assert check(tmp_path, moves) == []


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("<!-- module-moves: keep -->", "<!-- module-moves: keep -->"),
        ("<!-- module-moves:start -->", "<!-- module-moves:end -->"),
    ],
)
def test_unclosed_marker_names_the_expected_closer(
    tmp_path: Path, opening: str, closing: str
) -> None:
    write(tmp_path, "README.md", opening + "\n")
    with pytest.raises(ValueError, match="Unclosed") as error:
        check(tmp_path, MoveMap((), ()))
    assert repr(opening) in str(error.value)
    assert f"expected {closing!r}" in str(error.value)
