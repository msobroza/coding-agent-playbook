"""A builtin's handler config read against its ``CONFIG_SCHEMA`` (specs/prT-package-layout.md §8 B.7).

``HookConfig`` is the one reader of a builtin's merged ``handler.config``: a
value of the wrong kind reads as the caller's default, and the emptiness and
range rules are the caller's, named at each read. Reading an undeclared key, or
reading a key with a method that does not match its declared kind, raises.
"""

from __future__ import annotations

import ast
import re
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

import coding_agent_playbook.hook_runtime as hook_runtime
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.config.keys import ConfigKey
from coding_agent_playbook.hook_runtime.registry import builtin_handler_modules

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    type Read = Callable[[HookConfig], object]

#: The definitions whose parameters and aliases the config-read guard tracks.
_Function = ast.FunctionDef | ast.AsyncFunctionDef

_SCHEMA: Final = {
    "enabled": ConfigKey("boolean"),
    "mode": ConfigKey("string", "strictest", ("off", "ask", "enforce")),
    "label": ConfigKey("string"),
    "cap": ConfigKey("integer"),
    "budget": ConfigKey("number"),
    "hosts": ConfigKey("list", "relax"),
    "extra_rows": ConfigKey("regex", "extend"),
    "trailers": ConfigKey("table"),
}
#: The packages whose builtins read their config through ``HookConfig`` (B.7.4).
_BUILTIN_DIRS: Final = ("handlers", "stop")
#: Chain files whose raw reads B.13 leaves to the writer-side work ("until #62" in B.7.4).
_RAW_READS_ALLOWED: Final = frozenset({"ruff_feedback.py", "docstring_nonregression.py"})
#: ``(file, key)`` raw reads of keys sync writes into a hook's config and no ``CONFIG_SCHEMA``
#: declares: ``HookConfig`` raises on an undeclared key, and declaring one would let a layer set
#: it (validate would accept it in a consumer's ``[hooks.<id>]``). Every other raw read fails.
_SYNC_WRITTEN_READS: Final = frozenset(
    {
        # The cut-over date sync copies from [hooks.commit_convention]; validate checks its text.
        ("commit_convention.py", "cutover_date"),
        # toolchain declares no schema: sync writes both install hints from the guard config.
        ("toolchain.py", "install_hint"),
        ("toolchain.py", "cz_install_hint"),
        # The slash-command scope table sync compiles from the prompts.
        ("prompt_scope.py", "scopes"),
        # skill_nudge's CONFIG_SCHEMA is empty on purpose: sync writes the skill glob table.
        ("skill_nudge.py", "skills"),
    }
)
#: A list value as a TOML author may spell it, with the item kinds validate lets through.
_HOSTS: Final = ["pypi.org", "", "  ", 3, None, "mirror.internal"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param({"enabled": False}, False, id="false"),
        pytest.param({"enabled": True}, True, id="true"),
        pytest.param({"enabled": 0}, True, id="zero-is-not-false"),
        pytest.param({"enabled": "false"}, True, id="a-string-is-not-a-bool"),
        pytest.param({}, True, id="absent"),
    ],
)
def test_flag_reads_only_a_bool(raw: dict[str, object], expected: bool) -> None:
    assert HookConfig(raw, _SCHEMA).flag("enabled", True) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param({"mode": "enforce"}, "enforce", id="declared"),
        pytest.param({"mode": "block"}, "off", id="outside-the-order"),
        pytest.param({"mode": ""}, "off", id="empty"),
        pytest.param({"mode": ["ask"]}, "off", id="not-a-string"),
        pytest.param({}, "off", id="absent"),
    ],
)
def test_choice_outside_the_declared_order_is_the_default(
    raw: dict[str, object], expected: str
) -> None:
    assert HookConfig(raw, _SCHEMA).choice("mode", "off") == expected


@pytest.mark.parametrize(("value", "expected"), [("nightly", "nightly"), (3, "x"), (True, "x")])
def test_choice_of_a_key_without_an_order_reads_any_string(value: object, expected: str) -> None:
    assert HookConfig({"label": value}, _SCHEMA).choice("label", "x") == expected


