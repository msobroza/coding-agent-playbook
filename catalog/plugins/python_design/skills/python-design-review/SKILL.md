---
id: python-design-review
name: python-design-review
description: "Reviews the internal design of Python code (data shapes, function signatures, class cohesion, coupling, construction, idioms and pattern fit) and proposes the smallest fix for each problem, ranked by severity. Use when asked to critique or tidy the design of Python modules, to hunt design smells, to choose between a function, class, dataclass, Protocol, ABC or Callable, to judge whether a design pattern earns its keep, or to split a class that has taken on unrelated jobs."
---

# Python design review

A reading procedure for judging how Python code is shaped at the level of data, functions and classes, and for recommending the lightest change that fixes each problem. This file is complete on its own. Longer material may sit next to it: references/smell-catalog.md, references/quality-checklist.md, references/principles-and-grasp.md, references/patterns.md and references/lint-guardrails.md. Two optional scanners may sit there too: scripts/detect_smells.py and scripts/lcom4_clusters.py.

Layer boundaries, composition roots and persistence design are a separate review. This one stays inside modules.

## When to load

- Someone asks for a design review, a smell hunt, or "how would you clean this up" on Python code.
- A class or module keeps growing and its responsibilities need untangling.
- You must choose a construct (function, class, dataclass, Protocol, ABC, Callable) or decide whether a pattern is warranted.
- A refactor is planned and the problems should be ranked before anything is touched.

Not for formatting nits a formatter settles, performance tuning, security review or architectural layering.

## Ground rules

- Read before judging. Read every in-scope `.py` file and the callers of each hotspot. Skip generated, vendored and migration code. Tests show intent; review them only when asked.
- Stay read-only unless asked to change code.
- Every finding cites evidence you read: `file:line` and what the code does there. Scanner output alone is not evidence.
- Flag problems in both directions: missing structure (a 200-line function) and unearned structure (a Protocol, factory or strategy with one implementation and no test seam).
- Leave deliberate idioms alone: documented extension points (entry-point groups, plugin ABCs), framework base classes and framework-required mixins, overrides of a base-class or ABC method that ignore `self`, exception hierarchies, and keyword-only option flags that do not switch algorithms.
- When the project has a consistent convention, follow it and say that you did.

## Scan order

Earlier passes often explain later smells, and fixing the data first makes many function and class smells disappear.

1. **Data shapes.** Records passed as dicts, parallel collections, prefixed field groups, stored derived values, string option sets, float money, frozen dataclasses holding lists, keyed lookups done by scanning a list.
2. **Functions and signatures.** Length, nesting, parameter count, boolean switches, mutable defaults, misleading verbs, I/O mixed with computation.
3. **Classes and cohesion.** Methods clustering around disjoint attributes (LCOM4 above 1), staticmethod-only namespaces, stateless one-method classes, methods ignoring `self`, value-only subclasses, deep hierarchies, mixins that carry state.
4. **Coupling and construction.** Collaborators built inside `__init__`, attribute chains through other objects, reaching into another object's private state, module globals rebound at runtime, objects that need a second setup call, `__new__` returning other types.
5. **Idioms.** Resources without `with`, decorators without `functools.wraps`, `match` without a fallback, `lru_cache` on methods, naive datetimes, bare or swallowing `except`.
6. **Patterns.** Only now ask whether a pattern would help, or whether one already present should go. Use the lightest-form table below.

## Severity

Report in this order. Within a level, put the widest blast radius first (most callers, most shared state).

| Severity | Meaning | Typical findings |
| --- | --- | --- |
| correctness | Wrong results or hidden failures under realistic use | shared mutable default, bare or swallowing `except`, float money, leaked mutable internals, frozen dataclass with a list field used as a key, `lru_cache` on a method, `global` rebinding under concurrency |
| design | The next change becomes expensive or risky | low cohesion, hard-wired I/O collaborator, algorithm-switching bool, isinstance ladder, long parameter list, deep nesting, attribute chains |
| clarity | Slows readers without blocking change | vague or type-suffixed names, namespace class, method that could be a function, asymmetric names |
| restraint | Structure that costs more than it returns | single-implementation Protocol with no test seam, factory with one product, builder for three fields |

Report correctness findings even when only design was asked about.

## Smell to fix

| Smell | First fix to try |
| --- | --- |
| mutable-default-argument | Default to `None` and copy inside, or to an immutable `()` or `frozenset()`; `field(default_factory=list)` in a dataclass |
| isinstance-ladder | Put the behavior on the types (method or Protocol), or map type or enum to handler in a dict; a `match` must end in a raising `case _` |
| long-parameter-list | Group values that travel together into a dataclass; make options keyword-only |
| boolean-flag-parameter | Split into two named functions when the flag picks an algorithm; keyword-only when it tweaks one detail |
| bare-except, swallowed-exception | Catch the specific error you can handle; otherwise clean up and re-raise, or let it propagate |
| deep-nesting | Guard clauses and early returns; extract the loop body |
| long-function | Extract steps named for what they compute; separate gathering, computing and presenting |
| method-could-be-function | Module-level function; `staticmethod` only when it is part of the class's concept |
| namespace-class | A module of plain functions |
| type-in-name | Name the role, not the type: `stations`, not `station_list` |
| module-level-mutable-global-rebound | Pass the state in, or keep it in an object the entry point creates |
| parallel collections, prefixed fields | One record type |
| stored derived value | `@property`, or compute on demand |
| string option set | `Enum`, `StrEnum` or `Literal[...]` |
| hard-wired collaborator | Constructor parameter typed as a `Protocol` or `Callable`, wired in the composition root |
| low cohesion (LCOM4 above 1) | Split along the attribute clusters, then compose the parts |

