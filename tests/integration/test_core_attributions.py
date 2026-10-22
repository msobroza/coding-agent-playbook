"""CI gate: ``catalog/core/ATTRIBUTIONS.md`` maps every vendored core file (ADR 0004, D31).

Core copies upstream Python guidance and adapts it (D1). The credit and the
provenance live in one file: one section per source with its D11 pin, and inside
it one table per core skill mapping each upstream file to the core files it
became, or to DROP with a reason. A per-skill ``Engine-written files`` list
covers the files with no upstream text. The parser is ``tests/_attributions.py``;
each check here runs once on the shipped file and once on a synthetic tree.
"""

from __future__ import annotations

import hashlib
import textwrap
from typing import TYPE_CHECKING

import pytest

from tests._attributions import (
    ATTRIBUTIONS_PATH,
    SOURCE_PINS,
    Attributions,
    attribution_errors,
    load_core_attributions,
    parse_attributions,
)
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_PIN = "a" * 40
_LICENSE = b"MIT License\n\nCopyright (c) 2026 Somebody\n"
_LICENSE_SHA = hashlib.sha256(_LICENSE).hexdigest()

_SYNTHETIC = textwrap.dedent(
    f"""\
    # Attributions

    Header prose.

    ## up-source

    Source: an upstream collection.
    Commit: `{_PIN}`
    License: MIT License.

    ### alpha

    | Upstream file | Core files | Changes |
    | --- | --- | --- |
    | `skills/a.md` | `rules/a.md`, `references/guide.md` | Engine frontmatter; no URLs. |
    | `skills/b.md` | DROP | Recommends a tool the engine does not adopt. |

    Distilled (credited by name only, no vendored text):

    - `rules/d.md`

    ## Engine-written files

    ### alpha

    - `SKILL.md`
    """
)


# --------------------------------------------------------------------------- #
# The shipped file.
# --------------------------------------------------------------------------- #


def test_core_attributions_map_every_core_skill_file() -> None:
    errors = attribution_errors(load_core_attributions())
    assert errors == [], "catalog/core/ATTRIBUTIONS.md is out of step:\n" + "\n".join(errors)


def test_core_attributions_name_both_pins_and_drop_the_fresh_text_policy() -> None:
    """ADR 0004 retires 'written fresh' and the prS pin; D11's two commits replace them."""
    text = ATTRIBUTIONS_PATH.read_text(encoding="utf-8")
    assert "written fresh" not in text
    assert "bf64c51" not in text
    assert {name: source.commit for name, source in load_core_attributions().sources.items()} == {
        "python-best-practices": "fa0d3f58afb8bf56c028bb559e0e7bc1538e079a",
        "python-clean-architecture": "9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce",
    }
    assert dict(SOURCE_PINS) == {
        "python-best-practices": "fa0d3f58afb8bf56c028bb559e0e7bc1538e079a",
        "python-clean-architecture": "9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce",
    }


def test_core_attributions_list_engine_written_files_per_core_skill() -> None:
    """Every core skill has its own Engine-written list, so lanes never share one."""
    on_disk = {p.name for p in (CORE_ROOT / "skills").iterdir() if p.is_dir()}
    assert on_disk <= set(load_core_attributions().engine_written)


# --------------------------------------------------------------------------- #
# The parser and the checks, on synthetic input.
# --------------------------------------------------------------------------- #


def _parsed(text: str = _SYNTHETIC) -> Attributions:
    return parse_attributions(text)


def test_parse_reads_sources_pins_rows_distilled_and_engine_written() -> None:
    parsed = _parsed()

    source = parsed.sources["up-source"]
    assert source.commit == _PIN
    alpha = source.skills["alpha"]
    assert [(r.upstream, r.targets, r.dropped) for r in alpha.rows] == [
        ("skills/a.md", ("rules/a.md", "references/guide.md"), False),
        ("skills/b.md", (), True),
    ]
    assert alpha.rows[1].changes == "Recommends a tool the engine does not adopt."
    assert alpha.distilled == ["rules/d.md"]
    assert parsed.engine_written == {"alpha": ["SKILL.md"]}


#: The synthetic skill tree that :data:`_SYNTHETIC` describes exactly.
_TREE: dict[str, bytes] = {
    "alpha/SKILL.md": b"# Alpha\n",
    "alpha/rules/a.md": b"# A\n",
    "alpha/rules/d.md": b"# D\n",
    "alpha/references/guide.md": b"# Guide\n",
    "alpha/references/LICENSE.up-source": _LICENSE,
}