@pytest.mark.parametrize("value", [True, False, "8", 2.5, None])
def test_integer_never_counts_a_bool(value: object) -> None:
    assert HookConfig({"cap": value}, _SCHEMA).integer("cap", 64) == 64


@pytest.mark.parametrize(("value", "expected"), [(0, 64), (-3, 64), (1, 1), (4096, 4096)])
def test_integer_below_the_minimum_is_the_default(value: int, expected: int) -> None:
    assert HookConfig({"cap": value}, _SCHEMA).integer("cap", 64, minimum=1) == expected


@pytest.mark.parametrize(
    ("value", "bounds", "expected"),
    [
        pytest.param(0, {"below": "clamp"}, 1, id="below-clamped"),
        pytest.param(0, {"below": "default"}, 2, id="below-default"),
        pytest.param(99, {"above": "clamp"}, 8, id="above-clamped"),
        pytest.param(99, {"above": "default"}, 2, id="above-default"),
        pytest.param(5, {"below": "clamp", "above": "clamp"}, 5, id="inside"),
    ],
)
def test_integer_clamps_when_asked(value: int, bounds: dict[str, Any], expected: int) -> None:
    config = HookConfig({"budget": value}, _SCHEMA)

    assert config.integer("budget", 2, minimum=1, maximum=8, **bounds) == expected


def test_strings_drop_empty_by_default() -> None:
    assert HookConfig({"hosts": _HOSTS}, _SCHEMA).strings("hosts") == (
        "pypi.org",
        "  ",
        "mirror.internal",
    )


def test_strings_keep_blanks_when_asked() -> None:
    """git_policy's rule: an empty glob stays (and never matches a non-empty identity)."""
    config = HookConfig({"hosts": _HOSTS}, _SCHEMA)

    assert config.strings("hosts", blanks="keep") == ("pypi.org", "", "  ", "mirror.internal")


def test_strings_drop_blank_strings_when_asked() -> None:
    config = HookConfig({"hosts": _HOSTS}, _SCHEMA)

    assert config.strings("hosts", blanks="drop_blank") == ("pypi.org", "mirror.internal")


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param({"hosts": "pypi.org"}, id="a-string-is-not-iterated"),
        pytest.param({"hosts": {"pypi.org": True}}, id="a-table"),
        pytest.param({"hosts": None}, id="null"),
        pytest.param({}, id="absent"),
    ],
)
def test_strings_of_a_non_list_is_the_default(raw: dict[str, object]) -> None:
    assert HookConfig(raw, _SCHEMA).strings("hosts", ("main",)) == ("main",)


def test_strings_of_an_empty_list_is_empty_not_the_default() -> None:
    config = HookConfig({"hosts": ["", 3]}, _SCHEMA)

    assert (config.strings("hosts", ("main",)), config.strings("hosts", blanks="keep")) == (
        (),
        ("",),
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(3, id="an-int"),
        pytest.param("a.html", id="a-string"),
        pytest.param(None, id="null"),
        pytest.param(["a.html", 3], id="a-non-string-item"),
    ],
)
def test_strict_strings_raise_naming_the_key(value: object) -> None:
    config = HookConfig({"hosts": value}, _SCHEMA)

    with pytest.raises(
        ValueError, match=r"^handler config 'hosts' must be a list of strings, got "
    ):
        config.strings("hosts", blanks="keep", strict=True)


def test_strict_strings_read_an_absent_key_or_a_list_of_str() -> None:
    absent = HookConfig({}, _SCHEMA).strings("hosts", ("x",), blanks="keep", strict=True)
    listed = HookConfig({"hosts": ["a", ""]}, _SCHEMA).strings("hosts", blanks="keep", strict=True)

    assert (absent, listed) == (("x",), ("a", ""))


def test_value_returns_regex_rows_verbatim() -> None:
    rows = [r"\bdrop\b", {"argv0": "kubectl", "regex": r"\bdelete\b", "decision": "deny"}, 3]
    config = HookConfig({"extra_rows": rows, "trailers": {"Refs": "#1"}}, _SCHEMA)

    assert config.value("extra_rows") is rows
    assert (config.value("trailers"), HookConfig({}, _SCHEMA).value("extra_rows")) == (
        {"Refs": "#1"},
        None,
    )