## Choosing a construct

| You have | Use | Instead of |
| --- | --- | --- |
| A computation with no state between calls | a function | a class with one method and no fields |
| Related functions with no shared state | a module | a class of staticmethods |
| Named fields and little behavior | a `@dataclass` (frozen for values) or `NamedTuple` | a dict, or a tuple read by position |
| State plus rules that keep it consistent | a class whose methods guard its invariants | free functions that all mutate the same dict |
| One behavior to inject | a `Callable` alias with a role name | a single-method ABC |
| Several methods a consumer needs from a collaborator | a small `Protocol` declared beside the consumer | importing the concrete class |
| Shared implementation, enforced overrides or a documented extension point | an `ABC` | the same base logic copied into every implementer |
| A closed set of options | `Enum`, `StrEnum` or `Literal[...]` | bare string constants |
| A value with rules (a quantity and unit, an email) | a frozen dataclass that validates in `__post_init__` | a bare `str` or `float` |

Promote only when a need appears: function, then closure, then callable dataclass, then class; `Callable`, then `Protocol`, then `ABC`.

## Patterns: lightest form first

Move right only when the lighter form fails. The last column says when to stay lighter, or to skip the pattern altogether.

| Signal in the code | Lightest Pythonic form | Heavier form | Stop when |
| --- | --- | --- | --- |
| if/elif choosing among algorithms | pass a function (`Callable` alias) | callable dataclass, then Protocol classes | two fixed branches that will not grow |
| if/elif mapping a key to data or a constructor | dict lookup that raises a clear error for unknown keys | registry filled by `register` functions | the keys are a closed enum and `match` reads fine |
| Undo, redo, queued or logged actions | functions returning an undo closure | command dataclasses with `execute` and `undo` | nobody needs to reverse or replay |
| Same steps, different details across classes | one function taking the varying steps as parameters | ABC template method | only one variant exists |
| Sequential transformations | a list of functions applied in order | handler chain with early exit | three steps read fine inline |
| Core logic calling several side-effect systems | return event objects; one dispatcher calls handlers | in-process pub/sub keyed by event class | one side effect with one caller |
| Behavior depends on a mode that changes | enum plus a transition table | state objects behind a Protocol | two states that barely differ in behavior |
| Many optional parts, validated together | dataclass with defaults and keyword-only fields | builder whose `build()` returns a frozen product | every field is known at once |
| A third-party API with the wrong shape | wrapper function | adapter class implementing your Protocol | both sides are your own code |
| Callers coordinate many subsystem calls | one function that runs the sequence | facade class | the subsystem is already simple |
| Families of objects that must match | frozen dataclass bundling the callables | one factory class per family | there is only one family |
| Extension by other packages | explicit `register(registry)` functions | entry-point discovery | every variant lives in this repo |
| Expensive value needed only sometimes | `functools.cached_property` or a cached module function | lazy proxy object | it is always needed at startup |
| One shared instance | build it in the entry point and pass it down | module-level instance for process-wide services | tests need separate instances; metaclass or `__new__` caching adds nothing over this |

The long form, with the built-ins that replace each pattern and their pitfalls, is references/patterns.md.

## Optional scanners

If scripts/detect_smells.py exists next to this file, run it on the code under review, using the path of the directory that holds this SKILL.md:

```bash
python3 <this-skill-dir>/scripts/detect_smells.py src/
```

It takes files or directories (default: the current directory) and prints a JSON array of `{"smell", "file", "line", "evidence"}` objects sorted by file, line and smell. It exits 0 even when it finds smells and 2 on a usage error or unreadable path; files it cannot parse or analyse are reported on stderr and skipped. Each `smell` value is an entry heading in references/smell-catalog.md.

If scripts/lcom4_clusters.py exists, run it to find split candidates:

```bash
python3 <this-skill-dir>/scripts/lcom4_clusters.py src/
```

It prints `{"class", "file", "line", "lcom4", "clusters"}` for each class whose methods fall into more than one group, where methods join a group by sharing a `self` attribute or calling each other. Add `--all` to list every class. Each cluster is a candidate class after a split.

Both scripts print candidates, not verdicts. Open the code at every hit and confirm it before reporting. Dismiss hits that are deliberate (an override, a framework hook, a documented flag) and list them under "Considered and kept". When neither script is present, apply the same heuristics by reading. If the `playbook metrics` command is installed, its complexity and cohesion numbers can back a finding as well.

## Output format

Open with a one-line scope and a count per severity:

```text
Design review: src/irrigation (14 files read)
correctness 2 | design 5 | clarity 3 | restraint 1
```

Then one entry per finding, in severity order:

- **smell id**, `file:line`, severity.
- **Evidence:** what the code does, in one or two sentences.
- **Why it matters:** the principle and its concrete cost in this code.
- **Fix:** a minimal before/after, or a precise description of the lightest change that works.

Close with:

- **Considered and kept:** scanner hits and tempting refactors you rejected, each with its reason.
- **Suggested order:** which fixes go first (correctness, then the ones that unblock others) and which need characterization tests before anyone touches them.

If the code is in good shape, say so plainly. Never pad a report with invented findings.