def _errors(
    tmp_path: Path, text: str = _SYNTHETIC, tree: dict[str, bytes] | None = None
) -> list[str]:
    for rel, body in (_TREE if tree is None else tree).items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(body)
    return attribution_errors(
        parse_attributions(text),
        tmp_path,
        pins={"up-source": _PIN},
        license_sha256={"up-source": _LICENSE_SHA},
    )


def test_a_consistent_mapping_has_no_errors(tmp_path: Path) -> None:
    assert _errors(tmp_path) == []


def test_a_wrong_pin_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace(_PIN, "b" * 40)
    assert _errors(tmp_path, text) == [
        f"up-source: commit {'b' * 40} does not match the D11 pin {_PIN}"
    ]


def test_a_missing_or_unknown_source_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("## up-source", "## other-source")
    errors = _errors(tmp_path, text)
    assert "up-source: no section for this pinned source" in errors
    assert "other-source: a source without a D11 pin" in errors


def test_a_dangling_core_path_fails(tmp_path: Path) -> None:
    tree = {k: v for k, v in _TREE.items() if k != "alpha/rules/d.md"}
    assert _errors(tmp_path, tree=tree) == [
        "alpha/rules/d.md: listed in ATTRIBUTIONS.md but not in the skill"
    ]


def test_an_unlisted_core_skill_file_fails(tmp_path: Path) -> None:
    tree = {**_TREE, "alpha/scripts/tool.py": b"print()\n", "beta/SKILL.md": b"# Beta\n"}
    assert _errors(tmp_path, tree=tree) == [
        "alpha/scripts/tool.py: neither a mapping target nor engine-written in ATTRIBUTIONS.md",
        "beta/SKILL.md: neither a mapping target nor engine-written in ATTRIBUTIONS.md",
    ]


def test_a_directory_target_covers_every_file_under_it(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("`references/guide.md`", "`references/guide.md`, `examples/app/`")
    tree = {**_TREE, "alpha/examples/app/main.py": b"x = 1\n", "alpha/examples/app/a/b.py": b""}
    assert _errors(tmp_path, text, tree) == []


def test_a_drop_row_without_a_reason_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("Recommends a tool the engine does not adopt.", "")
    assert _errors(tmp_path, text) == ["up-source/alpha: `skills/b.md` is dropped without a reason"]


def test_a_mapped_row_without_changes_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("Engine frontmatter; no URLs.", "")
    assert _errors(tmp_path, text) == ["up-source/alpha: `skills/a.md` lists no changes"]


def test_an_upstream_file_mapped_twice_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("`skills/b.md` | DROP", "`skills/a.md` | DROP")
    assert _errors(tmp_path, text) == ["up-source: `skills/a.md` appears in more than one row"]


def test_a_file_both_engine_written_and_mapped_fails(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace("- `SKILL.md`", "- `SKILL.md`\n- `rules/a.md`")
    assert _errors(tmp_path, text) == [
        "alpha/rules/a.md: listed as engine-written and as holding upstream text"
    ]


def test_targets_without_a_license_copy_fail(tmp_path: Path) -> None:
    tree = {k: v for k, v in _TREE.items() if "LICENSE" not in k}
    assert _errors(tmp_path, tree=tree) == [
        "alpha: holds text from up-source but ships no references/LICENSE.up-source"
    ]


def test_a_license_copy_without_targets_fails(tmp_path: Path) -> None:
    tree = {**_TREE, "beta/SKILL.md": b"# Beta\n", "beta/references/LICENSE.up-source": _LICENSE}
    text = _SYNTHETIC + "\n### beta\n\n- `SKILL.md`\n"
    assert _errors(tmp_path, text, tree) == [
        "beta: ships references/LICENSE.up-source but holds no text from up-source"
    ]


def test_a_distilled_file_needs_no_license_copy(tmp_path: Path) -> None:
    text = _SYNTHETIC.replace(
        "| `skills/a.md` | `rules/a.md`, `references/guide.md` | Engine frontmatter; no URLs. |\n",
        "",
    ).replace("- `SKILL.md`", "- `SKILL.md`\n- `rules/a.md`\n- `references/guide.md`")
    tree = {k: v for k, v in _TREE.items() if "LICENSE" not in k}
    assert _errors(tmp_path, text, tree) == []


def test_a_changed_license_copy_fails(tmp_path: Path) -> None:
    tree = {**_TREE, "alpha/references/LICENSE.up-source": _LICENSE + b"\n"}
    assert _errors(tmp_path, tree=tree) == [
        "alpha/references/LICENSE.up-source: not byte-identical to up-source's license"
    ]
