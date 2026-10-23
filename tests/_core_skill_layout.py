"""The catalog gates of one core skill: what it may hold, where its links lead, its SKILL.md (prU L0-13).

A core skill ships ``SKILL.md`` and may ship ``rules/`` (its member rules,
D5), ``references/`` (long-form documents and the license copies, D19, D25,
D26), ``scripts/`` (the stdlib scripts from python_design, D2) and
``examples/`` (a runnable example app, D48). Each gate takes the skill's
directory and returns one problem string per violation, naming the
skill-relative path, so ``tests/integration/test_core_skills.py`` runs them over
the real catalog, one test per gate, and ``tests/integration/test_core_skill_layout.py``
proves them on scratch skills, all at once through :func:`every_gate_problems`.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.skills.naming import agent_skill_issues
from coding_agent_playbook.validation._sections import check_skill_sections
from coding_agent_playbook.validation._skills import check_rule_skills
from coding_agent_playbook.validation.link_check import classify_link, extract_markdown_links
from tests._budget_probe import every_gate_facts

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

#: Whether a file may sit in one side directory.
type _FileTest = Callable[[Path], bool]

#: The directories a core skill may hold beside its one file, ``SKILL.md``.
SKILL_DIRS: Final = ("examples", "references", "rules", "scripts")
#: The byte-identical upstream license copies a core skill's references/ may hold (D19, D64).
LICENSE_COPY_NAMES: Final = frozenset(
    {
        "LICENSE.python-best-practices",
        "LICENSE.python-clean-architecture",
        "LICENSE.simple-agent-api",
    }
)
#: A third-person description check (no "I", "you" or "we"), extended with "use" (a "Use when" opener).
NOT_THIRD_PERSON: Final = re.compile(r"(?i)(i|you|we|use)\b")
#: A URL in a SKILL.md: a scheme or a bare ``www.``.
URL: Final = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://|\bwww\.")
#: A line opening or closing a fenced code block: its backtick or tilde run.
_FENCE: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})")
#: D49: the line cap of an internal (engine-written) reference.
INTERNAL_REFERENCE_MAX_LINES: Final = 120
#: A path segment after ``references/`` that is itself a directory: real nesting (D78(16)).
_NESTED_REFERENCE: Final = re.compile(r"references/[^\s/()\[\]`'\"<>]+/")
_RULE_SUFFIXES: Final = (".md.j2", ".md")


def every_gate_problems(skill_dir: Path) -> list[str]:
    """Every catalog gate's problems for the repo-local skill at ``repo/playbook/skills/<id>``.

    The directory gates (inventory, links, nesting), the SKILL.md gates
    (description shape, plain markdown, the Agent Skills standard) and the
    skill checks of ``playbook validate`` (the ``playbook:`` block, the
    ``playbook.references`` list covering every references/ and examples/ file,
    D47), each validate finding as ``"validate: <path>: <message>"``.

    Example: ``every_gate_problems(repo / "playbook" / "skills" / "demo")`` -> ``[]``.
    """
    return [
        *inventory_problems(skill_dir),
        *link_problems(skill_dir),
        *nesting_problems(skill_dir),
        *description_problems(skill_dir),
        *plain_markdown_problems(skill_dir),
        *_validate_problems(skill_dir),
    ]


def inventory_problems(skill_dir: Path) -> list[str]:
    """What ``skill_dir`` holds beyond ``SKILL.md``, :data:`SKILL_DIRS` and their allowed files.

    ``rules/`` holds only ``<id>.md`` and ``<id>.md.j2`` files whose stem is the
    rule's frontmatter ``id``, ``references/`` only ``.md`` files and the two
    license copies, one level deep, and ``scripts/`` only ``.py`` files;
    ``examples/`` holds an app laid out as it needs.

    Example: a skill holding ``references/data.json`` ->
    ``["references/data.json: references/ holds only .md files and the license copies"]``.
    """
    allowed = f"SKILL.md and the directories {', '.join(SKILL_DIRS)}"
    problems = [
        f"{entry.name}: a core skill holds only {allowed}"
        for entry in sorted(skill_dir.iterdir())
        if not _is_skill_entry(entry)
    ]
    problems += _flat_dir_problems(
        skill_dir, "rules", _is_rule_file, "<id>.md or <id>.md.j2 files named by their id"
    )
    problems += _flat_dir_problems(
        skill_dir, "references", _is_reference_file, ".md files and the license copies"
    )
    problems += _flat_dir_problems(skill_dir, "scripts", _is_script_file, ".py files")
    return problems


def link_problems(skill_dir: Path) -> list[str]:
    """Every markdown link in ``SKILL.md`` or a rule that leaves the skill or dangles.

    ``SKILL.md`` may link only its own ``references/<file>.md``; a rule may link
    any existing file inside the same skill directory (``../references/x.md``).
    Each problem names the linking file, its line and the link target.

    Example: a rule linking ``../../other/references/z.md`` ->
    ``["rules/r.md:6: link '../../other/references/z.md': target ... escapes ..."]``.
    """
    problems: list[str] = []
    for path in _linking_files(skill_dir):
        relative = path.relative_to(skill_dir).as_posix()
        for link in extract_markdown_links(path.read_text(encoding="utf-8")):
            reason = classify_link(
                link.target, base_dir=path.parent, root_dir=skill_dir, allowed_domains=()
            )
            if reason is None and path.name == "SKILL.md":
                reason = _skill_md_link_reason(link.target)
            if reason is not None:
                problems.append(f"{relative}:{link.line}: link {link.target!r}: {reason}")
    return problems


def nesting_problems(skill_dir: Path) -> list[str]:
    """Each ``SKILL.md``, rule or reference line naming a directory under ``references/``.

    References stay one level deep; the bare ``references/`` of a drawn skill
    tree is not nesting (D78(16)). Each problem names the file, line and match.

    Example: a rule saying ``references/deep/guide.md`` ->
    ``["rules/r.md:6: names 'references/deep/' (references are one level deep)"]``.
    """
    texts = [*_linking_files(skill_dir), *_files(skill_dir / "references", "*.md")]
    problems: list[str] = []
    for path in texts:
        relative = path.relative_to(skill_dir).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            problems += [
                f"{relative}:{number}: names {match!r} (references are one level deep)"
                for match in _NESTED_REFERENCE.findall(line)
            ]
    return problems


def internal_reference_problems(skill_dir: Path, paths: Iterable[str]) -> list[str]:
    """The D49 shape of each internal reference at ``paths`` (skill-relative).

    An internal reference is an engine-written decision guide: it opens with a
    ``# `` title, holds at most :data:`INTERNAL_REFERENCE_MAX_LINES` lines and
    names rule ids and files in plain text, so it has no markdown link and no URL.
    Which references are internal is the caller's input (ATTRIBUTIONS' engine-written
    list); vendored references keep their upstream shape.

    Example: a guide linking ``../rules/r.md`` ->
    ``["references/guide.md:3: link '../rules/r.md': name rule ids and files in plain text"]``.
    """
    problems: list[str] = []
    for relative in paths:
        text = (skill_dir / relative).read_text(encoding="utf-8")
        if not text.startswith("# "):
            problems.append(f"{relative}: an internal reference opens with a '# ' title")
        if (count := len(text.splitlines())) > INTERNAL_REFERENCE_MAX_LINES:
            problems.append(
                f"{relative}: {count} lines, over D49's {INTERNAL_REFERENCE_MAX_LINES} lines"
            )
        problems += [
            f"{relative}:{link.line}: link {link.target!r}: name rule ids and files in plain text"
            for link in extract_markdown_links(text)
        ]
        if URL.search(text):
            problems.append(f"{relative}: holds a URL")
    return problems


def names_rule_id(text: str, rule_id: str) -> bool:
    """Whether ``text`` names ``rule_id`` as a whole id, not inside a longer hyphenated one.

    Example: ``names_rule_id("see demo-rule-x", "demo-rule")`` -> ``False``.
    """
    return re.search(rf"(?<![\w-]){re.escape(rule_id)}(?![\w-])", text) is not None


def prose_lines(body: str) -> Iterator[tuple[int, str]]:
    """``(line number, line)`` for each line of ``body`` outside fenced code blocks.

    The rule-id check reads prose only: a code example's ``@pytest.fixture`` is a
    Python module, not a pointer to the ``pytest`` rule (C-python-testing-refs).

    Example: ``list(prose_lines("a\\n```\\nb\\n```\\nc"))`` -> ``[(1, "a"), (5, "c")]``.
    """
    fence = ""
    for number, line in enumerate(body.splitlines(), start=1):
        opener = _FENCE.match(line)
        if opener and (not fence or opener.group(1).startswith(fence)):
            fence = "" if fence else opener.group(1)
            continue
        if not fence:
            yield number, line


def description_problems(skill_dir: Path) -> list[str]:
    """The D13 identity and description shape of a skill with a ``playbook:`` block.

    ``id`` and ``name`` are the directory name; the description is one
    third-person sentence ending in "." without "Use when" (the engine adds
    ``playbook.use_when``), which is a non-empty phrase not opening with "Use when".

    Example: a description ``"Use when testing."`` -> one problem naming it.
    """
    frontmatter, _ = split_frontmatter(_skill_md(skill_dir).read_text(encoding="utf-8"))
    skill_id = skill_dir.name
    problems: list[str] = []
    identity = (frontmatter.get("id"), frontmatter.get("name"))
    if identity != (skill_id, skill_id):
        problems.append(f"SKILL.md: (id, name) is {identity}, expected the directory name")
    description = str(frontmatter.get("description"))
    shaped = not NOT_THIRD_PERSON.match(description) and description.endswith(".")
    if not shaped or "use when" in description.lower():
        problems.append(
            f"SKILL.md: description {description!r} must be one third-person capability "
            "sentence without 'Use when' (the engine adds playbook.use_when)"
        )
    block = frontmatter.get("playbook")
    use_when = block.get("use_when") if isinstance(block, dict) else None
    if not isinstance(use_when, str) or not use_when.strip():
        problems.append("SKILL.md: needs a playbook: block with a non-empty playbook.use_when")
    elif use_when.lower().startswith("use when"):
        problems.append(f"SKILL.md: playbook.use_when {use_when!r} must not open with 'Use when'")
    return problems


def plain_markdown_problems(skill_dir: Path) -> list[str]:
    """The D13 body hygiene of ``SKILL.md``: no Jinja and no URL.

    Links are :func:`link_problems`' job; rule ids in the body need the catalog's
    rule set, so ``test_core_skills.py`` checks them itself.

    Example: a SKILL.md saying ``{{ project_name }}`` -> ``["SKILL.md: contains Jinja"]``.
    """
    text = _skill_md(skill_dir).read_text(encoding="utf-8")
    problems = ["SKILL.md: contains Jinja"] if "{{" in text or "{%" in text else []
    return problems + (["SKILL.md: contains a URL"] if URL.search(text) else [])


def _validate_problems(skill_dir: Path) -> list[str]:
    """The Agent Skills standard and ``playbook validate``'s skill checks over the skill.

    The skill sits at ``repo/playbook/skills/<id>``; it and its member rules load through the engine's artifact source, as
    sync loads them; the ``applies_if`` predicates are evaluated against
    :func:`~tests._budget_probe.every_gate_facts`.
    """
    source = FileSystemArtifactSource(repo_root=skill_dir.parents[2])
    [skill] = [s for s in source.list_skills() if s.source_dir == skill_dir]
    rules = [r for r in source.list_rules() if r.frontmatter.skill == skill_dir.name]
    facts = every_gate_facts()
    members = check_rule_skills(rules, [skill])
    sections = check_skill_sections(
        rules, [skill], check_predicate=lambda predicate: evaluate_predicate(predicate, facts)
    )
    findings = [*members.errors, *members.warnings, *sections.errors, *sections.warnings]
    return [
        *(f"SKILL.md: {issue}" for issue in agent_skill_issues(skill)),
        *(f"validate: {finding.path}: {finding.message}" for finding in findings),
    ]


def _is_skill_entry(entry: Path) -> bool:
    """``SKILL.md`` as a file, or one of :data:`SKILL_DIRS` as a directory."""
    if entry.name == "SKILL.md":
        return entry.is_file()
    return entry.name in SKILL_DIRS and entry.is_dir()


def _flat_dir_problems(skill_dir: Path, name: str, allowed: _FileTest, what: str) -> list[str]:
    """Each entry of ``skill_dir/name`` that is a directory or a file ``allowed`` rejects."""
    side_dir = skill_dir / name
    if not side_dir.is_dir():
        return []
    return [
        f"{name}/{entry.name}: {name}/ holds only {what}"
        for entry in sorted(side_dir.iterdir())
        if not entry.is_file() or not allowed(entry)
    ]


def _is_rule_file(path: Path) -> bool:
    """A ``<id>.md`` or ``<id>.md.j2`` whose frontmatter ``id`` is that stem."""
    suffix = next((s for s in _RULE_SUFFIXES if path.name.endswith(s)), None)
    if suffix is None:
        return False
    try:
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    return frontmatter.get("id") == path.name.removesuffix(suffix)


def _is_reference_file(path: Path) -> bool:
    return path.suffix == ".md" or path.name in LICENSE_COPY_NAMES


def _is_script_file(path: Path) -> bool:
    return path.suffix == ".py"


def _skill_md(skill_dir: Path) -> Path:
    return skill_dir / "SKILL.md"


def _linking_files(skill_dir: Path) -> list[Path]:
    """``SKILL.md`` and every rule source of ``skill_dir``, sorted."""
    rules = [*_files(skill_dir / "rules", "*.md"), *_files(skill_dir / "rules", "*.md.j2")]
    return [_skill_md(skill_dir), *sorted(rules)]


def _files(directory: Path, pattern: str) -> list[Path]:
    """The files directly in ``directory`` matching ``pattern``, sorted; ``[]`` without it."""
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(pattern) if path.is_file())


def _skill_md_link_reason(target: str) -> str | None:
    """Why ``SKILL.md`` may not link ``target``: only ``references/<file>.md`` is allowed."""
    path = PurePosixPath(target.split("#", 1)[0])
    if not str(path) or str(path) == ".":
        return None  # an anchor in SKILL.md itself
    if len(path.parts) == 2 and path.parts[0] == "references" and path.suffix == ".md":
        return None
    return "SKILL.md links only its own references/<file>.md"
