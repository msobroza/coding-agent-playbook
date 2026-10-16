"""Tests for the ``.coding-agent-playbook.toml`` / lockfile writer (``_dump_toml``).

Two contracts are pinned here:

* **Byte stability.** The golden strings below were captured from the writer
  *before* it was generalized to arbitrary depth (branch
  ``claude/init-local-overrides``, cut from ``1dd8f74``). Every Config and Lockfile
  shape the engine already wrote must keep producing exactly these bytes, so a
  re-run of ``playbook init`` / ``playbook sync`` never churns a committed file.
* **Round trip.** ``playbook init`` now writes back the committed tables
  ``Config`` does not manage (``[links]``, ``[metrics]``, future keys) verbatim,
  so the writer must reproduce anything :mod:`tomllib` can parse —
  ``tomllib.loads(_dump_toml(tomllib.loads(doc)))`` holds the same values with
  the same TOML types (:func:`tests.toml_equality.assert_toml_identical`, not
  ``==``, which lets ``1.0`` become ``1``), at any nesting depth.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import inspect
import sys
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._toml import dump_toml as _dump_toml
from coding_agent_playbook.config import Config, OutputConfig, ProjectMeta, StorageConfig
from coding_agent_playbook.lockfile import LockEntry, Lockfile
from tests.toml_equality import assert_toml_identical, toml_mismatch

if TYPE_CHECKING:
    from collections.abc import Iterator

# --- byte stability (golden output captured before the generalization) ------


def _representative_config() -> Config:
    """Every value shape ``Config.to_dict`` produces: escapes, nested cache, lists."""
    return Config(
        schema_version=1,
        project=ProjectMeta(
            name="risk-models",
            kind="python-application",
            description='Say "hi"\tto\nC:\\x and \x00',
        ),
        engine_version="0.17.0",
        overlays_enabled=["playbook_rules_bnp", "coding_agent_playbook.packs.superpowers"],
        adapters_enabled=["continue", "claude_code", "opencode", "shared_skills"],
        storage=StorageConfig(),
        detector_cache={
            "package_manager": "uv",
            "python_version": "3.12",
            "has_notebooks": False,
            "test_count": 42,
            "frameworks": {"fastapi": "0.115.0", "pydantic": "2.9.2"},
            "ci_providers": ["github", "gitlab"],
            "empty": [],
        },
        user_choices={"docstring_style": "numpy", "nested_list": [["a"], []]},
        output=OutputConfig(commit=False),
    )


_GOLDEN_CONFIG = (
    "schema_version = 1\n"
    'overlays_enabled = ["playbook_rules_bnp", "coding_agent_playbook.packs.superpowers"]\n'
    'adapters_enabled = ["continue", "claude_code", "opencode", "shared_skills"]\n'
    "\n"
    "[project]\n"
    'name = "risk-models"\n'
    'kind = "python-application"\n'
    'description = "Say \\"hi\\"\\tto\\nC:\\\\x and \\u0000"\n'
    "\n"
    "[engine]\n"
    'version = "0.17.0"\n'
    "\n"
    "[storage]\n"
    'artifact_source = "filesystem"\n'
    'state_source = "filesystem"\n'
    "\n"
    "[output]\n"
    "commit = false\n"
    "\n"
    "[detector_cache]\n"
    'package_manager = "uv"\n'
    'python_version = "3.12"\n'
    "has_notebooks = false\n"
    "test_count = 42\n"
    'ci_providers = ["github", "gitlab"]\n'
    "empty = []\n"
    "\n"
    "[detector_cache.frameworks]\n"
    'fastapi = "0.115.0"\n'
    'pydantic = "2.9.2"\n'
    "\n"
    "[user_choices]\n"
    'docstring_style = "numpy"\n'
    'nested_list = [["a"], []]\n'
)

_GOLDEN_LOCKFILE = (
    "schema_version = 1\n"
    'engine_version = "0.17.0"\n'
    'rendered_at = "2026-10-14T12:00:00Z"\n'
    "\n"
    "[[entries]]\n"
    'path = "AGENTS.md"\n'
    f'sha256 = "{"ab" * 32}"\n'
    "bytes = 4096\n"
    "\n"
    "[[entries]]\n"
    'path = ".claude/skills/x y/\\"q\\".md"\n'
    f'sha256 = "{"cd" * 32}"\n'
    "bytes = 0\n"
)


def test_config_output_is_byte_identical_to_the_pre_generalization_writer() -> None:
    assert _dump_toml(_representative_config().to_dict()) == _GOLDEN_CONFIG


def test_lockfile_output_is_byte_identical_to_the_pre_generalization_writer() -> None:
    lockfile = Lockfile(
        schema_version=1,
        engine_version="0.17.0",
        rendered_at="2026-10-14T12:00:00Z",
        entries=[
            LockEntry(path="AGENTS.md", sha256="ab" * 32, bytes=4096),
            LockEntry(path='.claude/skills/x y/"q".md', sha256="cd" * 32, bytes=0),
        ],
    )
    assert _dump_toml(lockfile.to_dict()) == _GOLDEN_LOCKFILE


def test_golden_config_parses_back_to_the_same_config() -> None:
    assert Config.from_dict(tomllib.loads(_GOLDEN_CONFIG)) == _representative_config()


# --- the comparator is strict where == is lenient ------------------------------

_UTC = dt.UTC
_PLUS_ONE = dt.timezone(dt.timedelta(hours=1))


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        pytest.param({"w": 1}, {"w": 1.0}, id="int-vs-float"),
        pytest.param([True], [1], id="bool-vs-int"),
        pytest.param({"z": 0.0}, {"z": -0.0}, id="zero-sign"),
        pytest.param([float("nan")], [-float("nan")], id="nan-sign"),
        pytest.param(
            dt.datetime(2026, 1, 1, 12, tzinfo=_UTC),
            dt.datetime(2026, 1, 1, 13, tzinfo=_PLUS_ONE),
            id="same-instant-other-offset",
        ),
        pytest.param(dt.datetime(2026, 1, 1), dt.date(2026, 1, 1), id="datetime-vs-date"),
        pytest.param({"a": [1]}, {"a": [1, 2]}, id="list-length"),
        pytest.param({"a": 1}, {"a": 1, "b": 2}, id="key-set"),
    ],
)
def test_comparator_catches_what_python_equality_lets_through(
    actual: object, expected: object
) -> None:
    """Each pair would pass a ``==`` round-trip test (bar the shape ones) yet is a
    different TOML document — the writer bugs the round-trip tests must catch."""
    assert toml_mismatch(actual, expected) is not None


def test_comparator_accepts_nan_and_ignores_table_key_order() -> None:
    nan = float("nan")
    assert toml_mismatch({"b": [nan], "a": 1}, {"a": 1, "b": [float("nan")]}) is None


# --- round trip over everything tomllib can produce --------------------------


_CORPUS: dict[str, str] = {
    "strings": r"""
