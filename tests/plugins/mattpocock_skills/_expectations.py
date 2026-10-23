"""Shared constants and scanners for the ``mattpocock_skills`` bundled plugin's gates.

specs/prT-mattpocock-skills.md section 7.2. Owned by T01: the per-skill lanes
(T02-T09) import from here and never edit it; a lane that needs another helper
writes it in its own test file. The id sets are the D9 targets of loads and
router labels, not an inventory pin: the gates parametrise over the skills
present (:func:`present_skill_ids`), and only T10's ``test_inventory.py`` pins
the whole set.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.validation.link_check import _CODE_SPAN_RE
from tests._catalog import plugin_root

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

PLUGIN_NAME: Final = "coding_agent_playbook.plugins.mattpocock_skills"
PLUGIN_ROOT: Final = plugin_root("mattpocock_skills")
SKILLS_ROOT: Final = PLUGIN_ROOT / "skills"
RULES_ROOT: Final = PLUGIN_ROOT / "rules"
ALLOWLIST_DIR: Final = Path(__file__).resolve().parent / "allowlist"
#: Upstream v1.3.1's MIT ``LICENSE`` ("Copyright (c) 2026 Matt Pocock"); a re-pin
#: (D5) that changes the licence fails loudly here.
LICENSE_SHA256: Final = "0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5"
#: The only plugin rule (D15, T03).
RULE_FILE_NAME: Final = "mattpocock-skills-tracker.md"
#: The plugin root's entries (G2); ``rules/`` arrives with T03.
ROOT_ENTRIES: Final = frozenset(
    {"LICENSE", "ATTRIBUTIONS.md", "README.md", "framework.toml", "skills", "rules"}
)
#: The licence files a skill's ``references/`` may hold besides markdown (D4, D6).
LICENSE_FILE_NAMES: Final = frozenset({"LICENSE", "LICENSE-show-me"})
SCRIPT_SHEBANG: Final = "#!/usr/bin/env python3"

#: The 26 final ids of D9: what loads and router labels may name.
FINAL_IDS: Final[frozenset[str]] = frozenset(
    {
        "ask-matt",
        "codebase-design",
        "diagnosing-bugs",
        "domain-modeling",
        "grill-me",
        "grill-with-docs",
        "grilling",
        "handoff",
        "implement",
        "implement-spec",
        "improve-codebase-architecture",
        "pr-body",
        "research",
        "retro",
        "setup-matt-pocock-skills",
        "tdd",
        "teach",
        "throwaway-prototype",
        "to-questionnaire",
        "to-spec",
        "to-tickets",
        "two-axis-review",
        "wait-what",
        "wayfinder",
        "wizard",
        "writing-for-agents",
    }
)
#: The 15 skills upstream marks ``disable-model-invocation: true`` (D19).
USER_INVOKED_IDS: Final[frozenset[str]] = frozenset(
    {
        "ask-matt",
        "grill-me",
        "grill-with-docs",
        "handoff",
        "implement",
        "implement-spec",
        "improve-codebase-architecture",
        "retro",
        "setup-matt-pocock-skills",
        "teach",
        "to-questionnaire",
        "to-spec",
        "to-tickets",
        "wait-what",
        "wayfinder",
    }
)
#: The D19 soft guard: the first non-blank body line of every user-invoked skill.
GUARD_LINE: Final = "Run this only when the user asked for it by name; otherwise stop."


def _tickets(**ids_by_ticket: str) -> dict[str, str]:
    return {i: ticket for ticket, ids in ids_by_ticket.items() for i in ids.split()}


#: Final id -> the ticket that fills its ``ATTRIBUTIONS.md`` section (section 5.3).
TICKET_OF: Final[Mapping[str, str]] = _tickets(
    T01="to-questionnaire wait-what",
    T02="domain-modeling grill-me grill-with-docs grilling",
    T03="setup-matt-pocock-skills to-spec to-tickets",
    T04="implement implement-spec wayfinder",
    T05="pr-body tdd two-axis-review",
    T06="codebase-design improve-codebase-architecture throwaway-prototype",
    T07="diagnosing-bugs wizard",
    T08="handoff research retro teach writing-for-agents",
    T09="ask-matt",
)
#: The 16 global ``##`` headings of ``ATTRIBUTIONS.md``, in order (section 5.3).
ATTRIBUTIONS_GLOBAL_SECTIONS: Final[tuple[str, ...]] = (
    "Provenance",
    "License copies",
    "Restructure",
    "Frontmatter",
    "Renames",
    "Cross-skill references",
    "No external URLs",
    "Imposed tools removed",
    "Harness built-ins reworded",
    "Script ports",
    "Plugin always rule",
    "Dropped and why",
    "Third-party content",
    "Consumer-repo conventions",
    "Rendering per adapter",
    "Gates",
)
PER_SKILL_HEADING: Final = "Per-skill changes"


def placeholder(skill_id: str) -> str:
    """The line a lane replaces in its skill's section: ``placeholder("tdd") == "_Filled by T05._"``."""
    return f"_Filled by {TICKET_OF[skill_id]}._"


