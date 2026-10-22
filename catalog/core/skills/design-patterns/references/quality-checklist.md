# Design quality checklist

One numbered list for a quick design pass over a module or a diff, in the same order as a full review: data first, patterns last. Each item names the smell ids from smell-catalog.md it covers and the rule that holds its detail. Use it when a ranked review per `design-review-by-severity` would be more than the change needs.

A "no" is a candidate finding, not an automatic one: confirm it in the code, and skip it when the code states a reason for its shape.

## Contents

- Reporting a quick pass
- Data shapes (1-10)
- Functions and signatures (11-19)
- Names (20-24)
- Classes and cohesion (25-33)
- Coupling and construction (34-43)
- Errors and idioms (44-52)
- Patterns and restraint (53-58)

## Reporting a quick pass

Read every file in scope first. Report each "no" as the item number, `file:line` and a one-line fix, grouped by file, with a count per item at the top:

```text
Quality check: 14 files read, 8 findings
- item 16 (deep nesting): 3
- item 18 (missing type hints): 2
- item 45 (swallowed exception): 2
- item 13 (boolean flag): 1
```

## Data shapes

1. Records crossing a function or module boundary are dataclasses, `NamedTuple`s or models, not `dict[str, Any]` (dict-as-record). Rule: `design-start-with-the-data`.
2. Values that belong together live in one record, not in parallel lists or dicts (parallel-collections). Rule: `design-start-with-the-data`.
3. No group of fields shares a prefix that is really a missing type, and no class holds so many fields that they fall into groups (prefixed-field-group). Rule: `design-start-with-the-data`.
4. Values computable from other fields are properties, not stored copies (stored-derived-value). Rule: python-coding's python-data-shapes.
5. Closed option sets are `Enum`, `StrEnum` or `Literal`, not bare strings (string-option-set). Rule: python-coding's python-enums.
6. Money is `Decimal` or integer minor units, never `float` (float-money). Rule: `design-value-objects`.
7. Frozen dataclasses hold only immutable fields: `tuple`, `frozenset`, other frozen values (shallow-frozen-dataclass). Rule: python-coding's python-frozen-dataclasses.
8. No method hands out the object's own mutable list or dict (leaked-mutable-internals). Rule: python-coding's python-hide-internal-state.
9. Keyed lookups use a dict built once, not a list scan per lookup (list-scan-lookup). Rule: python-coding's python-collection-choice.
10. Domain values with rules (quantities with units, identifiers, codes, email addresses) have their own small types where mixing them up would be costly (bare-primitive). Rule: `design-value-objects`.

## Functions and signatures

11. No mutable default arguments (mutable-default-argument). Rule: python-coding's python-typing.
12. At most five parameters; related ones are grouped, options are keyword-only (long-parameter-list). Rule: `design-start-with-the-data`.
13. No boolean parameter selects between two algorithms (boolean-flag-parameter). Rule: python-coding's python-function-signatures.
14. Each function does one job and fits on a screen; the house target is well under the scanner's 50-line limit (long-function). Rule: python-coding's python-small-units.
15. A complex condition is a named predicate function rather than an inline expression with a comment. Rule: python-coding's python-small-units.
16. Nesting stays at three blocks or fewer, using guard clauses and early returns (deep-nesting). Rule: python-coding's python-early-return.
17. Verbs match behavior: `get` is cheap and pure, `fetch` and `load` do I/O, `add` mutates a collection, `create` returns the new thing (misleading-verb). Rule: `design-name-for-intent`.
18. Every signature is fully type-hinted, private helpers included, and every path returns the same type. Rule: python-coding's python-typing.
19. Gathering input, computing and presenting live in separate functions; no `print` or `input` inside business logic. Rule: python-coding's python-pure-core.

## Names

20. Names state the role, not the type (type-in-name). Rule: `design-name-for-intent`.
21. No vague public names, cryptic abbreviations or stray single letters (vague-name). Rule: python-coding's python-meaningful-names.
22. No builtin names reused for locals or parameters (shadowed-builtin). Rule: python-coding's python-idioms.
23. Sibling classes use the same method names and signatures for the same job, or the matching dunder (asymmetric-names). Rule: `design-name-for-intent`.
24. Literals with a meaning are named constants (magic-number). Rule: python-coding's python-data-shapes.

## Classes and cohesion