@pytest.mark.parametrize(
    "read",
    [
        pytest.param(lambda c: c.flag("enabeld", True), id="flag"),
        pytest.param(lambda c: c.choice("enabeld", "off"), id="choice"),
        pytest.param(lambda c: c.integer("enabeld", 1), id="integer"),
        pytest.param(lambda c: c.strings("enabeld"), id="strings"),
        pytest.param(lambda c: c.value("enabeld"), id="value"),
    ],
)
def test_an_undeclared_key_raises_naming_the_declared_keys(read: Read) -> None:
    config = HookConfig({"enabeld": True}, {"enabled": ConfigKey("boolean"), "cap": _SCHEMA["cap"]})

    with pytest.raises(KeyError, match=r"'enabeld' is not a config key .*declared: cap, enabled"):
        read(config)


@pytest.mark.parametrize(
    ("read", "message"),
    [
        pytest.param(lambda c: c.flag("cap", True), "flag('cap') reads a boolean key", id="flag"),
        pytest.param(
            lambda c: c.choice("hosts", "x"), "choice('hosts') reads a string", id="choice"
        ),
        pytest.param(lambda c: c.integer("mode", 1), "integer('mode') reads an integer", id="int"),
        pytest.param(
            lambda c: c.strings("extra_rows"), "strings('extra_rows') reads a list", id="list"
        ),
        pytest.param(
            lambda c: c.value("hosts"), "value('hosts') reads a regex or table", id="value"
        ),
    ],
)
def test_a_read_that_does_not_match_the_declared_kind_raises(read: Read, message: str) -> None:
    with pytest.raises(TypeError, match=re.escape(message)):
        read(HookConfig({}, _SCHEMA))


@pytest.mark.parametrize(
    ("read", "expected"),
    [
        pytest.param(lambda c: c.integer("budget", 1), 3, id="integer-of-a-number-key"),
        pytest.param(lambda c: c.value("trailers"), {"Refs": "#1"}, id="value-of-a-table-key"),
    ],
)
def test_a_read_of_a_compatible_kind_is_allowed(read: Read, expected: object) -> None:
    config = HookConfig({"budget": 3, "trailers": {"Refs": "#1"}}, _SCHEMA)

    assert read(config) == expected


def _is_ctx_config(node: ast.expr) -> bool:
    """``ctx.config`` or ``self.ctx.config``: a builtin's merged handler config."""
    if not isinstance(node, ast.Attribute) or node.attr != "config":
        return False
    owner = node.value
    return (isinstance(owner, ast.Name) and owner.id == "ctx") or (
        isinstance(owner, ast.Attribute) and owner.attr == "ctx"
    )