#: G14: an operative load. Every load-target test, here and in the lanes, uses it.
LOAD_RE: Final = re.compile(r"[Ll]oad(?:s|ing)? the `([a-z0-9]+(?:-[a-z0-9]+)*)` skill")
#: G4: imposed tools named anywhere (section 7.2), case-insensitively.
_IMPOSED_NAMES: Final = (
    "gh glab jq tput curl wget xdg-open wslview explorer.exe shellcheck npx npm yarn deno puppeteer"
)
IMPOSED_TOOL_RE: Final = re.compile(
    r"(?i)(?<![\w.-])(?:"
    + "|".join(re.escape(name) for name in _IMPOSED_NAMES.split())
    + r")(?![\w-])|jsdelivr|unpkg|cdnjs|via CDN"
)
#: G4 and the D2 amendment (prF F6): ``playbook forge``, the engine's one forge
#: command (ADR 0003), is allowed where G4 bans ``gh`` and ``glab``, but only in
#: these files (paths relative to ``skills/``): setup and its Forge issues seed.
FORGE_COMMAND: Final = "playbook forge"
FORGE_COMMAND_FILES: Final = frozenset(
    {
        "setup-matt-pocock-skills/SKILL.md",
        "setup-matt-pocock-skills/references/issue-tracker-forge.md",
    }
)
#: G5: words legal in prose and denied only in command position (section 7.3).
AMBIGUOUS_WORDS: Final = frozenset({"open", "start", "bash", "sh", "node", "bun", "pnpm"})
#: G7: Claude Code-only names (D17).
CLAUDE_ONLY_RE: Final = re.compile(
    r"Skill tool|Task tool|AskUserQuestion|TodoWrite|(?<![\w/])/(?:clear|compact)\b"
)
#: G8: text that only works with an upstream plugin install (D2).
COUPLING_RE: Final = re.compile(
    r"CLAUDE_PLUGIN_ROOT|\.claude-plugin|claude plugin install|/plugin install"
    r"|npx skills|skills\.sh|mattpocock-skills:"
)
_SEPARATOR_RE: Final = re.compile(r"&&|\|\||;|\||\$\(")
_ENV_ASSIGNMENT_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PROMPT_WORDS: Final = frozenset({"$", ">", "%"})
_SUBPROCESS_CALLS: Final = frozenset({"run", "call", "check_call", "check_output", "Popen"})


@dataclass(frozen=True)
class Hit:
    """One scanner match: ``path`` relative to its skill directory (or the plugin root
    for a rule), 1-based ``line``, the matched ``text``, its column ``span`` and the line."""

    path: str
    line: int
    text: str
    span: tuple[int, int]
    line_text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.text!r} in {self.line_text.strip()!r}"


@dataclass(frozen=True)
class AllowEntry:
    """One allowlist line (section 7.4): ``<path>: <exact excerpt of one line>``."""

    path: str
    excerpt: str
    source: str

    def covers(self, hit: Hit) -> bool:
        """True when ``hit`` sits inside an occurrence of the excerpt on its line."""
        if hit.path != self.path:
            return False
        start = hit.line_text.find(self.excerpt)
        while start != -1:
            if start <= hit.span[0] and hit.span[1] <= start + len(self.excerpt):
                return True
            start = hit.line_text.find(self.excerpt, start + 1)
        return False


def present_skill_ids() -> list[str]:
    """The skill directories under ``skills/``, sorted (empty before the plugin exists)."""
    if not SKILLS_ROOT.is_dir():
        return []
    return sorted(p.name for p in SKILLS_ROOT.iterdir() if p.is_dir())