25. Each module, class and function has one reason to change. Rule: `design-single-responsibility`.
26. Each class's methods share its state; no class splits into unrelated clusters, LCOM4 = 1 (low-cohesion-class). Rule: `design-split-god-class`.
27. No class consists only of staticmethods (namespace-class). Rule: `design-lightest-construct`.
28. Instance methods use `self`, unless they override a base method or satisfy an interface (method-could-be-function). Rule: `design-lightest-construct`.
29. No class wraps a single stateless method that should be a function (single-method-class). Rule: `design-lightest-construct`.
30. Logic sits with the data it reads; no function interrogates another object's fields to decide for it (feature-envy). Rule: `design-tell-dont-ask`.
31. No subclass exists only to pass different constants (value-only-subclass). Rule: `design-composition-over-inheritance`.
32. Hierarchies are shallow; behavior is reused by composition, and mixins never depend on host attributes (inheritance-for-reuse). Rule: `design-composition-over-inheritance`.
33. Type-dependent behavior lives on the types or in a dispatch table, not in an isinstance ladder (isinstance-ladder). Rule: `design-open-closed`.

## Coupling and construction

34. I/O collaborators are passed in, never built inside `__init__` or business functions (hard-wired-collaborator). Rule: python-coding's python-dependency-injection.
35. Concrete implementations are chosen in one composition root per entry point. Rule: python-architecture's arch-composition-root.
36. Abstractions are `Callable` aliases or small Protocols owned by the consumer; an ABC appears where shared implementation, enforced overrides or a documented extension point justify it, and a working ABC hierarchy stays. Rule: `design-dependency-inversion`.
37. No reaching through chains of other objects' attributes (attribute-chain). Rule: `design-tell-dont-ask`.
38. No access to another object's private attributes (private-access). Rule: `design-tell-dont-ask`.
39. No `global` rebinding; state is passed and returned (module-level-mutable-global-rebound). Rule: `design-low-coupling`; shared clients and configuration are python-coding's python-no-global-singletons.
40. Every object is usable as soon as it is constructed (two-step-initialization). Rule: `design-complete-construction`.
41. `__new__` never returns a different class (polymorphic-new). Rule: `design-complete-construction`.
42. Imports are explicit, and modules import without side effects such as connecting or registering (wildcard-import). Rule: python-coding's python-imports.
43. Imports point inward and form no cycle. Rule: python-architecture's arch-dependency-direction and arch-break-import-cycles.

## Errors and idioms

44. No bare `except` (bare-except). Rule: python-coding's python-error-handling.
45. No `except Exception` that only passes or continues; broad catches clean up and re-raise (swallowed-exception). Rule: python-coding's python-error-handling.
46. Wrapped exceptions keep their cause with `raise ... from exc`, and domain failures raise the project's own exception types. Rule: python-coding's python-error-handling and python-custom-exceptions.
47. Every releasable resource is held in a `with` block (missing-with). Rule: python-coding's python-context-managers.
48. Decorators use `functools.wraps` (missing-wraps). Rule: python-coding's python-decorators.
49. Every `match` ends in a raising fallback or `assert_never` (match-without-fallback). Rule: python-coding's python-match-fallback.
50. No `lru_cache` or `cache` on instance methods (method-cache). Rule: python-coding's python-properties.
51. Timestamps are timezone-aware UTC, and domain code receives the clock (naive-datetime). Rule: python-coding's python-pure-core.
52. Outbound calls have explicit timeouts; retries are bounded and limited to transient errors on idempotent calls. Rule: python-coding's python-retries-and-timeouts.

## Patterns and restraint

53. Each pattern in use solves a present problem and is in its lightest workable form; the pattern table in this skill's SKILL.md gives the signal and the lighter form. Rule: `design-pattern-from-smell`.
54. An if/elif that picks an algorithm takes a function instead, and one that maps a key to a constructor is a mapping. Rule: `design-strategy` and `design-dispatch-table`.
55. A function that ends by calling several side-effect systems publishes an event instead. Rule: `design-domain-events`.
56. Each piece of knowledge has one home, and nothing exists for a need nobody stated. Rule: `design-dry-yagni-kiss`.
57. No abstraction with one implementation, no test double and no second variant in sight (speculative-abstraction). Rule: `design-pattern-from-smell`.
58. Documented extension points, framework bases and override contracts are left as they are. Rule: `design-review-by-severity`.
