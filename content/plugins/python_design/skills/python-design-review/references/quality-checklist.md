# Design quality checklist

One numbered list for a quick pass, in the same order as the full review: data first, patterns last. Each item names the smell ids in references/smell-catalog.md that it covers. For a fast review, report findings as "item number, `file:line`, one-line fix", grouped by file, with a count per item at the top.

A "no" is a candidate finding, not an automatic one: confirm it in the code and skip it when there is a stated reason.

## Data shapes

1. Records crossing a function or module boundary are dataclasses, `NamedTuple`s or models, not `dict[str, Any]` (dict-as-record).
2. Values that belong together live in one record, not in parallel lists or dicts (parallel-collections).
3. No group of fields shares a prefix that is really a missing type (prefixed-field-group).
4. Values computable from other fields are properties, not stored copies (stored-derived-value).
5. Closed option sets are `Enum`, `StrEnum` or `Literal`, not bare strings (string-option-set).
6. Money is `Decimal` or integer minor units, never `float` (float-money).
7. Frozen dataclasses hold only immutable fields: `tuple`, `frozenset`, other frozen values (shallow-frozen-dataclass).
8. No method hands out the object's own mutable list or dict (leaked-mutable-internals).
9. Keyed lookups use a dict built once, not a list scan per lookup (list-scan-lookup).
10. Domain values with rules (quantities with units, identifiers, codes) have their own small types where mixing them up would be costly.

## Functions and signatures

11. No mutable default arguments (mutable-default-argument).
12. At most five parameters; related ones are grouped, options are keyword-only (long-parameter-list).
13. No boolean parameter selects between two algorithms (boolean-flag-parameter).
14. Each function does one job and fits on a screen; the house target is well under the scanner's 50-line limit (long-function).
15. Nesting stays at three blocks or fewer, using guard clauses and early returns (deep-nesting).
16. Verbs match behavior: `get` is cheap and pure, `fetch` and `load` do I/O, `add` mutates a collection, `create` returns the new thing (misleading-verb).
17. Gathering input, computing and presenting live in separate functions.
18. Every signature is fully type-hinted, private helpers included.

## Names

19. Names state the role, not the type (type-in-name).
20. No vague public names, cryptic abbreviations or stray single letters (vague-name).
21. No builtin names reused for locals or parameters (shadowed-builtin).
22. Sibling classes use the same method names and signatures for the same job, or the matching dunder (asymmetric-names).

## Classes and cohesion

23. Each class's methods share its state; no class splits into unrelated clusters, LCOM4 = 1 (low-cohesion-class).
24. No class consists only of staticmethods (namespace-class).
25. Instance methods use `self`, unless they override a base method or satisfy an interface (method-could-be-function).
26. No class wraps a single stateless method that should be a function (single-method-class).
27. Logic sits with the data it reads; no function interrogates another object's fields to compute about it (feature-envy).
28. No subclass exists only to pass different constants (value-only-subclass).
29. Hierarchies are shallow; behavior is reused by composition, and mixins never depend on host attributes (inheritance-for-reuse).
30. Type-dependent behavior lives on the types or in a dispatch table, not in an isinstance ladder (isinstance-ladder).

## Coupling and construction

31. I/O collaborators are passed in, never built inside `__init__` or business functions (hard-wired-collaborator).
32. Concrete implementations are chosen in one composition root per entry point.
33. Abstractions are `Callable` aliases or small Protocols owned by the consumer; an ABC appears where shared implementation, enforced overrides or a documented extension point justify it, and a working ABC hierarchy stays.
34. No reaching through chains of other objects' attributes (attribute-chain).
35. No access to another object's private attributes (private-access).
36. No `global` rebinding; state is passed and returned (module-level-mutable-global-rebound).
37. Every object is usable as soon as it is constructed (two-step-initialization).
38. `__new__` never returns a different class (polymorphic-new).
39. Imports are explicit and modules import without side effects such as connecting or registering (wildcard-import).

## Errors and idioms

40. No bare `except` (bare-except).
41. No `except Exception` that only passes or continues; broad catches clean up and re-raise (swallowed-exception).
42. Wrapped exceptions keep their cause with `raise ... from exc`.
43. Every releasable resource is held in a `with` block (missing-with).
44. Decorators use `functools.wraps` (missing-wraps).
45. Every `match` ends in a raising fallback or `assert_never` (match-without-fallback).
46. No `lru_cache` or `cache` on instance methods (method-cache).
47. Timestamps are timezone-aware UTC, and domain code receives the clock (naive-datetime).
48. Outbound calls have explicit timeouts; retries are bounded and limited to transient errors on idempotent calls.

## Patterns and restraint

49. Each pattern in use solves a present problem and is in its lightest workable form (see references/patterns.md).
50. No abstraction with one implementation, no test double and no second variant in sight (speculative-abstraction).
51. Documented extension points, framework bases and override contracts are left as they are.
