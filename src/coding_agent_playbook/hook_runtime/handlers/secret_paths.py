"""secrets-path-guard: deny agent reads and writes of credential paths (specs/prK-hook-pack.md §E.4).

Default, ``pre_tool_use``, path-only: a file is never opened to classify it
(SPEC §17.3). The policy is ``guard_config``'s (``_secret_policy.path_policy``),
extended by ``extra_globs`` and relaxed by ``allow_paths`` (both also from
``[guardrails.secrets]``):

- **Structured tools** (a boundary): the path of Read, Edit, Write,
  NotebookEdit and ``apply_patch``; a Grep/Glob search path, and the file glob
  of a Glob ``pattern`` or a Grep ``glob`` (a repo-wide Grep is not denied:
  ripgrep honors ``.gitignore`` and the native ``Read(...)`` rows cover the
  rest); and an ``mcp__*`` tool's ``path``, ``file_path``, ``uri``,
  ``filename`` or ``paths[]`` argument.
- **Bash** (a speed bump): every argv token and redirect target of every
  segment, whatever argv0 is, including ``REV:<path>`` (``git show``),
  ``--opt=<path>`` and ``@<path>`` forms; ``bash -c`` scripts are their own
  segments. A read token counts when it names an existing file (only a git
  command's may name history), so prose and search terms pass. A command the
  parser could not follow is judged on its split words.
- ``deny`` with a two-line reason naming ``.env.example``; ``ask`` instead for a
  write that would *create* a dotenv file and for a hard link whose inode is a
  secret file's (``_secret_inodes``). Bare ``env`` / ``printenv`` get one
  context line per session.

``on_error: ask``. The Claude adapter also renders the native ``Read(...)`` /
``Edit(...)`` deny rows that survive a missing interpreter (``_secret_native``).
"""

from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.handlers._secret_inodes import (
    InodeIndex,
    build_inode_index,
    inode_of,
    is_secret_inode,
)
from coding_agent_playbook.hook_runtime.handlers._secret_policy import (
    classify_path,
    path_policy,
    spelled,
)
from coding_agent_playbook.hook_runtime.handlers._targets import shell_target
from coding_agent_playbook.hook_runtime.paths import fold_key, normalize_path
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.security.files import user_home

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell import Segment
    from coding_agent_playbook.security.paths import PathPolicy

__all__ = ["ADVICE", "CONFIG_SCHEMA", "ENV_CONTEXT", "secret_path_guard"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "extra_globs": ConfigKey("list", "extend"),
    "allow_paths": ConfigKey("list", "relax"),
}
ADVICE: Final = (
    "Use .env.example for variable NAMES; ask the user to supply values; "
    "read them from the environment at runtime."
)
ENV_CONTEXT: Final = (
    "The environment can hold credentials: print only the variable you need, by name, "
    "and never echo a secret value."
)
_MCP_PATH_KEYS: Final = ("path", "file_path", "uri", "filename")
_FILE_URI: Final = "file://"
#: The file-glob argument of each search tool (Grep's ``pattern`` is a content regex).
_SEARCH_GLOB_KEYS: Final[Mapping[str, str]] = {"Glob": "pattern", "Grep": "glob"}
_ENV_PRINTERS: Final = frozenset({("env",), ("printenv",)})
_GIT_ARGV0: Final = (("git",), ("git.exe",))
_SPACE: Final = re.compile(r"\s")
_DOTENV: Final = ".env*"
_WRITE_REDIRECTS: Final = frozenset({">", ">>", ">|", "&>", "&>>", "<>"})
_HOME_VAR: Final = re.compile(r"^(?:\$HOME|\$\{HOME\})(?=/|$)")
#: What a degraded (regex-split) word may carry around a path: quotes, redirections.
_DEGRADED_NOISE: Final = re.compile(r"^\d*[<>]+[&|]?|^['\"]|['\"]$")

type Verdict = Literal["deny", "ask"]


@dataclass(frozen=True, slots=True)
class _Hit:
    """One judged path: the verdict, the name the agent used, and why."""

    verdict: Verdict
    shown: str
    rule: str


