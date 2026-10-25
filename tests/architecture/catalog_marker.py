"""Which test modules depend on skill content, and whether each one carries the ``catalog`` marker.

ADR 0010: a pull request that changes only skill content runs ``pytest -m catalog``
(the skill lane), so the lane is only as sound as the marker. A test module is
skill-dependent when it imports a skill helper, directly or through helper modules
under ``tests/``. Such a module (unless :data:`MARKER_EXEMPTIONS` names it), and
every test module under ``tests/core_skills/`` or ``tests/core_skill_pins/``
(skill-lane paths), needs a module-level ``pytestmark`` holding
``pytest.mark.catalog``. tests/architecture/test_catalog_marker.py runs the guard.

Stdlib only, and the sources are parsed, never imported: the guard must not run
the code it judges.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping
    from pathlib import Path

#: Modules that read skill content: importing one, or any submodule, makes a module skill-dependent.
SKILL_HELPER_MODULES: Final = (
    "tests.core_skill_pins",
    "tests._core_skill_layout",
    "tests.core_skills",
)
#: Names of a shared helper module that read or point at skill content; its other names
#: do not. Importing the module itself, or ``*`` from it, counts as importing them all.
#: test_catalog_marker.py fails when a helper there uses one of these names unlisted.
SKILL_HELPER_NAMES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "tests._catalog": frozenset(
            {
                "CORE_SKILLS_ROOT",
                "KEPT_RULE_IDS",
                "_parsed_core_rules",
                "core_rule_paths",
                "core_rule_skill_ids",
                "core_rules",
                "core_skill_ids",
                "core_skill_root",
                "core_skills",
            }
        )
    }
)
#: Skill-dependent test modules that carry no marker on purpose, each with why. They
#: read core skill ids only to adapt to whatever core ships, so a skill edit cannot
#: change their result, and they are among the slowest sync tests: marking them
#: would add about half again to the skill lane (ADR 0010). The full lane on every
#: push to main still runs them. An entry that no longer applies fails the guard.
MARKER_EXEMPTIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "tests/cli/test_sync_orphans.py": "core_skill_ids() only tolerates the core skills",
        "tests/cli/test_sync_skills.py": "core_skill_ids() only filters out the core skills",
        "tests/cli/test_sync_validate_gate.py": "core_rule_skill_ids() only builds a message",
        "tests/cli/test_validate_skills.py": "core_rule_skill_ids() only builds a message",
    }
)
#: pytest's default ``python_files``: pyproject.toml sets no other.
_TEST_FILE_PATTERNS: Final = ("test_*.py", "*_test.py")
_CATALOG_MARK: Final = "pytest.mark.catalog"
#: The nodes a statement can nest inside: blocks, ``except`` clauses and ``case`` arms.
_STATEMENT_NODES: Final = (ast.stmt, ast.excepthandler, ast.match_case)
#: Test-shaped files under tests/fixtures/ are sample trees for other tests, not tests.
_FIXTURES_DIR: Final = "fixtures"
#: The test directories that are skill-lane paths (ADR 0010), under ``tests/``.
_SKILL_LANE_TEST_DIRS: Final = ("core_skills", "core_skill_pins")
_MARKER_FIX_HINT: Final = (
    "Fix: add pytestmark = pytest.mark.catalog at module level"
    " (or append pytest.mark.catalog to an existing pytestmark list)."
)


@dataclass(frozen=True)
class ImportRef:
    """One imported module, plus the name taken from it by ``from module import name``."""

    module: str
    name: str | None = None

    def candidates(self) -> tuple[str, ...]:
        """The modules this import may load: ``module.name`` (if a submodule) first, then ``module``.

        Example: ``ImportRef("tests", "kit").candidates()`` -> ``("tests.kit", "tests")``.
        """
        if self.name is None:
            return (self.module,)
        return (f"{self.module}.{self.name}", self.module)

    def parent_packages(self) -> tuple[str, ...]:
        """The packages Python imports before ``module``, outermost first.

        Example: ``ImportRef("tests.kit.sub", "f").parent_packages()`` -> ``("tests", "tests.kit")``.
        """
        parts = self.module.split(".")
        return tuple(".".join(parts[:end]) for end in range(1, len(parts)))


@dataclass(frozen=True)
class SkillReach:
    """The skill helper a module reaches, and the helper modules the import goes through."""

    helper: str
    via: tuple[str, ...]

    def describe(self) -> str:
        """``reaches <helper> directly`` or ``reaches <helper> through a -> b``.

        Example: ``SkillReach("tests.core_skill_pins", ()).describe()``.
        """
        if not self.via:
            return f"reaches {self.helper} directly"
        return f"reaches {self.helper} through {' -> '.join(self.via)}"


@dataclass(frozen=True)
class UnmarkedModule:
    """A test module that lacks the marker; ``reach`` is ``None`` for one in a skill-lane test dir."""

    path: str
    reach: SkillReach | None

    def describe(self) -> str:
        """One report line: the module's path and why it needs the marker.

        Example: ``UnmarkedModule("tests/core_skills/x/test_a.py", None).describe()``.
        """
        if self.reach is None:
            return f"- {self.path}: sits under a skill-lane test directory"
        return f"- {self.path}: {self.reach.describe()}"


def _collected_test_modules(tests_root: Path) -> list[Path]:
    """Every ``test_*.py`` and ``*_test.py`` under ``tests_root`` outside ``fixtures/``, sorted.

    Example: ``_collected_test_modules(REPO_ROOT / "tests")[0].name`` -> ``"test_...py"``.
    """
    paths = {path for pattern in _TEST_FILE_PATTERNS for path in tests_root.rglob(pattern)}
    return sorted(p for p in paths if p.relative_to(tests_root).parts[0] != _FIXTURES_DIR)


def _module_name_of(path: Path, tests_root: Path) -> str:
    """The dotted name ``path`` imports as, with ``tests_root``'s name as the top package.

    Example: ``_module_name_of(root / "cli" / "__init__.py", root)`` -> ``"tests.cli"``.
    """
    parts = path.relative_to(tests_root.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _import_refs(tree: ast.Module, package: str) -> list[ImportRef]:
    """Every import in ``tree``, at any depth, as absolute :class:`ImportRef` s in source order.

    ``package`` is what relative imports resolve against. Imports inside functions
    and ``if TYPE_CHECKING:`` blocks count, as they do for the engine's import
    contracts (``exclude_type_checking_imports = false``): the guard errs towards
    marking, which costs skill-lane time, never soundness.

    Example: ``_import_refs(ast.parse("from tests import kit"), "tests")`` -> ``[ImportRef("tests", "kit")]``.
    """
    refs: list[ImportRef] = []
    for node in _import_statements(tree.body):
        if isinstance(node, ast.Import):
            refs.extend(ImportRef(alias.name) for alias in node.names)
            continue
        module = _absolute_module(node.module, node.level, package)
        refs.extend(ImportRef(module, None if a.name == "*" else a.name) for a in node.names)
    return refs


def _import_statements(nodes: Iterable[ast.AST]) -> Iterator[ast.Import | ast.ImportFrom]:
    # Statements only, in source order: an import is never inside an expression, and
    # skipping expression subtrees made the real-tree walk several times faster.
    for node in nodes:
        if isinstance(node, ast.Import | ast.ImportFrom):
            yield node
        children = ast.iter_child_nodes(node)
        yield from _import_statements(c for c in children if isinstance(c, _STATEMENT_NODES))


def _absolute_module(module: str | None, level: int, package: str) -> str:
    """``from <level dots><module> import ...`` written in ``package``, as an absolute name."""
    if level == 0:
        return module or ""
    parts = package.split(".")
    base = parts[: len(parts) - level + 1]
    return ".".join([*base, module] if module else base)


def _in_skill_helper_module(module: str) -> bool:
    return any(module == m or module.startswith(f"{m}.") for m in SKILL_HELPER_MODULES)


def _skill_helper_of(ref: ImportRef) -> str | None:
    """The skill helper ``ref`` imports directly, or ``None``.

    Example: ``_skill_helper_of(ImportRef("tests", "core_skill_pins"))`` -> ``"tests.core_skill_pins"``.
    """
    named = _named_skill_helper(ref)
    if named is not None:
        return named
    # The imported module first, so ``from pkg.mod import NAME`` names pkg.mod, not NAME;
    # ``module.name`` still catches ``from tests import core_skill_pins``.
    candidates = reversed(ref.candidates())
    return next((m for m in candidates if _in_skill_helper_module(m)), None)


def _named_skill_helper(ref: ImportRef) -> str | None:
    """A skill name of a :data:`SKILL_HELPER_NAMES` module that ``ref`` imports, or ``None``.

    ``import tests._catalog``, ``from tests import _catalog`` and a star import
    reach every listed name, through attribute access or ``*``, so they count.
    """
    if ref.module in SKILL_HELPER_NAMES and ref.name is None:
        return ref.module
    if ref.name in SKILL_HELPER_NAMES.get(ref.module, frozenset()):
        return f"{ref.module}.{ref.name}"
    whole_module = f"{ref.module}.{ref.name}"
    return whole_module if whole_module in SKILL_HELPER_NAMES else None


def unlisted_skill_names(tree: ast.Module, listed: frozenset[str]) -> list[str]:
    """The top-level names of a helper module that use a ``listed`` name but are not listed.

    Keeps :data:`SKILL_HELPER_NAMES` from drifting: a new ``tests._catalog`` helper
    built on ``CORE_SKILLS_ROOT`` or ``core_rules`` reads skill content too.

    Example: ``unlisted_skill_names(ast.parse("A = 1\\ndef f(): return A"), frozenset({"A"}))``
    -> ``["f"]``.
    """
    unlisted: list[str] = []
    for node in tree.body:
        name = _defined_name(node)
        if name is None or name in listed:
            continue
        if {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & listed:
            unlisted.append(name)
    return sorted(unlisted)


def _defined_name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name
    target: ast.expr | None = node.target if isinstance(node, ast.AnnAssign) else None
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def has_catalog_marker(tree: ast.Module) -> bool:
    """Whether the module's last top-level ``pytestmark`` is ``pytest.mark.catalog`` or holds it.

    Per-test decorators do not count: a module marked test by test can end up half
    marked, and the skill lane would then skip the rest without a sign.

    Example: ``has_catalog_marker(ast.parse("pytestmark = pytest.mark.catalog"))`` -> ``True``.
    """
    values = list(_pytestmark_values(tree))
    if not values:
        return False
    last = values[-1]
    elements = last.elts if isinstance(last, ast.List | ast.Tuple) else [last]
    return any(ast.unparse(element) == _CATALOG_MARK for element in elements)


def _pytestmark_values(tree: ast.Module) -> Iterator[ast.expr]:
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(_is_pytestmark(target) for target in targets):
            yield node.value


def _is_pytestmark(target: ast.expr) -> bool:
    return isinstance(target, ast.Name) and target.id == "pytestmark"


class SkillDependencies:
    """Which modules under one ``tests/`` root reach a skill helper; each helper is parsed once."""

    def __init__(self, tests_root: Path) -> None:
        self._tests_root = tests_root
        #: Helper module -> its imports, or ``None`` when the module is not a helper to follow.
        self._helper_refs: dict[str, list[ImportRef] | None] = {}

    def reach_of(self, path: Path, tree: ast.Module) -> SkillReach | None:
        """The first skill helper the module at ``path`` (parsed as ``tree``) reaches, or ``None``.

        Example: ``SkillDependencies(root).reach_of(path, ast.parse(path.read_text()))``.
        """
        module = _module_name_of(path, self._tests_root)
        return self._first_reach(_import_refs(tree, _package_of(module, path)), (), set())

    def _first_reach(
        self, refs: Iterable[ImportRef], via: tuple[str, ...], seen: set[str]
    ) -> SkillReach | None:
        for ref in refs:
            helper = _skill_helper_of(ref)
            if helper is not None:
                return SkillReach(helper, via)
            reach = self._reach_through_helper(ref, via, seen)
            if reach is not None:
                return reach
        return None

    def _reach_through_helper(
        self, ref: ImportRef, via: tuple[str, ...], seen: set[str]
    ) -> SkillReach | None:
        # ``seen`` spans one module's walk: a helper explored once, or on the route
        # (an import cycle), cannot open a new route, so it is not walked again.
        # The parent packages run first on import, so their __init__ counts too.
        for candidate in (*ref.parent_packages(), *ref.candidates()):
            refs = self._refs_of_helper(candidate)
            if refs is None or candidate in seen:
                continue
            seen.add(candidate)
            reach = self._first_reach(refs, (*via, candidate), seen)
            if reach is not None:
                return reach
        return None

    def _refs_of_helper(self, module: str) -> list[ImportRef] | None:
        if module not in self._helper_refs:
            path = self._helper_path(module)
            refs = (
                None
                if path is None
                else _import_refs(_parse_module(path), _package_of(module, path))
            )
            self._helper_refs[module] = refs
        return self._helper_refs[module]

    def _helper_path(self, module: str) -> Path | None:
        """The source of ``module`` when it is a helper to follow, else ``None``.

        Skill helpers are where the walk stops. A test module is followed like any
        helper: importing a function out of it runs that module's imports, and its
        own marker does not mark the importer.
        """
        if _in_skill_helper_module(module) or not module.startswith(f"{self._tests_root.name}."):
            return None
        base = self._tests_root.parent.joinpath(*module.split("."))
        return next(
            (p for p in (base.with_suffix(".py"), base / "__init__.py") if p.is_file()), None
        )


def _package_of(module: str, path: Path) -> str:
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _repo_relative(path: Path, tests_root: Path) -> str:
    return path.relative_to(tests_root.parent).as_posix()


def unmarked_skill_dependent_modules(
    tests_root: Path, exemptions: Mapping[str, str] = MARKER_EXEMPTIONS
) -> list[UnmarkedModule]:
    """Rule 1: every test module that reaches a skill helper but lacks the marker, sorted by path.

    A module listed in ``exemptions`` (repo-relative path -> why) is not reported.

    Example: ``marker_report(unmarked_skill_dependent_modules(REPO_ROOT / "tests"))``.
    """
    dependencies = SkillDependencies(tests_root)
    offenders: list[UnmarkedModule] = []
    for path in _collected_test_modules(tests_root):
        if _repo_relative(path, tests_root) in exemptions:
            continue
        tree = _parse_module(path)
        reach = None if has_catalog_marker(tree) else dependencies.reach_of(path, tree)
        if reach is not None:
            offenders.append(UnmarkedModule(_repo_relative(path, tests_root), reach))
    return offenders


def stale_exemptions(
    tests_root: Path, exemptions: Mapping[str, str] = MARKER_EXEMPTIONS
) -> list[str]:
    """The exemptions that no longer apply, each with why, sorted by path.

    An exemption is stale when its module is gone, carries the marker, or reaches
    no skill helper any more: then it only hides a future dependency.

    Example: ``stale_exemptions(REPO_ROOT / "tests")`` -> ``[]``.
    """
    dependencies = SkillDependencies(tests_root)
    reasons = {path: _staleness(tests_root.parent / path, dependencies) for path in exemptions}
    return [f"{path}: {why}" for path, why in sorted(reasons.items()) if why]


def _staleness(path: Path, dependencies: SkillDependencies) -> str | None:
    if not path.is_file():
        return "no such test module"
    tree = _parse_module(path)
    if has_catalog_marker(tree):
        return "it carries the catalog marker"
    return "it reaches no skill helper" if dependencies.reach_of(path, tree) is None else None


def unmarked_skill_lane_test_modules(tests_root: Path) -> list[UnmarkedModule]:
    """Rule 2: every test module under a skill-lane test directory that lacks the marker.

    ``tests/core_skills/`` and ``tests/core_skill_pins/`` are skill-lane paths, and
    the skill lane runs only marked tests, so an unmarked module there would run on
    no skill-lane pull request at all. Sorted by path.

    Example: ``unmarked_skill_lane_test_modules(REPO_ROOT / "tests")`` -> ``[]``.
    """
    lane_dirs = [tests_root / name for name in _SKILL_LANE_TEST_DIRS]
    return [
        UnmarkedModule(_repo_relative(path, tests_root), None)
        for path in _collected_test_modules(tests_root)
        if any(path.is_relative_to(d) for d in lane_dirs)
        and not has_catalog_marker(_parse_module(path))
    ]


def marker_report(offenders: Iterable[UnmarkedModule]) -> str:
    """The guard's failure message: a header, one line per offender, then the fix.

    Example: ``marker_report([UnmarkedModule("tests/core_skills/x/test_a.py", None)])``.
    """
    lines = [offender.describe() for offender in offenders]
    header = (
        f"{len(lines)} test module(s) lack the catalog marker"
        " (ADR 0010: the skill lane runs only -m catalog):"
    )
    return "\n".join([header, *lines, _MARKER_FIX_HINT])
