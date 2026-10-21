---
id: review-architecture
name: Review architecture
description: "Read-only architecture review: map modules into layers, trace the import graph and its cycles, and report boundary, coupling and composition-root violations by severity."
slash: review-architecture
version: 1
input_variables:
  - name: target
    description: Package, directory or module to review (e.g. "src/app"); the whole repository when omitted
    required: false
includes_rules:
  - python-dependency-injection
eval_samples:
  - review-architecture-layer-leak
---

# Review architecture

Structural problems cost more than local ones because they spread: one business function that builds its own database client makes every caller, test and future backend pay for it. This review makes the dependency structure visible and points at the few edges that cost the most.

## Ground rules

- **Read-only.** Do not create, edit, move or delete any file. Fixes appear in the report as short before/after snippets.
- **Non-interactive.** Review the target the user named, or the whole repository when none was given. State any assumption in the report instead of stopping to ask.
- **Evidence only.** Every finding cites `path:line` for code you actually read. Never report a problem you inferred from a file name.

## Workflow

1. **Read everything in scope.** Open every module under the target, then the modules that import it. Small files often hold the wiring that matters.
2. **Build the import graph.** Record each edge, including imports inside functions and methods. Note fan-in hubs (modules most others import) and every cycle, written as a full path such as `a.py -> b.py -> a.py`.
3. **Assign one layer per module.** Use transport (HTTP handlers, CLI commands, queue consumers), business (rules and decisions), persistence (databases, files, remote APIs), composition root (the entry point or app factory that builds concrete objects and connects them), shared models (plain value types used across layers), or unclear (mixed concerns).
4. **Check each edge's direction.** Transport calls business. Business depends on abstractions it owns, and persistence implements them. Any layer may import shared models. The composition root may import anything; its wiring imports are correct, not violations.

## What to look for

- Transport importing persistence directly, skipping business logic.
- Upward imports: business or persistence importing transport, or persistence calling business functions (importing the abstraction it implements is fine).
- Web framework, ORM session, HTTP client or vendor SDK imports in business modules.
- Concrete construction outside the composition root: business code instantiating clients, stores or connections, including instances created as default arguments.
- Hidden globals and service locators: module-level mutable instances, registries or accessors that return a process-wide object.
- Domain decisions (validation, pricing, branching on business rules) inside handlers.
- ORM rows, cursors or driver objects returned past the persistence layer.
- Builtin or driver exceptions (`KeyError`, `sqlite3.Error`) escaping a layer instead of a domain error.
- One module importing or calling another module's `_private` names.
- Import cycles, including a cycle that a function-local import only hides.

## Not violations

- Imports under `if TYPE_CHECKING:`; they create no runtime edge.
- Function-local imports that keep an optional or heavy dependency lazy. Flag a local import only when its purpose is to dodge a runtime cycle.
- A single-module script or small tool. Do not invent layers where there is nothing to separate.

## Severity

- **Critical**: breaks the layer direction or makes business code untestable without real infrastructure. Examples are concrete construction in business logic, upward imports, and cycles that cross layers.
- **Important**: coupling that compounds over time. Examples are hidden globals, service locators, leaked persistence types, builtin exceptions crossing a boundary, and hubs that mix concerns.
- **Suggestion**: a local improvement, such as cross-module private access, a handler doing light domain work, or a module whose layer is unclear.

Within each bucket, rank by blast radius: the number of modules and callers the problem reaches.

## Output format

1. **Layer map**: one line per layer, listing its modules. Then **Dependency flows**: one line per edge or group of edges, `a.py -> b.py`, marked `ok` or `violation: <kind>`. Then **Cycles**: each cycle as a path, or `none found`. If the code is not layered, show the actual flow and sketch a target layering instead.
2. **What works well**: two to four specific strengths, each with a file and line.
3. **Findings**, grouped under Critical, Important and Suggestion. Each finding gives `path:line`, the principle broken (for example "depend on abstractions" or "one composition root"), its concrete cost (what it makes hard to test, swap or change), and a minimal before/after of a few lines.
4. **Fix plan**: an ordered list of small, safe steps, highest blast radius first, each naming the files it touches.

Do not modify the code; this review only reports.