@register_hook_handler(
    "secret_path_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "context", "none"],
    config_schema=CONFIG_SCHEMA,
    config_domain="secrets",
)
def secret_path_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny a credential path; ask for a new dotenv file or a secret's hard link.

    Example::

        >>> secret_path_guard(read_of(".env"), ctx).reason.splitlines()[0]  # doctest: +SKIP
        'Blocked: ".env" holds credentials.'
    """
    tool = ev.tool
    if tool is None:
        return None
    judge = _Judge(ev, ctx, path_policy(ctx.cfg, ctx.config))
    hits = judge.shell(tool) if tool.tool_class is ToolClass.SHELL else judge.files(tool)
    return _result(hits, ctx) or _env_context(tool, ctx)


@dataclass(frozen=True, slots=True)
class _Judge:
    """The policy applied to one event's paths."""

    ev: CanonicalEvent
    ctx: HandlerContext
    policy: PathPolicy

    @property
    def home(self) -> str:
        return self.ctx.home or user_home()

    def files(self, tool: ToolCall) -> list[_Hit]:
        """The structured tool's paths, MCP path arguments and search globs."""
        writes = set(tool.write_paths)
        paths = [*tool.paths, *(self._normalize(raw) for raw in _mcp_paths(tool))]
        hits = [self.path_hit(p, writing=p in writes) for p in paths]
        hits.append(self._search_glob(tool))
        return [hit for hit in hits if hit is not None]

    def shell(self, tool: ToolCall) -> list[_Hit]:
        """Every token and redirect target of every segment of the command."""
        command = tool.command
        if command is None:
            return []
        degraded = command.parse_error is not None
        hits = (self._segment_hits(segment, degraded=degraded) for segment in command.segments)
        return [hit for found in hits for hit in found]

    def _segment_hits(self, segment: Segment, *, degraded: bool) -> list[_Hit]:
        """One segment's judged paths.

        A read can leak only an existing file, so a read token must name one:
        ``grep -r id_rsa .`` or ``echo .env`` passes when no such file is
        there. A write target may be new, and a git command's paths name
        history (``git show HEAD:.env`` of a since-deleted file).
        """
        history = segment.argv[:1] in _GIT_ARGV0
        hits: list[_Hit | None] = []
        for raw, writing in _segment_paths(segment, degraded=degraded):
            path = shell_target(raw, segment, self.ev, self.ctx)
            if writing or history or path.exists:
                hits.append(self.path_hit(path, writing=writing))
        return [hit for hit in hits if hit is not None]

    def path_hit(self, path: NormalizedPath, *, writing: bool) -> _Hit | None:
        """The verdict on one normalized path, or ``None`` when it is not a secret."""
        verdict = classify_path(self.policy, path, home=self.home, platform=self.ctx.platform)
        shown = spelled(path)
        if verdict == "unknown":
            return _Hit("ask", shown, "hard_link") if self._secret_inode(path) else None
        if verdict is None:
            return None
        if writing and not path.exists and self._dotenv(path):
            return _Hit("ask", shown, "new_dotenv")
        return _Hit(verdict, shown, "secret_path")

    def _search_glob(self, tool: ToolCall) -> _Hit | None:
        """A Glob ``pattern`` / Grep ``glob`` that names secret files is a request for them."""
        key = _SEARCH_GLOB_KEYS.get(tool.name)
        pattern = None if key is None else tool.raw_input.get(key)
        if not isinstance(pattern, str) or not pattern:
            return None
        if not self.policy.matches(pattern, home=self.home, platform=self.ctx.platform):
            return None
        return _Hit("deny", pattern, "secret_glob")

    def _secret_inode(self, path: NormalizedPath) -> bool:
        inode = inode_of(path.realpath)
        repo = self.ev.repo
        if inode is None or repo is None:
            return False
        ctx = self.ctx

        def build() -> InodeIndex:
            return build_inode_index(
                repo.worktree_root,
                self.policy,
                home=self.home,
                platform=ctx.platform,
                clock=ctx.clock,
            )

        return is_secret_inode(inode, ctx.session.store, self.ev.session_id, build, clock=ctx.clock)

    def _dotenv(self, path: NormalizedPath) -> bool:
        name = fold_key(posixpath.basename(path.path), self.ctx.platform)
        return fnmatch.fnmatchcase(name, _DOTENV)

    def _normalize(self, raw: str) -> NormalizedPath:
        ev, ctx = self.ev, self.ctx
        return normalize_path(raw, base=ev.cwd, repo=ev.repo, home=ctx.home, platform=ctx.platform)


