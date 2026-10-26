"""The checks a config file must pass, and :class:`ConfigError` for one that fails (SPEC §7.1).

``.coding-agent-playbook.toml`` and ``.coding-agent-playbook.local.toml`` are
each checked on their own, before the SPEC §7.2 merge, so an error names the
file at fault: the enabled lists (:func:`check_enabled_keys`), the tables
``Config`` reads (:func:`check_config_tables`), and, on the merged result, the
keys ``Config`` has no default for (:func:`required_value`). A leaf module, split
from ``config.py`` (v0.18; now ``config/model.py``); callers import these names
from here.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Any, TypeGuard

from coding_agent_playbook import toml_writer as _toml
from coding_agent_playbook.catalog.roots import canonical_overlay_name
from coding_agent_playbook.config.framework import BUNDLED_FRAMEWORK_NAMES
from coding_agent_playbook.config.layout import layout_table_problems
from coding_agent_playbook.detector.platform_facts import KNOWN_PLATFORMS, PLATFORMS_KEY

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class ConfigError(ValueError):
    """A config file the engine refuses to load (SPEC §7.1).

    Raised for a file ``tomllib`` cannot read (bad syntax, not UTF-8, nested too
    deeply; ``config.files``) and for content that parses as TOML in a
    shape the engine is known to misread: the enabled-list mistakes
    :func:`check_enabled_keys` catches, a table ``Config`` reads that is not one
    (:func:`check_config_tables`), a malformed ``[output]``
    (``config.model.parse_output_config``), and a missing required key
    (``schema_version``, ``[project] name``/``kind``, ``[engine] version``;
    :func:`required_value`). Other unknown keys are still
    ignored. A ``ValueError`` subclass, so existing
    ``except ValueError`` callers still catch it; the CLI reports it as
    ``error: <message>``, exit 2.

    Example::

        >>> raise ConfigError("cfg.toml: the [overlays] table is not read")
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: cfg.toml: the [overlays] table is not read
    """


_OVERLAYS_KEY = "overlays_enabled"

#: The top-level list keys ``Config`` reads, with the placeholder a fix-it hint
#: shows when there is no usable value to quote back.
_ENABLED_KEYS: dict[str, str] = {
    _OVERLAYS_KEY: "[<package names>]",
    "adapters_enabled": "[<adapter names>]",
}

#: Legacy names a user may write instead (``[overlays] enabled = [...]``, as the
#: docs once showed), mapped to the key that is actually read.
_LEGACY_NAMES: dict[str, str] = {
    "overlays": "overlays_enabled",
    "adapters": "adapters_enabled",
}

#: Where the enabled keys must go. Every fix-it hint says so: replacing a
#: ``[overlays]`` table with the key *in place* would nest it in the table above.
_PLACEMENT = "at the top of the file, above the first [table] header"

_NESTED_NOTE = "TOML puts every key written after a [table] header in that table"

#: How close a key must be to an enabled key to be refused as its misspelling.
_MISSPELLING_SIMILARITY = 0.8

#: A table path: ``()`` for the top level, ``("detector_cache", "frameworks")``…
_TablePath = tuple[str, ...]


def check_enabled_keys(data: Mapping[str, object], *, source: str) -> None:
    """Refuse the enabled-list shapes ``Config`` would silently misread (SPEC §7.1).

    Only the top-level ``overlays_enabled`` / ``adapters_enabled`` lists of
    non-empty strings are read. Each of these was silently ignored before and is
    now refused: an ``[overlays]`` / ``[adapters]`` table (or the dotted
    ``overlays.enabled = …`` key), an enabled key written after a ``[table]``
    header (TOML nests it in that table, at any depth), and a close misspelling
    such as ``overlay_enabled``. Ignored, they read as empty lists, so
    ``playbook sync`` rendered with only ``agents_md`` and deleted the other
    adapters' earlier output as leftovers. A string value (which became a list
    of characters) and an empty name are refused too. ``source`` names the file
    in every message line; every problem found is reported in one error.

    Example::

        >>> check_enabled_keys({"adapters_enabled": ["claude_code"]}, source="cfg.toml")
        >>> check_enabled_keys({"adapters": {}}, source="cfg.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: cfg.toml: the [adapters] table is not read ...
    """
    problems = [
        problem
        for path, table in _iter_tables(data)
        for key, value in table.items()
        if (problem := _key_problem(path, key, value)) is not None
    ]
    if problems:
        raise ConfigError("\n".join(f"{source}: {problem}" for problem in problems))


def _iter_tables(
    table: Mapping[str, object], path: _TablePath = ()
) -> Iterator[tuple[_TablePath, Mapping[str, object]]]:
    """Yield ``table`` and, depth first, every table nested in it, with its path.

    Arrays of tables (``[[x]]``) are walked too, under the array's own name.
    Iterative: ``tomllib`` builds ``[a.b.c…]`` headers with no depth limit, and
    the recursive walk raised ``RecursionError`` (a traceback, exit 1) at ~990.
    """
    pending: list[tuple[_TablePath, Mapping[str, object]]] = [(path, table)]
    while pending:
        current_path, current = pending.pop()
        yield current_path, current
        pending.extend(reversed(_child_tables(current_path, current)))


def _child_tables(
    path: _TablePath, table: Mapping[str, object]
) -> list[tuple[_TablePath, Mapping[str, object]]]:
    """The tables directly inside ``table`` (an array of tables' elements included), in order."""
    children: list[tuple[_TablePath, Mapping[str, object]]] = []
    for key, value in table.items():
        items = value if isinstance(value, list) else [value]
        children.extend(((*path, key), item) for item in items if isinstance(item, dict))
    return children


def _key_problem(path: _TablePath, key: str, value: object) -> str | None:
    """Why ``key`` (in the table at ``path``) is misread, or ``None`` when it is fine."""
    if not path and key in _ENABLED_KEYS:
        return _list_value_problem(key, value)
    target = _intended_enabled_key(path, key, value)
    return None if target is None else _misplaced_key_problem(path, key, value, target)


def _intended_enabled_key(path: _TablePath, key: str, value: object) -> str | None:
    """The enabled key ``key`` was meant as although it is not read there, else ``None``.

    A legacy name only counts nested when it holds an ``enabled`` table, so a
    framework called ``adapters`` in ``[detector_cache.frameworks]`` still loads.
    """
    if key in _ENABLED_KEYS:
        return key  # only reached nested: the top level is read as written
    if key in _LEGACY_NAMES:
        legacy = not path or (isinstance(value, dict) and "enabled" in value)
        return _LEGACY_NAMES[key] if legacy else None
    return _misspelled_enabled_key(key)


def _misspelled_enabled_key(key: str) -> str | None:
    """The enabled key ``key`` is a close misspelling of, else ``None``.

    Compared case-insensitively with ``-`` as ``_`` and the words sorted, so
    ``Overlays-Enabled`` and ``enabled_adapters`` match as well as ``overlay_enabled``.
    """
    normalized = {_normalized_key(name): name for name in _ENABLED_KEYS}
    close = difflib.get_close_matches(
        _normalized_key(key), normalized, n=1, cutoff=_MISSPELLING_SIMILARITY
    )
    return normalized[close[0]] if close else None


def _normalized_key(key: str) -> str:
    """``key`` lowercased, split on ``_``/``-``, its words sorted and rejoined with ``_``."""
    return "_".join(sorted(key.lower().replace("-", "_").split("_")))


def _misplaced_key_problem(path: _TablePath, key: str, value: object, target: str) -> str:
    """Say where ``key`` is and why it is not read, then the exact top-level line to write."""
    notes = [_NESTED_NOTE] if path else []
    if key not in _ENABLED_KEYS and key not in _LEGACY_NAMES:
        notes.append(f"did you mean {target}?")
    why = f" ({'; '.join(notes)})" if notes else ""
    listed = value.get("enabled") if isinstance(value, dict) else value
    return (
        f"{_describe_key(path, key, value)} is not read (found {value!r}){why}; "
        f"use the top-level key instead, {_PLACEMENT}: {target} = {_replacement(target, listed)}"
    )


def _describe_key(path: _TablePath, key: str, value: object) -> str:
    """``the [overlays] table``, ``the top-level key 'x'``, or ``'x' in the [engine] table``."""
    if isinstance(value, dict) and key in _LEGACY_NAMES:
        return f"the [{'.'.join((*path, key))}] table"
    if not path:
        return f"the top-level key {key!r}"
    return f"{key!r} in the [{'.'.join(path)}] table"


def _list_value_problem(key: str, value: object) -> str | None:
    """Say why ``value`` is not a usable ``key`` list, or ``None`` when it is one."""
    if not _is_str_list(value):
        replacement = _replacement(key, value)
        return f"{key} must be a list of strings, got {value!r}; write {key} = {replacement}"
    if any(not item.strip() for item in value):
        # An empty name reached importlib and crashed every command with a traceback.
        return f"{key} lists an empty name, got {value!r}; remove the empty entry"
    return None


def _replacement(key: str, listed: object) -> str:
    """The value to show in ``key = …``: ``listed`` itself when usable, else a placeholder.

    A lone string is the common slip, so it is quoted back as the one-element list.
    Overlay names are shown canonical, so the hint never recommends the deprecated
    ``coding_agent_playbook.packs.*`` spelling (SPEC v0.19).
    """
    names = [listed] if isinstance(listed, str) else listed
    if not _is_str_list(names):
        return _ENABLED_KEYS[key]
    if key == _OVERLAYS_KEY:
        names = [canonical_overlay_name(name) for name in names]
    return _toml.format_scalar(names)


def _is_str_list(value: object) -> TypeGuard[list[str]]:
    """True for a list whose every item is a ``str`` (an empty list included)."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


#: The keys ``Config.from_dict`` has no default for, each with the line that supplies it.
_REQUIRED_KEYS: dict[tuple[str, ...], str] = {
    ("schema_version",): "schema_version = 1 at the top of the file",
    ("project", "name"): 'name = "<project name>" under the [project] header',
    ("project", "kind"): 'kind = "<project kind>" under the [project] header',
    ("engine", "version"): 'version = "<engine version>" under the [engine] header',
}


#: The top-level keys ``Config`` reads as tables, each with the fix-it hint for a non-table.
_TABLE_HINTS: dict[str, str] = {
    "project": f"write {_REQUIRED_KEYS[('project', 'name')]}",
    "engine": f"write {_REQUIRED_KEYS[('engine', 'version')]}",
    "storage": 'write state_source = "filesystem" under the [storage] header',
    "output": "write commit = false under the [output] header",
    "detector_cache": "delete the line; `playbook check --refresh` writes the table",
    "user_choices": "write each choice as key = value under the [user_choices] header",
}


def check_config_tables(data: Mapping[str, object], *, source: str) -> None:
    """Refuse a top-level table ``Config`` reads that holds something else (SPEC §7.1).

    ``project = "x"`` or ``user_choices = "x"`` used to reach ``Config.from_dict``
    as a ``TypeError``/``AttributeError``/``ValueError`` traceback (exit 1), or to
    pass unseen while the other file's table replaced it in the §7.2 merge, until
    ``init``/``check --refresh`` read the committed file alone and crashed.
    ``ConfigFiles`` runs it on each file before the merge (through
    ``config.model.check_config_file``, which also checks ``[output] commit``), so the
    error names the file at fault. Every non-table is listed in one error.

    Example::

        >>> check_config_tables({"project": "x"}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: [project] must be a table, ...
    """
    problems = [
        f"{source}: [{key}] must be a table, got {data[key]!r}; {hint}"
        for key, hint in _TABLE_HINTS.items()
        if key in data and not isinstance(data[key], dict)
    ]
    if problems:
        raise ConfigError("\n".join(problems))


def required_value(data: Mapping[str, Any], path: tuple[str, ...], *, source: str) -> Any:
    """The value at ``path`` (a key of :data:`_REQUIRED_KEYS`) in ``data``, or a ``ConfigError``.

    A missing key used to escape as a ``KeyError`` traceback; the error now names
    ``source``, the key and the line to write, and the CLI exits 2 (SPEC §7.1).
    Call it after :func:`check_config_tables`, which makes every table on the
    way a ``dict`` (``project = "x"`` was a ``TypeError``).

    Example::

        >>> required_value({"engine": {}}, ("engine", "version"), source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: the required key engine.version ...
    """
    value: Any = data
    for key in path:
        if key not in value:
            raise ConfigError(
                f"{source}: the required key {'.'.join(path)} is missing; "
                f"write {_REQUIRED_KEYS[path]}"
            )
        value = value[key]
    return value


_FRAMEWORK_KEY = "framework"

#: Spellings of ``framework`` refused wherever they hold a value but are not read:
#: TOML nests a key written after a ``[table]`` header (init writes
#: ``[detector_cache.frameworks]`` last), and ``Config`` reads only the top-level
#: ``framework``, so a switch appended at the end of the file did nothing (D57).
_FRAMEWORK_SPELLINGS = (_FRAMEWORK_KEY, "frameworks")


def check_framework_key(data: Mapping[str, object], *, source: str) -> None:
    """Refuse a ``framework`` that is not a non-empty name, or that is not read (D57).

    The value is a bundled framework's short name (``superpowers``,
    ``mattpocock``), an overlay module name, or ``none``; which layer it names is
    resolved later (``config.framework``), so a misspelt name is reported by the
    overlay preflight, not here. Like the enabled lists (:func:`check_enabled_keys`),
    a ``framework`` (or ``frameworks``) value inside a table, and a top-level
    ``frameworks``, are refused with the line to write instead; a table is never
    refused, so ``[detector_cache.frameworks]`` still loads.

    Example::

        >>> check_framework_key({"framework": 1}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: framework must be ...
    """
    problems = [
        problem
        for path, table in _iter_tables(data)
        for key, value in table.items()
        if (problem := _framework_key_problem(path, key, value)) is not None
    ]
    if problems:
        raise ConfigError("\n".join(f"{source}: {problem}" for problem in problems))


def _framework_key_problem(path: _TablePath, key: str, value: object) -> str | None:
    """Why ``key`` (in the table at ``path``) is a misread ``framework``, else ``None``."""
    if key not in _FRAMEWORK_SPELLINGS or isinstance(value, dict):
        return None
    if not path and key == _FRAMEWORK_KEY:
        return None if _is_name(value) else _framework_value_problem(value)
    notes = [_NESTED_NOTE] if path else []
    if key != _FRAMEWORK_KEY:
        notes.append(f"did you mean {_FRAMEWORK_KEY}?")
    shown = _toml.format_scalar(value) if _is_name(value) else '"<framework name>"'
    return (
        f"{_describe_key(path, key, value)} is not read (found {value!r}) "
        f"({'; '.join(notes)}); use the top-level key instead, {_PLACEMENT}: "
        f"{_FRAMEWORK_KEY} = {shown}"
    )


def _framework_value_problem(value: object) -> str:
    """The message for a top-level ``framework`` that is not a non-empty name."""
    bundled = ", ".join(f'"{name}"' for name in BUNDLED_FRAMEWORK_NAMES)
    return (
        f"framework must be a framework name such as {bundled}, "
        f'an overlay module name or "none", got {value!r}'
    )


def check_platforms_key(data: Mapping[str, object], *, source: str) -> None:
    """Refuse a ``platforms`` key the detector would ignore (prU D63).

    Only a top-level list of :data:`KNOWN_PLATFORMS` names is read
    (``detector.platform_facts.committed_platforms``); ``platforms = ["domino"]``
    turns the Domino skills on in a repo with no Domino marker yet. A string, an
    unknown name, or a ``platforms`` value nested in a table (written after a
    ``[table]`` header) is refused with the line to write instead.

    Example::

        >>> check_platforms_key({"platforms": "domino"}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: platforms must be a list ...
    """
    problems = [
        problem
        for path, table in _iter_tables(data)
        if PLATFORMS_KEY in table
        and (problem := _platforms_problem(path, table[PLATFORMS_KEY])) is not None
    ]
    if problems:
        raise ConfigError("\n".join(f"{source}: {problem}" for problem in problems))


def check_layout_table(data: Mapping[str, object], *, source: str) -> None:
    """Refuse a ``[layout]`` the layout adapter cannot use, naming ``source`` and each key (D71).

    An unknown key, an absolute path, a ``..`` segment or a trailing ``/`` would make
    ``playbook sync`` rewrite paths to somewhere outside the repo or to nothing, so
    the config does not load (``config.layout.layout_table_problems`` says why).

    Example::

        >>> check_layout_table({"layout": {"specs": "/s"}}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: [layout] specs must be a relative ...
    """
    problems = layout_table_problems(data)
    if problems:
        raise ConfigError("\n".join(f"{source}: {problem}" for problem in problems))


def _platforms_problem(path: _TablePath, value: object) -> str | None:
    """Why ``platforms`` (in the table at ``path``) is not read as written, else ``None``."""
    # A nested table of that name is someone else's (``[detector_cache.platforms]``);
    # a top-level ``[platforms]`` table is refused below, since the detector ignores it.
    if path and isinstance(value, dict):
        return None
    if path:
        return (
            f"{_describe_key(path, PLATFORMS_KEY, value)} is not read (found {value!r}) "
            f"({_NESTED_NOTE}); use the top-level key instead, {_PLACEMENT}: "
            f"{PLATFORMS_KEY} = {_platforms_value(value)}"
        )
    if not _is_str_list(value):
        return (
            f"{PLATFORMS_KEY} must be a list of platform names, got {value!r}; "
            f"write {PLATFORMS_KEY} = {_platforms_value(value)}"
        )
    unknown = sorted(set(value) - KNOWN_PLATFORMS)
    if unknown:
        return (
            f"{PLATFORMS_KEY} names unknown platform(s) {unknown}; "
            f"known platforms: {sorted(KNOWN_PLATFORMS)}"
        )
    return None


def _platforms_value(value: object) -> str:
    """The list to show in ``platforms = …``: ``value`` when usable (a lone string listed), else an example."""
    names = [value] if isinstance(value, str) else value
    return _toml.format_scalar(names) if _is_str_list(names) else '["domino"]'


_PROMPTS_KEY = "prompts"

#: Why a config that still sets ``prompts`` fails to load (ADR 0012, #300).
PROMPTS_KEY_REMOVED = (
    "retired key 'prompts': it was removed because consumer repos always get the "
    "current text of the release they install; delete the 'prompts' line"
)


def check_prompts_key(data: Mapping[str, object], *, source: str) -> None:
    """Refuse a top-level ``prompts``, the removed prompt-set key (ADR 0012), naming ``source``.

    A repo once picked ``"v1"`` or ``"v2"`` prompts with it; a sync now always
    renders the current text, so a config that still sets it fails to load rather
    than silently rendering other text than its author expects.

    Example::

        >>> check_prompts_key({"prompts": "v2"}, source="c.toml")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        coding_agent_playbook.config.schema.ConfigError: c.toml: retired key 'prompts': ...
    """
    if _PROMPTS_KEY in data:
        raise ConfigError(f"{source}: {PROMPTS_KEY_REMOVED}")


def _is_name(value: object) -> TypeGuard[str]:
    """True for a non-blank string."""
    return isinstance(value, str) and bool(value.strip())