def _is_bytecode_cache(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def plugin_files() -> list[Path]:
    """Every file of the plugin, root files included, bytecode caches excluded, sorted."""
    if not PLUGIN_ROOT.is_dir():
        return []
    paths = (p for p in PLUGIN_ROOT.rglob("*") if p.is_file())
    return sorted(p for p in paths if not _is_bytecode_cache(p.relative_to(PLUGIN_ROOT)))


def skill_files(skill_id: str) -> list[Path]:
    """Every file of one skill directory, bytecode caches excluded, sorted."""
    return [p for p in plugin_files() if (SKILLS_ROOT / skill_id) in p.parents]


def rule_files() -> list[Path]:
    """Every file under ``rules/`` (none before T03)."""
    return [p for p in plugin_files() if RULES_ROOT in p.parents]


def skill_docs(skill_id: str) -> list[Path]:
    """``SKILL.md`` plus ``references/**/*.md`` of one skill, sorted."""
    skill_dir = SKILLS_ROOT / skill_id
    references = sorted((skill_dir / "references").rglob("*.md"))
    return [skill_dir / "SKILL.md", *(p for p in references if p.is_file())]


def scripts_of(skill_id: str) -> list[Path]:
    """The files under one skill's ``scripts/``."""
    return [p for p in skill_files(skill_id) if (SKILLS_ROOT / skill_id / "scripts") in p.parents]


#: The engine-owned role tag (prU D77, L0-19): one ``capabilities: [<role>]`` line as
#: the last frontmatter key of seven skills, listed in ATTRIBUTIONS. The upstream
#: fidelity pins compare the vendored text without it.
_CAPABILITIES_LINE_RE: Final = re.compile(r"^capabilities: \[[a-z_, ]+\]\n", re.MULTILINE)


def vendored_text(skill_id: str, relative: str = "SKILL.md") -> str:
    """The shipped text of one skill file, minus the engine's ``capabilities`` tag line.

    Read as bytes, so a newline change still shows. Example::

        vendored_text("tdd").split("\\n")[:5]  # upstream frontmatter plus the id line
    """
    text = (SKILLS_ROOT / skill_id / relative).read_bytes().decode("utf-8")
    if relative != "SKILL.md":
        return text
    return _CAPABILITIES_LINE_RE.sub("", text, count=1)


def split_skill(skill_id: str) -> tuple[dict[str, object], str]:
    """The source ``SKILL.md`` of ``skill_id`` as (frontmatter, body), without the role tag."""
    return split_frontmatter(vendored_text(skill_id))


def hit_path(path: Path) -> str:
    """``path`` relative to its skill directory, or to the plugin root outside ``skills/``."""
    relative = path.relative_to(PLUGIN_ROOT)
    if relative.parts[0] == "skills" and len(relative.parts) > 2:
        return Path(*relative.parts[2:]).as_posix()
    return relative.as_posix()


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def regex_hits(path: Path, pattern: re.Pattern[str]) -> list[Hit]:
    """Every match of ``pattern`` in ``path``, line by line."""
    rel = hit_path(path)
    return [
        Hit(rel, number, m.group(0), m.span(), line)
        for number, line in enumerate(_read_lines(path), 1)
        for m in pattern.finditer(line)
    ]


def imposed_tool_hits(path: Path) -> list[Hit]:
    """G4: unambiguous imposed-tool names, CDN hosts and "via CDN" anywhere in ``path``."""
    return regex_hits(path, IMPOSED_TOOL_RE)


def forge_command_spans(path: Path) -> list[tuple[int, str]]:
    """``(line, text)`` of every code span of ``path`` that starts with ``playbook forge``."""
    text = path.read_text(encoding="utf-8")
    return [
        (text.count("\n", 0, match.start(2)) + 1, match.group(2))
        for match in _CODE_SPAN_RE.finditer(text)
        if match.group(2).startswith(FORGE_COMMAND + " ")
    ]


def command_position_hits(path: Path) -> list[Hit]:
    """G5: ambiguous words (and, in a script, any imposed tool) in command position."""
    if path.suffix == ".py":
        return _script_command_hits(path)
    lines = _read_lines(path)
    hits = {(h.line, h.span): h for h in _markdown_command_hits(hit_path(path), lines)}
    return [hits[key] for key in sorted(hits)]


def _markdown_segments(lines: list[str]) -> Iterator[tuple[int, int, str]]:
    """``(line index, column, text)`` of every command segment (section 7.3 steps 1-2)."""
    prose = list(lines)
    fence = ""
    for index, line in enumerate(lines):
        head = line.lstrip()
        if not fence and head.startswith(("```", "~~~")):
            fence, prose[index] = head[:3], ""
        elif fence:
            prose[index] = ""
            if head.startswith(fence):
                fence = ""
            else:
                yield index, 0, line
        elif head.startswith("$ "):
            column = len(line) - len(head) + 2
            yield index, column, line[column:]
    offsets = [0]
    for line in prose:
        offsets.append(offsets[-1] + len(line) + 1)
    for match in _CODE_SPAN_RE.finditer("\n".join(prose)):
        for piece_offset, piece in _split_lines(match.group(2), match.start(2)):
            index = max(i for i, start in enumerate(offsets) if start <= piece_offset)
            yield index, piece_offset - offsets[index], piece


def _split_lines(text: str, offset: int) -> Iterator[tuple[int, str]]:
    for piece in text.split("\n"):
        yield offset, piece
        offset += len(piece) + 1


def _command_words(segment: str) -> Iterator[tuple[int, str]]:
    """``(column, word)`` of the word in command position of each piece (steps 3-4)."""
    starts = [0, *(m.end() for m in _SEPARATOR_RE.finditer(segment))]
    ends = [m.start() for m in _SEPARATOR_RE.finditer(segment)] + [len(segment)]
    for start, end in zip(starts, ends, strict=True):
        words = [(m.start() + start, m.group(0)) for m in re.finditer(r"\S+", segment[start:end])]
        if words and words[0][1] in _PROMPT_WORDS:
            words = words[1:]
        while words and _ENV_ASSIGNMENT_RE.match(words[0][1]):
            words = words[1:]
        if words:
            yield words[0]


def _markdown_command_hits(rel: str, lines: list[str]) -> Iterator[Hit]:
    for index, column, segment in _markdown_segments(lines):
        for word_column, word in _command_words(segment):
            if word in AMBIGUOUS_WORDS:
                start = column + word_column
                yield Hit(rel, index + 1, word, (start, start + len(word)), lines[index])


def _is_denied_command(word: str) -> bool:
    name = os.path.basename(word)
    return name in AMBIGUOUS_WORDS or IMPOSED_TOOL_RE.fullmatch(name) is not None


def _call_name(node: ast.Call) -> tuple[str, str]:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id, func.attr
    return "", func.id if isinstance(func, ast.Name) else ""


def _command_argument(node: ast.Call) -> ast.expr | None:
    keyword = next((k.value for k in node.keywords if k.arg == "args"), None)
    return node.args[0] if node.args else keyword


def _command_word(node: ast.Call) -> str | None:
    """The command word a ``subprocess``/``os`` call would run, if it is a literal."""
    module, name = _call_name(node)
    shell = any(k.arg == "shell" and getattr(k.value, "value", False) for k in node.keywords)
    is_subprocess = module in {"subprocess", ""} and name in _SUBPROCESS_CALLS
    is_os_string = module == "os" and name in {"system", "popen"}
    if module == "os" and name.startswith("exec"):
        # os.exec* takes the program as a string, never a list; the basename is checked.
        return _string_constant(node.args[0]) if node.args else None
    if not (is_subprocess or is_os_string):
        return None
    argument = _command_argument(node)
    if isinstance(argument, ast.List | ast.Tuple) and argument.elts:
        return _string_constant(argument.elts[0])
    text = _string_constant(argument)
    if text is not None and (is_os_string or shell):
        return (text.split() or [""])[0]
    return None


def _string_constant(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _script_command_hits(path: Path) -> list[Hit]:
    lines = _read_lines(path)
    hits: list[Hit] = []
    for node in ast.walk(ast.parse("\n".join(lines), filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        word = _command_word(node)
        if word and _is_denied_command(word):
            span = (node.col_offset, node.end_col_offset or node.col_offset)
            hits.append(Hit(hit_path(path), node.lineno, word, span, lines[node.lineno - 1]))
    return hits


def load_allowlist(skill_id: str) -> list[AllowEntry]:
    """Parse ``allowlist/<skill_id>.txt``; a malformed line raises with its location."""
    source = ALLOWLIST_DIR / f"{skill_id}.txt"
    entries: list[AllowEntry] = []
    for number, raw in enumerate(source.read_text(encoding="utf-8").split("\n"), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        path, separator, excerpt = line.partition(": ")
        if not separator or not path or not excerpt:
            raise ValueError(
                f"{source.name}:{number}: {raw!r} is not '<path relative to skills/{skill_id}/>: "
                "<exact excerpt of one line>'"
            )
        entries.append(AllowEntry(path, excerpt, f"{source.name}:{number}"))
    return entries