basic = "plain"
escapes = "quote \" backslash \\ tab \t newline \n cr \r"
controls = "nul \u0000 bell \u0007 esc \u001B del \u007F"
unicode = "café — π 🐍"
literal = 'C:\no\escapes'
multiline = '''
two
lines'''
empty = ""
""",
    "booleans-and-integers": """
yes = true
no = false
zero = 0
negative = -17
big = 9_223_372_036_854_775_807
hex = 0xDEAD_BEEF
octal = 0o755
binary = 0b1101
""",
    "floats": """
plain = 1.5
integral = 1.0
integral_large = 20.0
small = 1e-05
large = 6.02e23
exponent = 1e+16
negative_zero = -0.0
positive_inf = inf
negative_inf = -inf
not_a_number = nan
signed_nan = -nan
""",
    "dates-and-times": """
offset_utc = 1979-05-27T07:32:00Z
offset_negative = 1979-05-27T00:32:00.999999-07:00
offset_positive = 1979-05-27T07:32:00+05:30
offset_space = 1979-05-27 07:32:00Z
local_datetime = 1979-05-27T07:32:00
local_datetime_fraction = 1979-05-27T00:32:00.5
local_date = 1979-05-27
local_time = 07:32:00
local_time_fraction = 00:32:00.999999
""",
    "arrays": """
