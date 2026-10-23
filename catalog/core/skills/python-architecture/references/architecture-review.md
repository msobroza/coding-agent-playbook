# Architecture review

A read-only procedure for reviewing how a whole package's modules depend on each other: map the layers with the skill's layer_map.py script, configure the run for the project, confirm every hit by reading the import, walk the coupling checklist, then report. Each kind of finding names the rule that fixes it. The review edits nothing and asks nothing: it ends with a report and a fix plan.

## Contents

- When to review
- 1. Read the code
- 2. Map the layers with layer_map.py
- 3. Configure the run for the project
- 4. Confirm every hit
- 5. Coupling checklist
- 6. Report

## When to review

- Planning the package layout of a new service, API, worker or CLI, or adding its first database or external integration.
- Reviewing an import graph: a handler that queries the ORM, business code that imports a web framework or builds its own client, an import cycle, an ORM row returned to a caller.
- Deciding whether a port, a repository, a unit of work, a read model or an event store is justified.

The review covers relations between modules. Function-level style (names, long functions, idioms) belongs to the python-coding skill, and the shape of code inside one module to the design-patterns skill.

## 1. Read the code

Read every Python file in scope, test code included, before judging any of them. Note what each module imports, at module level and inside functions, and which modules build concrete sessions, clients and settings objects.

## 2. Map the layers with layer_map.py

Run the script before reading the code in detail. It needs Python 3.10 or later and the standard library only; nothing in the project is imported or executed.

```text
python3 scripts/layer_map.py [ROOT] [--layer NAME=DIR1,DIR2 ...] [--allow NAME=DEP1,DEP2 ...] [--root-module NAME ...] [--json]
```

- ROOT is the project directory, the current directory when omitted; when ROOT/src holds Python files, that is what gets scanned. Test code (`tests/`, `test/`, `test_*.py`, `*_test.py`, `conftest.py`) is skipped, because tests wire their own fakes the way a composition root does.
- A module's layer is the outermost part of its dotted name that matches a layer name, so `routes/loans.py` and `loans/routes.py` are both interface code. A module that matches nothing is unlayered and never checked.
- A package named like a layer is a container, not a layer, when the names below it cover at least two other layers and no package beside it names another layer (`api/` holding `api/services/` and `api/db/`). Containers are listed in the report; a layer name with `/`, such as `api/models`, overrules one for part of its tree.
- `--layer NAME=DIR1,DIR2` replaces one layer's names or adds a layer. `--allow NAME=DEP1,DEP2` replaces the layers NAME may import. `--root-module NAME` marks one more composition root, as a dotted module, its trailing part or a scanned file's path. Repeat each flag once per value.
- Only interface modules may import a composition root. Any other layered module that imports one is a violation: a service locator.
- Imports under `if TYPE_CHECKING:` never fail the run; the ones that would break a rule are listed apart. Cycles count only imports that run at import time, so a cycle hidden by a function-local import has to be found by reading the code.
- The default output is a text report: the rules, the layer map, the flows between layers, rule violations with `path:line`, import cycles and type-only imports. `--json` prints the same as one object (`layers`, `flows`, `violations`, `cycles`, `type_only`, `unlayered`, `composition_roots`, `container_packages`).
- Exit code 0 means no violation and no cycle, 1 at least one of either, and 2 a usage error, including a `--root-module` that matches nothing and a ROOT with no module to scan.

```text
Rule violations: 2
  shop/routers/carts.py:1  shop.routers.carts [interface] imports shop.db.tables [infrastructure]
  shop/services/carts.py:1  shop.services.carts [application] imports shop.db.tables [infrastructure]

Import cycles (modules that import one another at import time): 1
  shop.db.tables, shop.services.carts
```

## 3. Configure the run for the project

Describe the project to the script instead of arguing with its output. First decide the persistence step the code is at (`arch-persistence-steps`):

- At step 1 (injected session, queries in the use case) use cases legitimately import the mapped classes. If those live in `db/`, run with `--allow application=domain,infrastructure`; if they live in `models/`, the defaults already treat them as domain.
- From step 2 on, a `models/` package that holds ORM tables is infrastructure, and a use case importing it is a leak. Pass `--layer domain=domain,entities --layer infrastructure=db,models,repositories,adapters,infrastructure,infra,persistence,storage` so those imports show up.
- Singular module names (`service.py`, `repository.py`) match nothing by default. Add them with `--layer`, repeating the default names you keep (`arch-one-layout-axis`).
- A worker entry point under another file name needs `--root-module worker`, or its wiring imports show up as violations (`arch-composition-root`).

## 4. Confirm every hit

Every hit is a candidate, not a verdict: the layer map is inferred from names. Open the importing line and decide whether the module is an unrecognized composition root, a misclassified directory or a real leak. For each cycle, check whether it crosses layers, which is critical, or stays inside one package, where it usually means a module should be split or merged (`arch-break-import-cycles`).

## 5. Coupling checklist

Walk the whole import graph with these questions; each names the rule that holds the fix.

| Look for | Rule |
| --- | --- |
| An interface module that imports a database module or runs a query | `arch-dependency-direction`, `arch-use-case-functions` |
| A use case that imports the web framework, the engine module or a concrete client instead of taking a port | `arch-dependency-direction`, `arch-ports` |
| Concrete objects built in many files instead of one composition root, or a module importing the root to fetch a collaborator | `arch-composition-root` |
| Two modules importing each other, or a cycle masked by a function-local import | `arch-break-import-cycles` |
| ORM rows, driver errors or `dict[str, Any]` crossing a layer | `arch-typed-records-across-layers` |
| A port with one implementation and no fake, or a remote system called without one | `arch-ports` |
| A repository that commits, returns ORM objects or grows CRUD for every table | `arch-repository-port`, `sqlalchemy-repositories` |
| One use case writing through several repositories with separate commits | `arch-unit-of-work` |
| Module-level mutable state shared across files | python-coding's python-no-global-singletons |
| Business code that cannot run without a real database or network | `arch-make-legacy-testable` |
| One module imported by nearly everything, or a utils, helpers or common package | `arch-no-junk-drawer-packages` |
| Layer packages and feature packages mixed in one tree | `arch-one-layout-axis` |

Reaching into another module's private names and long attribute chains are coupling inside the code rather than between layers: the design-patterns rules design-low-coupling and design-tell-dont-ask.

## 6. Report

1. **Layer map**: one line per layer listing its modules, then one line each for composition roots, container packages (when there are any) and unlayered modules. A vertical list, never multi-column art.
2. **Flows**: layer-to-layer edges with counts, each marked ok or violation. A project that follows no layer model gets its flows as they are, plus one line on the target layout.
3. **What works well**: specific strengths with file and line, such as use cases that take their ports or one composition root.
4. **Violations and cycles**: `path:line`, importer and imported module, and the rule broken, each confirmed by reading the code. Cycles are written as full paths, such as `a.py -> b.py -> a.py`.
5. **Persistence step**: the step the code is at, and whether the signal for the next step, or for stepping back, is present.
6. **Findings by severity.** Critical: wrong-direction imports, business code that cannot run without real infrastructure, cycles that cross layers. Important: hidden globals and service locators, ORM rows or driver errors crossing a boundary, commits inside data-access code. Suggestion: speculative ports, a handler doing light domain work, a module whose layer is unclear. Each finding gives `path:line`, the rule id, its concrete cost (what it makes hard to test, swap or change) and a minimal before and after.
7. **Fix plan**: small, safe steps ordered by blast radius, each naming the files it touches.
