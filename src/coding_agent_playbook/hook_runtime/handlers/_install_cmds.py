"""Install-shaped shell segments: what a command asks a package manager to fetch (specs/prK-hook-pack.md §E.4).

dependency-allowlist-guard judges these requests and taint-escalation asks
before any of them once the session read untrusted content, so one parser
serves both. Tokens only, never a substring: ``echo pip install x`` installs
nothing. Recognized:

- direct commands (``segment.argv``): ``pip``/``pip3``/``python -m pip``
  ``install|download|wheel``, ``uv add``, ``uv pip install``, ``uv tool
  install|run``, ``pipx install|run``, ``poetry add``, ``pdm add``,
  ``conda|mamba|micromamba install|create``, ``npm install|i|add|exec`` and
  ``npx``;
- runner launchers the shell parser unwraps (``uvx``, ``uv run --with``,
  ``pipx run``): read from ``raw_argv``, since the effective argv is then the
  tool being run.

Names are PEP 503-normalized (``_pep503``); a self-install (``-e .``,
``".[dev]"``, a local path) names nothing, and ``-r FILE`` is returned as a
file for the caller to read. ``uv sync``, ``uv run`` without ``--with``, ``npm
ci`` and a bare ``npm install`` request nothing.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook._pep503 import canonical_name, requirement_names
from coding_agent_playbook.hook_runtime.handlers._cli_words import (
    CliWords,
    split_words,
    value_options,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["DEFAULT_INDEXES", "Index", "InstallRequest", "install_requests"]

type Ecosystem = Literal["python", "conda", "node"]
type _Reader = Callable[[list[str]], InstallRequest | None]
#: An index a command names: ``primary`` replaces the default, ``extra`` is mixed in.
type Index = tuple[Literal["primary", "extra"], str]


#: The default index; naming it as ``--index-url`` is not index mixing.
DEFAULT_INDEXES: Final = frozenset({"https://pypi.org/simple", "https://pypi.python.org/simple"})
#: The installer's own bootstrap (``pip install -U pip``) is not a project dependency.
_BOOTSTRAP: Final = frozenset({"pip", "setuptools", "wheel", "python"})
_PIP: Final = re.compile(r"^pip(?:\d+(?:\.\d+)?)?$")
_PYTHON: Final = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")
_LOCAL: Final = re.compile(r"^(?:\.{1,2}(?:[/\[]|$)|/|~|file:)")
_PRIMARY: Final = frozenset({"-i", "--index-url", "--default-index"})
_EXTRA: Final = frozenset({"--extra-index-url", "--index"})
_FILES: Final = frozenset({"-r", "--requirement", "--requirements", "--with-requirements"})
_WITH: Final = frozenset({"--with"})
_DEV: Final = frozenset({"--dev", "-D", "--save-dev", "-d"})
_DEV_GROUPS: Final = frozenset({"--group", "-G", "--optional"})
_COMMON_VALUES: Final = frozenset(
    {*_PRIMARY, *_EXTRA, *_FILES, *_WITH, *_DEV_GROUPS, "-c", "--constraint", "-p", "--python"}
)
_PIP_VALUES: Final = _COMMON_VALUES | value_options(
    "-e --editable -f --find-links -t --target --prefix --root --src --platform "
    "--python-version --implementation --abi --no-binary --only-binary --progress-bar "
    "--upgrade-strategy -d --dest -w --wheel-dir --trusted-host --proxy --retries --timeout "
    "--exists-action --cert --client-cert --cache-dir --log --config-settings -C "
    "--global-option --build-option --report --root-user-action --keyring-provider"
)
_UV_VALUES: Final = _COMMON_VALUES | value_options(
    "--from -w --with-editable --rev --tag --branch --extra --package --script --directory "
    "--project --bounds --marker -m --constraints --overrides --index-strategy "
    "--keyring-provider --resolution --prerelease --exclude-newer --link-mode --cache-dir "
    "--config-file --color -C --config-setting -P --upgrade-package --reinstall-package "
    "--refresh-package --python-platform --target --prefix --env-file -f --find-links"
)
_PIPX_VALUES: Final = _COMMON_VALUES | value_options("--spec --pip-args --suffix --preinstall")
_POETRY_VALUES: Final = _COMMON_VALUES | value_options("-E --extras --source --markers -C")
_CONDA_VALUES: Final = _COMMON_VALUES | value_options(
    "-n --name --prefix --channel --file --solver --repodata-fn"
)
_NPM_VALUES: Final = value_options("--registry --prefix -w --workspace --tag --omit -p --package")
_CONDA: Final = frozenset({"conda", "mamba", "micromamba"})


@dataclass(frozen=True, slots=True)
class InstallRequest:
    """One install-shaped command: who fetches what, from which index.

    ``adder`` is the project manager the command adds through (``pip``,
    ``uv pip``, ``uv``, ``poetry``, ``pdm``), ``None`` for a tool run or a
    non-Python ecosystem; ``files`` are its ``-r`` files, as written.

    Example::

        >>> install_requests(parse("pip install Foo_Bar")[0])[0].names  # doctest: +SKIP
        ('foo-bar',)
    """

    tool: str
    ecosystem: Ecosystem
    adder: str | None = None
    names: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    indexes: tuple[Index, ...] = ()
    dev: bool = False


def install_requests(segment: Segment) -> list[InstallRequest]:
    """Every install request ``segment`` makes: its own command, then a runner launcher's.

    Example::

        >>> [r.tool for r in install_requests(parse("uvx --from git+https://x/r ruff")[0])]
        ... # doctest: +SKIP
        ['uvx']
    """
    found = [request for request in (_direct(segment.argv),) if request is not None]
    found.extend(_runner(segment))
    return found


def _direct(argv: Sequence[str]) -> InstallRequest | None:
    if not argv:
        return None
    program = posixpath.basename(argv[0])
    if _PYTHON.match(program) and list(argv[1:3]) == ["-m", "pip"]:
        return _pip(argv[3:], "pip")
    if _PIP.match(program):
        return _pip(argv[1:], "pip")
    reader = _READERS.get(program)
    return None if reader is None else reader(list(argv[1:]))


def _pip(words: Sequence[str], adder: str) -> InstallRequest | None:
    if not words or words[0] not in ("install", "download", "wheel"):
        return None
    scan = split_words(words[1:], _PIP_VALUES)
    names = _python_names([*scan.operands, *scan.of(frozenset({"-e", "--editable"}))])
    tool = f"{adder} {words[0]}"
    return _python(tool, adder if words[0] == "install" else None, names, scan)


def _uv(words: list[str]) -> InstallRequest | None:
    head = words[:2]
    if head[:1] == ["add"]:
        scan = split_words(words[1:], _UV_VALUES)
        return _python("uv add", "uv", _python_names(scan.operands), scan)
    if head == ["pip", "install"]:
        return _pip(words[1:], "uv pip")
    if head in (["tool", "install"], ["tool", "run"]):
        return _tool(f"uv {' '.join(head)}", words[2:], _UV_VALUES)
    if head[:1] == ["run"]:
        return _with_only("uv run", words[1:])
    return None


def _uvx(words: list[str]) -> InstallRequest | None:
    return _tool("uvx", words, _UV_VALUES)


def _pipx(words: list[str]) -> InstallRequest | None:
    if words[:1] not in (["install"], ["run"], ["inject"]):
        return None
    return _tool(f"pipx {words[0]}", words[1:], _PIPX_VALUES)


def _poetry_or_pdm(manager: str) -> _Reader:
    def read(words: list[str]) -> InstallRequest | None:
        if words[:1] != ["add"]:
            return None
        values = _POETRY_VALUES if manager == "poetry" else _COMMON_VALUES
        scan = split_words(words[1:], values)
        return _python(f"{manager} add", manager, _python_names(scan.operands), scan)

    return read


def _conda(words: list[str]) -> InstallRequest | None:
    if words[:1] not in (["install"], ["create"]):
        return None
    scan = split_words(words[1:], _CONDA_VALUES)
    names = (
        canonical_name(re.split(r"[=<>!~\s]", word.rpartition("::")[2])[0])
        for word in scan.operands
    )
    kept = tuple(dict.fromkeys(n for n in names if n and n not in _BOOTSTRAP))
    return InstallRequest(
        f"conda {words[0]}", "conda", names=kept, files=tuple(scan.of(frozenset({"--file"})))
    )


def _npm(words: list[str]) -> InstallRequest | None:
    if words[:1] in (["install"], ["i"], ["add"]):
        scan = split_words(words[1:], _NPM_VALUES)
        names = _node_names(scan.operands)
        return InstallRequest("npm install", "node", names=names) if names else None
    if words[:1] == ["exec"]:
        return _npx(words[1:])
    return None


def _npx(words: list[str]) -> InstallRequest | None:
    scan = split_words(words, _NPM_VALUES, stop_at_operand=True)
    names = _node_names([*scan.of(frozenset({"-p", "--package"})), *scan.operands[:1]])
    return InstallRequest("npx", "node", names=names) if names else None


_READERS: Final[dict[str, _Reader]] = {
    "uv": _uv,
    "uvx": _uvx,
    "pipx": _pipx,
    "poetry": _poetry_or_pdm("poetry"),
    "pdm": _poetry_or_pdm("pdm"),
    **dict.fromkeys(_CONDA, _conda),
    "npm": _npm,
    "npx": _npx,
}
#: Launchers the shell parser unwraps: the raw words after them, read like the direct form.
_RUNNERS: Final[tuple[tuple[tuple[str, ...], _Reader], ...]] = (
    (("uvx",), _uvx),
    (("uv", "run"), lambda words: _with_only("uv run", words)),
    (("pipx", "run"), lambda words: _tool("pipx run", words, _PIPX_VALUES)),
)


def _runner(segment: Segment) -> list[InstallRequest]:
    """The requests of the runner launchers the parser stripped (``uvx``, ``uv run``, ``pipx run``)."""
    raw = list(segment.raw_argv)
    found: list[InstallRequest] = []
    for prefix, reader in _RUNNERS:
        if " ".join(prefix) not in segment.wrappers:
            continue
        start = _find(raw, prefix)
        request = None if start is None else reader(raw[start + len(prefix) :])
        if request is not None:
            found.append(request)
    return found


def _find(words: list[str], prefix: tuple[str, ...]) -> int | None:
    for index in range(len(words) - len(prefix) + 1):
        window = [posixpath.basename(words[index]), *words[index + 1 : index + len(prefix)]]
        if tuple(window) == prefix:
            return index
    return None


def _tool(tool: str, words: Sequence[str], values: frozenset[str]) -> InstallRequest | None:
    """A tool install or ephemeral run: the package is ``--from``/``--spec``, else the command."""
    scan = split_words(words, values, stop_at_operand=True)
    source = scan.of(frozenset({"--from", "--spec"})) or scan.operands[:1]
    names = _python_names([*source, *scan.of(_WITH)])
    return _python(tool, None, names, scan) if names or scan.of(_FILES) else None


def _with_only(tool: str, words: Sequence[str]) -> InstallRequest | None:
    """``uv run``: an install only through ``--with`` / ``--with-requirements``."""
    scan = split_words(words, _UV_VALUES, stop_at_operand=True)
    names = _python_names(scan.of(_WITH))
    return _python(tool, None, names, scan) if names or scan.of(_FILES) else None


def _python(tool: str, adder: str | None, names: tuple[str, ...], scan: CliWords) -> InstallRequest:
    indexes: list[Index] = [("primary", value) for value in scan.of(_PRIMARY)]
    indexes.extend(("extra", _index_url(value)) for value in scan.of(_EXTRA))
    groups = {value.lower() for value in scan.of(_DEV_GROUPS)}
    return InstallRequest(
        tool,
        "python",
        adder=adder,
        names=names,
        files=tuple(scan.of(_FILES)),
        indexes=tuple(indexes),
        dev=bool(scan.flags & _DEV) or "dev" in groups,
    )


def _python_names(words: Sequence[str]) -> tuple[str, ...]:
    """The projects ``words`` name; local paths and self-installs name none.

    A direct URL without ``#egg=`` or a wheel name is named by its last path
    part (``git+https://host/org/tool.git@v1`` is ``tool``): still a request.
    """
    names: list[str] = []
    for word in words:
        if not word or _LOCAL.match(word):
            continue
        found = sorted(requirement_names(word))
        if not found and "://" in word:
            last = word.split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
            found = [canonical_name(last.partition("@")[0].removesuffix(".git"))]
        names.extend(found)
    return tuple(dict.fromkeys(n for n in names if n and n not in _BOOTSTRAP))


def _index_url(value: str) -> str:
    """uv's ``--index name=url`` form, or the bare URL."""
    name, equals, url = value.partition("=")
    return url if equals and "://" not in name else value


def _node_names(words: Sequence[str]) -> tuple[str, ...]:
    """npm package names, version suffix dropped (``@scope/x@1`` -> ``@scope/x``)."""
    names: list[str] = []
    for word in words:
        if not word or _LOCAL.match(word):
            continue
        scoped = word.startswith("@")
        name = word[1:].partition("@")[0] if scoped else word.partition("@")[0]
        names.append(("@" + name if scoped else name).lower()[:214])
    return tuple(dict.fromkeys(n for n in names if n.strip("@")))