empty = []
integers = [1, 2, 3]
nested = [[1, 2], ["a", "b"], [[true]], []]
mixed = [1, "two", 3.5, true, 1979-05-27, 07:32:00, [4]]
inline_tables = [{ a = 1 }, { b = [1, 2], c = { d = "e" } }]
mixed_tables = [1, { a = 1 }, "x"]
array_of_arrays_of_tables = [[{ a = 1 }, { b = 2 }], []]
empty_inline_table = [{}]
""",
    "tables-at-any-depth": """
[a]
own = 1
[a.b]
own = 2
[a.b.c]
own = 3
[a.b.c.d]
deepest = true
""",
    "scalar-keys-after-sub-tables-in-dict-order": """
[x]
sub.deep = 1
after = 2
[x.y.z]
leaf = "z"
""",
    "empty-tables": """
[empty]
[parent.empty_child]
[parent.full_child]
k = 1
""",
    "inline-table-values": """
point = { x = 1, y = { z = 2 } }
[holder]
inline = { a = [1, { b = 2 }] }
""",
    "arrays-of-tables": """
[[fruits]]
name = "apple"
[fruits.physical]
color = "red"
shape = "round"
[[fruits.varieties]]
name = "red delicious"
[[fruits.varieties]]
name = "granny smith"
[fruits.varieties.taste]
sour = true

[[fruits]]
name = "banana"
[[fruits.varieties]]
name = "plantain"
""",
    "arrays-of-tables-at-depth": """
[a.b]
own = "b"
[[a.b.c]]
x = 1
[a.b.c.d]
y = 2
[[a.b.c.e]]
z = 3
[[a.b.c]]
x = 4
[[a.b.c]]
""",
    "quoted-keys": """
"weird key" = 1
"dot.ted" = 2
"café" = 3
"" = 4
'single "quoted"' = 5
"tab\\tkey" = 6
["table with space"."sub.key"]
"x y" = 1
[["arr ay"]]
"k.v" = { "in ner" = 1 }
""",
    "realistic-config": """
schema_version = 1
adapters_enabled = ["continue", "claude_code"]
future_top_level = "kept"

[project]
name = "r"
kind = "python-library"

[engine]
version = "0.17.0"

[links]
allowed_domains = ["example.com", "docs.example.org"]

[metrics]
mode = "both"
fail_on_breach = true
test_cmd = ["python", "-m", "pytest", "-q"]

[metrics.thresholds.cyclomatic_complexity]
warn = 10
fail = 20.5

[metrics.regression.coverage]
max_worsening = 0.0

[metrics.weights]
cyclomatic_complexity = 1.0
coverage = 0.25

