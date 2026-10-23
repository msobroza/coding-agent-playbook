# Choosing a data shape

Which type a new value gets, and the rule that shows that shape. This page only routes: the rules hold the examples and the reasons. The Pydantic rows apply when the repository depends on Pydantic; their rules are absent from the skill's index otherwise.

## Questions in order

Stop at the first yes.

1. Does the value come from outside the process (a request body, a message, a file, the environment)? Parse it with a Pydantic model where it enters (pydantic-boundaries), and configuration with one settings object (pydantic-typed-settings). Without Pydantic, use a dataclass that checks its fields in `__post_init__` (python-dataclass-post-init) and translate its error at the boundary (python-error-boundaries).
2. Is it one of a closed set of options? An `Enum`, or a `Literal` in a signature (python-enums).
3. Is it an identifier that must never be mixed with another of the same base type? A `NewType` (python-type-aliases). When it also needs validation, a small value object: design-value-objects in the design-patterns skill.
4. Is it behavior rather than data? A role-named `Callable` alias for one behavior (python-type-aliases), a small `Protocol` for several (python-protocols).
5. Is it two or three values returned together? A tuple. More than three: a `NamedTuple` or a dataclass (python-data-shapes).
6. Must it stay a dict because a library takes or returns one? A `TypedDict` at that edge only (python-data-shapes); read its absent keys as python-optional-keys says.
7. Otherwise: a dataclass (python-data-shapes), frozen when nothing changes it after creation (python-frozen-dataclasses).

## Shapes

| Shape | For | Not for | Rule |
| --- | --- | --- | --- |
| dataclass | a record of named fields | a dict of strings or parallel lists | python-data-shapes |
| frozen dataclass with tuple and frozenset fields | value records, dict keys, data shared across threads | records that change in place | python-frozen-dataclasses |
| dataclass with `__post_init__` | records whose fields need checks or normalizing | storing derived values | python-dataclass-post-init |
| tuple | at most three values returned together | anything read by position past three | python-data-shapes |
| `NamedTuple` | a small immutable record that unpacks like a tuple | a record that grows fields | python-data-shapes |
| `TypedDict` | a dict a library requires, at that edge | a record passed further inward | python-data-shapes |
| Pydantic `BaseModel` | untrusted input, validated once where it enters | internal records after that point | pydantic-boundaries |
| `BaseSettings` | all configuration, loaded once at startup | values read from the environment anywhere else | pydantic-typed-settings |
| `Enum` or `Literal` | a closed set of options | bare string constants | python-enums |
| `NewType` | identifiers that must never be mixed | values that need runtime validation | python-type-aliases |
| class with underscored state | an object that protects an invariant | a plain record | python-hide-internal-state |
| `Protocol` or `Callable` alias | a seam typed by behavior | data | python-protocols, python-type-aliases |

## Inside a Pydantic model

| Need | Rule |
| --- | --- |
| Limits on one field (length, range, pattern) | pydantic-field-constraints |
| Checks across several fields | pydantic-model-validators |
| Secrets, URLs, emails, positive counts, money | pydantic-special-types |
| The output format on the wire | pydantic-serializers |

## Fields and derived values

- A list or dict default: `field(default_factory=...)`, never a shared literal (python-data-shapes).
- A value derived from other fields: a `@property`, not a stored copy (python-dataclass-post-init, python-properties).
- Read access to protected state: a property over an underscored field (python-properties, python-hide-internal-state).
- Many small instances of one record: the slots option python-data-shapes shows.
- A collection field of a frozen record: a tuple or frozenset copied at construction (python-frozen-dataclasses).
- Decoded JSON whose shape varies: dispatch on its shape with `match` (python-match-destructuring).
- Money: `Decimal`, never `float`, as the house style says; in a Pydantic model see pydantic-special-types.

## Owned by other skills

- Request and response schemas of a web API: web-api-schemas in the web-application skill.
- Typed records that cross architecture layers: arch-typed-records-across-layers in the python-architecture skill.
- The lightest construct for a design (function, dataclass, class or pattern): design-lightest-construct in the design-patterns skill.
- Numeric arrays and data frames: the ml-data skill.

Related guides: python-version-idioms.md, error-flow.md.