def _config_names(function: _Function) -> set[str]:
    """The names holding a handler config in ``function``: a ``config`` parameter or alias."""
    names = {arg.arg for arg in (*function.args.args, *function.args.kwonlyargs)}
    aliases = {
        target.id
        for node in ast.walk(function)
        if isinstance(node, ast.Assign) and _is_ctx_config(node.value)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    return (names & {"config"}) | aliases


def _raw_read_key(node: ast.expr, names: set[str]) -> ast.expr | None:
    """The key ``node`` reads raw from a handler config (``.get(key)`` or ``[key]``), else None."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
        owner = node.func.value
        named = isinstance(owner, ast.Name) and owner.id in names
        if node.func.attr == "get" and (named or _is_ctx_config(owner)):
            return node.args[0]
    if isinstance(node, ast.Subscript) and _is_ctx_config(node.value):
        return node.slice
    return None


def _spelled_keys(key: ast.expr) -> frozenset[object]:
    """The literal keys ``key`` evaluates to (each arm of a conditional); empty when not literal."""
    if isinstance(key, ast.IfExp):
        body, orelse = _spelled_keys(key.body), _spelled_keys(key.orelse)
        return body | orelse if body and orelse else frozenset()
    return frozenset({key.value}) if isinstance(key, ast.Constant) else frozenset()


def _sync_written(key: ast.expr, allowed: frozenset[str]) -> bool:
    """Whether every key ``key`` can spell is one of the file's ``allowed`` sync-written keys."""
    spelled = _spelled_keys(key)
    return bool(spelled) and spelled <= allowed


def _raw_reads(function: _Function) -> Iterator[tuple[int, ast.expr]]:
    """``(line, key)`` of each raw handler-config read in ``function``."""
    names = _config_names(function)
    for node in (n for n in ast.walk(function) if isinstance(n, ast.expr)):
        key = _raw_read_key(node, names)
        if key is not None:
            yield node.lineno, key


def _raw_config_reads(source: str, sync_written: frozenset[str]) -> list[int]:
    """The lines of ``source`` that read a handler-config key without ``HookConfig``.

    A raw read of one of the ``sync_written`` keys (no ``CONFIG_SCHEMA`` declares them) is
    not counted; any other key, declared or not, is.
    """
    functions = [f for f in ast.walk(ast.parse(source)) if isinstance(f, _Function)]
    reads = (read for function in functions for read in _raw_reads(function))
    return sorted({line for line, key in reads if not _sync_written(key, sync_written)})


def _sync_written_keys(path: Path) -> frozenset[str]:
    """The sync-written keys ``_SYNC_WRITTEN_READS`` lets the module at ``path`` read raw."""
    return frozenset(key for name, key in _SYNC_WRITTEN_READS if name == path.name)


def _builtin_sources(root: Path) -> list[Path]:
    """Every module of ``root``'s builtin packages, pack subpackages included, minus the allowlist."""
    return [
        path
        for folder in _BUILTIN_DIRS
        for path in sorted((root / folder).rglob("*.py"))
        if path.name not in _RAW_READS_ALLOWED
    ]


def _builtin_handler_files() -> set[Path]:
    """The source file of every registered in-tree builtin handler."""
    specs = (find_spec(module) for module in builtin_handler_modules().values())
    return {Path(spec.origin) for spec in specs if spec is not None and spec.origin is not None}


def test_the_config_read_guard_finds_each_raw_read_shape() -> None:
    source = (
        "def handler(ev, ctx):\n"
        "    a = ctx.config.get('mode')\n"
        "    b = ctx.config['mode']\n"
        "    config = self.ctx.config\n"
        "    c = config.get('mode')\n"
        "    d = ctx.config.get('install_hint')\n"
        "    g = ctx.config.get('retain_dayz')\n"
        "    h = ctx.config.get('cz_install_hint' if tool == 'cz' else 'install_hint')\n"
        "    i = ctx.config.get('install_hint' if tool == 'cz' else 'mode')\n"
        "def helper(config, rows):\n"
        "    e = config.get(KEY)\n"
        "    f = rows.get('mode')\n"
    )

    allowed = frozenset({"install_hint", "cz_install_hint"})

    assert _raw_config_reads(source, allowed) == [2, 3, 5, 7, 9, 11]


def test_the_config_read_guard_walks_pack_subpackages(tmp_path: Path) -> None:
    for rel in (
        "handlers/audit/log.py",
        "handlers/top.py",
        "handlers/ruff_feedback.py",
        "stop/x.py",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")

    found = [path.relative_to(tmp_path).as_posix() for path in _builtin_sources(tmp_path)]

    assert found == ["handlers/audit/log.py", "handlers/top.py", "stop/x.py"]


def test_the_config_read_guard_scans_every_registered_builtin() -> None:
    sources = set(_builtin_sources(Path(hook_runtime.__file__).parent))
    expected = {path for path in _builtin_handler_files() if path.name not in _RAW_READS_ALLOWED}

    assert expected, "no registered builtin handler module was found"
    assert expected - sources == set()


def test_in_tree_builtins_read_their_config_through_hook_config() -> None:
    root = Path(hook_runtime.__file__).parent
    sources = _builtin_sources(root)
    offenders = [
        f"{path.relative_to(root)}:{line}"
        for path in sources
        for line in _raw_config_reads(path.read_text(encoding="utf-8"), _sync_written_keys(path))
    ]

    assert sources, f"no builtin modules under {_BUILTIN_DIRS} of {root}"
    assert offenders == []