[future_feature]
enabled_at = 2026-10-14
ratio = 1e-05
[future_feature.deep.deeper]
leaf = [1, { two = 2 }]
[[future_feature.rules]]
id = "r1"
""",
}


@pytest.mark.parametrize("doc", list(_CORPUS.values()), ids=list(_CORPUS))
def test_dump_toml_round_trips_what_tomllib_parses(doc: str) -> None:
    parsed = tomllib.loads(doc)
    assert_toml_identical(tomllib.loads(_dump_toml(parsed)), parsed)


def test_dump_toml_round_trip_is_a_fixed_point() -> None:
    """A second dump of the re-parsed output is byte-identical to the first."""
    for doc in _CORPUS.values():
        once = _dump_toml(tomllib.loads(doc))
        assert _dump_toml(tomllib.loads(once)) == once


def test_dump_toml_round_trips_python_temporal_values() -> None:
    data = {
        "dates": {
            "utc": dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.UTC),
            "offset": dt.datetime(
                2026, 10, 14, 12, 0, 0, 250, tzinfo=dt.timezone(dt.timedelta(hours=-7))
            ),
            "local": dt.datetime(2026, 10, 14, 12, 0),
            "day": dt.date(2026, 10, 14),
            "time": dt.time(23, 59, 59, 999999),
        }
    }
    assert_toml_identical(tomllib.loads(_dump_toml(data)), data)


# --- rendering shape ------------------------------------------------------------


def test_dump_toml_emits_tables_at_any_depth() -> None:
    """The writer used to refuse a third level (``TypeError``); preserved user
    tables (``[metrics.thresholds.<name>]``) need arbitrary depth."""
    assert _dump_toml({"a": {"b": {"c": {"d": 1}}}}) == "[a]\n\n[a.b]\n\n[a.b.c]\nd = 1\n"


def test_dump_toml_emits_a_tables_own_keys_before_its_sub_tables() -> None:
    """TOML puts a key written after ``[a.t]`` inside ``a.t``, so ``s`` must come first."""
    rendered = _dump_toml({"a": {"t": {"k": 1}, "s": 2}})
    assert rendered == "[a]\ns = 2\n\n[a.t]\nk = 1\n"


def test_dump_toml_emits_arrays_of_tables_with_sub_tables_at_depth() -> None:
    data = {"a": {"b": [{"x": 1, "c": {"y": 2}, "d": [{"z": 3}]}, {"x": 4}]}}
    assert _dump_toml(data) == (
        "[a]\n\n[[a.b]]\nx = 1\n\n[a.b.c]\ny = 2\n\n[[a.b.d]]\nz = 3\n\n[[a.b]]\nx = 4\n"
    )


def test_dump_toml_quotes_keys_in_assignments_and_headers() -> None:
    data = {"top key": 1, "dot.ted": {"weird key": {"k": 1}, "é": 2}}
    assert _dump_toml(data) == (
        '"top key" = 1\n\n["dot.ted"]\n"é" = 2\n\n["dot.ted"."weird key"]\nk = 1\n'
    )


def test_dump_toml_renders_mixed_arrays_inline() -> None:
    """Only an all-table array becomes ``[[...]]``; a mixed one stays inline."""
    assert _dump_toml({"m": [1, {"a": 1}]}) == "m = [1, { a = 1 }]\n"


def test_dump_toml_emits_empty_tables() -> None:
    assert _dump_toml({"e": {}, "f": {"g": {}}}) == "[e]\n\n[f]\n\n[f.g]\n"


# --- unsupported Python types still fail loudly ---------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"weird": object()}, id="top-level"),
        pytest.param({"a": {"b": {"c": None}}}, id="table-at-depth"),
        pytest.param({"a": [{"b": {1, 2}}]}, id="array-of-tables"),
        pytest.param({"a": [b"bytes"]}, id="inside-array"),
        pytest.param({"a": [1, {"b": (1, 2)}]}, id="inside-inline-table"),
    ],
)
def test_dump_toml_rejects_unsupported_types(data: dict[str, Any]) -> None:
    with pytest.raises(TypeError, match=r"^_dump_toml does not support value of type"):
        _dump_toml(data)


# --- documents tomllib accepts that the writer used to crash on ------------------


@contextlib.contextmanager
def _frames_to_spare(frames: int) -> Iterator[None]:
    """Run the block with only ``frames`` stack frames left before ``RecursionError``.

    A writer that recursed once per nesting level would need a frame per level;
    a tight budget proves the walk is iterative without a slow, huge document.
    """
    depth = len(inspect.stack(0))
    previous = sys.getrecursionlimit()
    sys.setrecursionlimit(depth + frames)
    try:
        yield
    finally:
        sys.setrecursionlimit(previous)


@pytest.mark.parametrize(
    "doc",
    [
        pytest.param("[" + ".".join(["t"] * 400) + "]\nk = 1\n", id="tables"),
        pytest.param("[[" + ".".join(["t"] * 400) + "]]\nk = 1\n", id="arrays-of-tables"),
        pytest.param("x = " + "[" * 300 + "1" + "]" * 300 + "\n", id="inline-arrays"),
        pytest.param("x = [0, " + "{ a = " * 200 + "1" + " }" * 200 + "]\n", id="inline-tables"),
    ],
)
def test_dump_toml_writes_deep_nesting_without_recursing(doc: str) -> None:
    """Regression: the writer recursed three frames per table level, so a header
    332+ levels deep (``tomllib`` builds headers iteratively, with no limit) raised
    ``RecursionError`` instead of being written; inline values recursed too, so a
    deep one ``tomllib`` accepted could overflow from a deeper caller stack."""
    parsed = tomllib.loads(doc)
    with _frames_to_spare(60):
        rendered = _dump_toml(parsed)
    assert_toml_identical(tomllib.loads(rendered), parsed)


def test_dump_toml_writes_integers_past_the_int_to_str_limit_in_hex(
    default_int_max_str_digits: int,
) -> None:
    """Regression: ``tomllib`` reads ``0x``/``0o``/``0b`` literals with no digit limit,
    but ``str`` refuses ints past 4300 decimal digits, so these raised ``ValueError``."""
    doc = f"hex = 0x{'f' * 4000}\nbinary = 0b1{'0' * 15000}\noctal = 0o7{'7' * 6000}\n"
    parsed = tomllib.loads(doc)
    rendered = _dump_toml(parsed)
    assert rendered.startswith(f"hex = 0x{'f' * 4000}\n")
    assert_toml_identical(tomllib.loads(rendered), parsed)


# --- keys that need quotes (a latent bug of the pre-generalization writer) ---------


def _config_with_keys_that_need_quotes() -> Config:
    return Config(
        schema_version=1,
        project=ProjectMeta(name="r", kind="python-library"),
        engine_version="0.17.0",
        detector_cache={
            "dependencies": {"ruamel.yaml": ">=0.17", "zope.interface": "", "Café_Pkg": "==1"},
        },
        user_choices={"docs.style": "google", '"q"': 1, "plain": True},
    )


def test_config_keys_that_need_quotes_are_written_quoted() -> None:
    """Regression: ``_dump_toml`` wrote keys raw, so ``ruamel.yaml = ">=0.17"`` (a
    dotted dependency name a first ``init`` detects) was re-read as ``{ruamel:
    {yaml: …}}``, and a non-ASCII name (``Café_Pkg``) made the file unparseable."""
    rendered = _dump_toml(_config_with_keys_that_need_quotes().to_dict())
    assert '\n"ruamel.yaml" = ">=0.17"\n' in rendered
    assert '\n"Café_Pkg" = "==1"\n' in rendered
    assert '\n"docs.style" = "google"\n' in rendered
    assert '\n"\\"q\\"" = 1\n' in rendered
    assert "\nplain = true\n" in rendered


def test_config_keys_that_need_quotes_round_trip_through_config() -> None:
    config = _config_with_keys_that_need_quotes()
    reparsed = tomllib.loads(_dump_toml(config.to_dict()))
    assert_toml_identical(reparsed, config.to_dict())
    assert Config.from_dict(reparsed) == config


# --- P6: tables Config does not model ([hooks], [metrics]…) ride along -------------


def test_dump_toml_round_trips_extension_tables_beyond_depth_two() -> None:
    """P6: a preserved ``[hooks]``/``[metrics]`` nests past two header levels and
    holds arrays of tables with tables inside; it comes back with the same types."""
    data = {
        "schema_version": 1,
        "a": {"flat": True, "b": {"c": {"d": 1, "e": {"f": [1.5, "x"]}}}},
        "metrics": {"rows": [{"name": "cc", "fail": 20}, {"name": "mi", "warn": {"min": 0.5}}]},
        "entries": [{"path": "x", "meta": {"deep": {"er": 1}}, "tags": [{"k": "v"}]}],
    }
    assert_toml_identical(tomllib.loads(_dump_toml(data)), data)


def test_dump_toml_keeps_temporal_values() -> None:
    data = {
        "links": {"checked_on": dt.date(2026, 10, 14), "at": dt.time(7, 30)},
        "stamp": dt.datetime(2026, 10, 14, 9, 0, tzinfo=dt.UTC),
    }
    assert tomllib.loads(_dump_toml(data)) == data


def test_dump_toml_quotes_non_bare_keys() -> None:
    data = {
        "top key": "v",
        "hooks": {"with space": 1, "a.b": {"enabled": False}, "plain": {"x": 1}},
        "my entries": [{"k.k": 1}],
    }
    text = _dump_toml(data)
    assert tomllib.loads(text) == data
    assert '"top key" = "v"\n' in text
    assert '"with space" = 1\n' in text
    assert '[hooks."a.b"]\nenabled = false\n' in text
    assert "[hooks.plain]\n" in text
    assert '[["my entries"]]\n"k.k" = 1\n' in text


# Captured from the pre-P6 writer: the engine's own shapes, the lockfile's
# hook-era fields (``kind``/``adapter``/``scope``/``executable``) included, must not drift.
_ENGINE_SHAPES_GOLDEN_CONFIG = """\
schema_version = 1
overlays_enabled = ["acme_overlay"]
adapters_enabled = ["continue", "claude_code"]