def _segment_paths(segment: Segment, *, degraded: bool) -> Iterator[tuple[str, bool]]:
    """``(raw path, written)`` for each argv token form and redirect target of ``segment``."""
    from coding_agent_playbook.hook_runtime.shell import write_targets

    written = set(write_targets(segment))
    # A plain argv0 is a command name; one with a "/" (or a degraded word) may be a path.
    head = segment.argv[:1]
    argv = segment.argv if degraded or any("/" in word for word in head) else segment.argv[1:]
    for token in argv:
        word = _DEGRADED_NOISE.sub("", token) if degraded else token
        for raw in _token_forms(word):
            yield raw, raw in written
    for redirect in segment.redirects:
        if redirect.target is not None and not redirect.target.isdigit():
            yield redirect.target, redirect.op in _WRITE_REDIRECTS


def _token_forms(token: str) -> list[str]:
    """The path spellings one argv token may hold: itself, ``@x``, ``--o=x``, ``REV:x``.

    Example::

        >>> _token_forms("HEAD:.env"), _token_forms("--env-file=.env")
        (['HEAD:.env', '.env'], ['.env'])
    """
    token = _HOME_VAR.sub("~", token)
    forms = [token]
    if token.startswith("@"):
        forms.append(token[1:])
    option, equals, value = token.partition("=")
    if equals and option.startswith("-"):
        forms.append(value)
    rev, colon, rest = token.partition(":")
    if colon and rest and "/" not in rev and not rest.startswith("//"):
        forms.append(rest)
    # Prose is no path: a commit message (".env loading fix") has a space in its last part.
    return [
        form
        for form in dict.fromkeys(forms)
        if form and not form.startswith("-") and not _SPACE.search(posixpath.basename(form))
    ]


def _mcp_paths(tool: ToolCall) -> list[str]:
    """The path-like arguments of an MCP tool call (a heuristic: §E.4, degraded on OpenCode)."""
    if tool.tool_class is not ToolClass.MCP:
        return []
    raw = tool.raw_input
    values = [raw.get(key) for key in _MCP_PATH_KEYS]
    listed = raw.get("paths")
    values.extend(listed if isinstance(listed, list) else ())
    found = [value for value in values if isinstance(value, str) and value]
    return [value[len(_FILE_URI) :] if value.startswith(_FILE_URI) else value for value in found]


def _result(hits: list[_Hit], ctx: HandlerContext) -> HandlerResult | None:
    denied = [hit for hit in hits if hit.verdict == "deny"]
    if denied:
        reason = f"Blocked: {quote_data(denied[0].shown)} holds credentials.\n{ADVICE}"
        return HandlerResult(
            decision=Decision.DENY, hook_id=ctx.hook.id, rule_id=denied[0].rule, reason=reason
        )
    if not hits:
        return None
    first = hits[0]
    return HandlerResult(
        decision=Decision.ASK, hook_id=ctx.hook.id, rule_id=first.rule, reason=_ask_reason(first)
    )


def _ask_reason(hit: _Hit) -> str:
    shown = quote_data(hit.shown)
    if hit.rule == "new_dotenv":
        return (
            f"{shown} would be a new credentials file.\n"
            "Confirm with the user; commit only an .env.example with variable NAMES."
        )
    return f"{shown} is a hard link to a credentials file.\n{ADVICE}"


def _env_context(tool: ToolCall, ctx: HandlerContext) -> HandlerResult | None:
    command = tool.command if tool.tool_class is ToolClass.SHELL else None
    if command is None or not any(s.argv in _ENV_PRINTERS for s in command.segments):
        return None
    if not ctx.session.once("secrets:env"):
        return None
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=ctx.hook.id, rule_id="env_dump", context=(ENV_CONTEXT,)
    )
