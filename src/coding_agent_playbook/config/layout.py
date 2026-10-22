"""The document layout of a consumer repo: the ``[layout]`` table and its prefix rewriter (D60, D71).

D60 fixes where the engineering documents live (``CONTEXT.md``, ``docs/adr``,
``docs/specs``…); D71 makes each place configurable in the committed config::

    [layout]
    specs = "specs"

A key left out keeps its D60 default (:data:`LAYOUT_DEFAULTS`), so a repo that sets
nothing gets exactly D60. Every framework writes its paths in the default form; when
a key differs from its default, ``playbook sync`` rewrites that default path prefix
in the synced files (:class:`LayoutRewriter`), and the prefixes a framework declares
in ``framework.toml``'s ``[layout_aliases]`` map to the configured place too. File
name patterns (``YYYY-MM-DD-<slug>.md``) are never touched. A stdlib-only module:
``config.framework`` imports :data:`LAYOUT_KEYS` from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The D60 default of each D71 layout key, in the spec's order. Directories are
#: written without a trailing slash; ``glossary``, ``context_map`` and
#: ``architecture`` are files.
LAYOUT_DEFAULTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "glossary": "CONTEXT.md",
        "context_map": "CONTEXT-MAP.md",
        "adr": "docs/adr",
        "architecture": "docs/architecture.md",
        "specs": "docs/specs",
        "plans": "docs/plans",
        "research": "docs/research",
        "agents": "docs/agents",
        "scratch": ".scratch",
    }
)
#: The layout keys of D71, in the spec's order; a layout alias maps to one.
LAYOUT_KEYS: Final = tuple(LAYOUT_DEFAULTS)
#: The committed config's table name.
LAYOUT_TABLE: Final = "layout"

# A path prefix starts where no path character precedes it (``mydocs/specs`` and
# ``x/docs/specs`` are other paths), or right after a ``./`` that itself starts one.
_PATH_START: Final = r"(?:(?<![\w./-])|(?<=(?<![\w./-])\./))"
# ... and ends at ``/``, at a sentence's full stop, or at any other non-path character
# (``docs/specs-old`` and ``docs/specs.md`` are other paths).
_PATH_END: Final = r"(?=/|\.(?!\w)|[^\w.-]|\Z)"


def resolve_layout(explicit: Mapping[str, str]) -> dict[str, str]:
    """Every layout key's path: ``explicit``'s value, else the D60 default.

    Example::

        >>> resolve_layout({"specs": "specs"})["specs"], resolve_layout({})["plans"]
        ('specs', 'docs/plans')
    """
    return {key: explicit.get(key, default) for key, default in LAYOUT_DEFAULTS.items()}


def layout_table_problems(data: Mapping[str, object]) -> list[str]:
    """Why the ``[layout]`` table of ``data`` (a decoded config file) is refused; ``[]`` if sound.

    The table holds only :data:`LAYOUT_KEYS`; each value is a non-empty relative POSIX
    path inside the repo: no leading ``/`` or drive, no backslash, no ``..``, ``.``
    or empty segment, and no trailing ``/``. Each problem names its key (D71);
    ``config.schema.check_layout_table`` raises them as one ``ConfigError``.

    Example::

        >>> layout_table_problems({"layout": {"spec": "s"}})  # doctest: +ELLIPSIS
        ["[layout] unknown key 'spec'; known keys: glossary, ..."]
    """
    if LAYOUT_TABLE not in data:
        return []
    table = data[LAYOUT_TABLE]
    if not isinstance(table, dict):
        return [f'[layout] must be a table like {{specs = "docs/specs"}}, got {table!r}']
    return [
        f"[layout] {problem}"
        for key, value in table.items()
        if (problem := _key_problem(key, value)) is not None
    ]


def _key_problem(key: str, value: object) -> str | None:
    """Why ``key = value`` is refused, or ``None`` when it is a usable layout path."""
    if key not in LAYOUT_DEFAULTS:
        return f"unknown key {key!r}; known keys: {', '.join(LAYOUT_KEYS)}"
    if not isinstance(value, str) or not value.strip():
        return f"{key} must be a non-empty string, got {value!r}"
    return _path_problem(key, value)


def _path_problem(key: str, value: str) -> str | None:
    """Why ``value`` is not a plain relative path inside the repo, or ``None``."""
    hint = f'write it relative to the repo root, like {key} = "{LAYOUT_DEFAULTS[key]}"'
    if value.startswith(("/", "~")) or "\\" in value or re.match(r"^[A-Za-z]:", value):
        return f"{key} must be a relative path inside the repo, got {value!r}; {hint}"
    if value.endswith("/"):
        return f"{key} must not end with '/', got {value!r}; {hint}"
    segments = value.split("/")
    if ".." in segments:
        return f"{key} must not contain a '..' segment, got {value!r}; {hint}"
    if any(segment in ("", ".") for segment in segments):
        return f"{key} must not contain a '.' or empty segment, got {value!r}; {hint}"
    return None


@dataclass(frozen=True, order=True)
class RewriteCount:
    """How many times one prefix was rewritten in one text.

    Example: ``RewriteCount("docs/specs", "specs", 3)``.
    """

    source: str
    target: str
    occurrences: int


@dataclass(frozen=True)
class LayoutRewriter:
    """Rewrites default (and alias) path prefixes to the configured layout, in one pass.

    Built with :meth:`for_layout`; falsy when it rewrites nothing, which is the
    case for the default layout without aliases, so sync output stays
    byte-identical to the output without the adapter.

    Example::

        >>> LayoutRewriter.for_layout({"specs": "specs"}).rewrite("docs/specs/x.md")[0]
        'specs/x.md'
    """

    targets: Mapping[str, str]

    @classmethod
    def for_layout(
        cls, explicit: Mapping[str, str], *, aliases: Mapping[str, str] | None = None
    ) -> LayoutRewriter:
        """The rewriter for a ``[layout]`` table and the enabled frameworks' aliases.

        A key rewrites its default only when its configured path differs; an alias
        (``"docs/superpowers/plans/" = "plans"``) always maps to the configured path
        of its key, the D60 default included: a framework that declares aliases
        writes into the document layout even when the repo sets no ``[layout]``
        (D71; the layout guard blocks the framework's own paths either way).

        Example::

            >>> bool(LayoutRewriter.for_layout({"specs": "docs/specs"}))
            False
        """
        resolved = resolve_layout(explicit)
        targets = {
            default: resolved[key]
            for key, default in LAYOUT_DEFAULTS.items()
            if resolved[key] != default
        }
        for prefix, key in (aliases or {}).items():
            source = prefix.rstrip("/")
            if key in resolved and source != resolved[key]:
                targets[source] = resolved[key]
        return cls(MappingProxyType(targets))

    def __bool__(self) -> bool:
        return bool(self.targets)

    def rewrite(self, text: str) -> tuple[str, tuple[RewriteCount, ...]]:
        """``text`` with every prefix rewritten, and the counts per prefix (sorted).

        One regex pass, longest prefix first, so a rewritten path is never
        rewritten again.

        Example::

            >>> LayoutRewriter.for_layout({"adr": "adr"}).rewrite("docs/adr/0001-x.md")
            ('adr/0001-x.md', (RewriteCount(source='docs/adr', target='adr', occurrences=1),))
        """
        if not self.targets:
            return text, ()
        counts: dict[str, int] = {}

        def _replace(match: re.Match[str]) -> str:
            source = match.group(0)
            counts[source] = counts.get(source, 0) + 1
            return self.targets[source]

        rewritten = self._pattern().sub(_replace, text)
        return rewritten, tuple(
            sorted(RewriteCount(source, self.targets[source], n) for source, n in counts.items())
        )

    def _pattern(self) -> re.Pattern[str]:
        alternatives = "|".join(
            self._alternative(source) for source in sorted(self.targets, key=len)[::-1]
        )
        return re.compile(f"{_PATH_START}(?:{alternatives}){_PATH_END}")

    def _alternative(self, source: str) -> str:
        """``source`` as a regex that skips text already holding its own target.

        prU L0-28: when the target extends its source (``docs/specs`` ->
        ``docs/specs/v2``), ``docs/specs/v2/x`` must stay as it is, or a second
        rewrite (and the rendered document-layout rule) would read ``docs/specs/v2/v2``.
        """
        target = self.targets[source]
        if not target.startswith(f"{source}/"):
            return re.escape(source)
        return f"{re.escape(source)}(?!{re.escape(target[len(source) :])}{_PATH_END})"