[project]
name = "my-app"
kind = "python-application"
description = "An \\"app\\""

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"

[output]
commit = false

[detector_cache]
python_version = "3.12"
has_ci = true

[detector_cache.frameworks]
fastapi = "0.110.0"
scikit-learn = "1.5"

[user_choices]
banking_mode = false
docstring_style = "numpy"
"""

_ENGINE_SHAPES_GOLDEN_LOCKFILE = """\
schema_version = 2
engine_version = "0.1.0a0"
rendered_at = "2026-05-28T12:00:00Z"

[[entries]]
path = "AGENTS.md"
sha256 = "abc"
bytes = 4
kind = "composite"
adapter = "agents_md"

[[entries]]
path = ".claude/settings.json"
sha256 = "def"
bytes = 9
scope = "json:/hooks"
executable = true
"""


def test_dump_toml_without_extra_tables_is_byte_identical() -> None:
    config = Config(
        schema_version=1,
        project=ProjectMeta(name="my-app", kind="python-application", description='An "app"'),
        engine_version="0.1.0a0",
        overlays_enabled=["acme_overlay"],
        adapters_enabled=["continue", "claude_code"],
        detector_cache={
            "python_version": "3.12",
            "has_ci": True,
            "frameworks": {"fastapi": "0.110.0", "scikit-learn": "1.5"},
        },
        user_choices={"banking_mode": False, "docstring_style": "numpy"},
        output=OutputConfig(commit=False),
    )
    lockfile = Lockfile(
        schema_version=2,
        engine_version="0.1.0a0",
        rendered_at="2026-05-28T12:00:00Z",
        entries=[
            LockEntry("AGENTS.md", "abc", 4, kind="composite", adapter="agents_md"),
            LockEntry(".claude/settings.json", "def", 9, scope="json:/hooks", executable=True),
        ],
    )
    assert _dump_toml(config.to_dict()) == _ENGINE_SHAPES_GOLDEN_CONFIG
    assert _dump_toml(lockfile.to_dict()) == _ENGINE_SHAPES_GOLDEN_LOCKFILE
