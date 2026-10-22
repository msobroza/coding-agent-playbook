---
id: design-dispatch-table
name: Dispatch table
description: "Replace an if/elif on a key read from config or data with an immutable mapping to callables, looked up by a function that raises a domain error naming the known keys."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 65
tags: [python, design, patterns]
---

# Dispatch table

## Description

Creating objects or picking a handler from config, JSON or user input tends to grow an if/elif chain that ties each type string to a constructor. Every new type edits the chain, and each branch digs its own arguments out of a dict. Since functions are values, map the key to a callable instead: one lookup replaces the chain, a new type is one new entry, and the lookup is the single place that handles an unknown key. Validate the raw config into a typed record first, then call the handler with explicit arguments.

## Bad Example

```python
def build_parsers(config: dict[str, Any]) -> list[Parser]:
    parsers: list[Parser] = []
    for item in config["inputs"]:
        if item["format"] == "csv":
            parsers.append(CsvParser(**item["options"]))
        elif item["format"] == "json":
            parsers.append(JsonParser(**item["options"]))
        elif item["format"] == "xml":
            parsers.append(XmlParser(**item["options"]))
        # an unknown format is silently skipped
    return parsers
```

## Good Example

```python
@dataclass(frozen=True)
class InputSpec:
    format_name: str
    source: Path
    delimiter: str = ","


ParseInput = Callable[[InputSpec], Iterator[Record]]

PARSERS: Final[Mapping[str, ParseInput]] = {
    "csv": parse_csv,
    "json": parse_json,
}


def parser_for(format_name: str) -> ParseInput:
    try:
        return PARSERS[format_name]
    except KeyError:
        raise UnknownFormatError(
            f"unknown format {format_name!r}; known: {sorted(PARSERS)}"
        ) from None


def read_inputs(specs: Sequence[InputSpec]) -> Iterator[Record]:
    for spec in specs:
        yield from parser_for(spec.format_name)(spec)
```

When other modules add keys, the entry point builds a registry object and fills it with explicit calls instead of mutating a module-level dict:

```python
class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, ParseInput] = {}

    def register(self, format_name: str, parse: ParseInput) -> None:
        self._parsers[format_name] = parse
```

## Notes

- A raw lookup raises a bare `KeyError` that reads like a bug; raise a domain error that names the unknown key and lists the known ones, and never fall back to a silent default with `.get(key, default)`.
- Unpacking config with `**options` ties JSON keys to parameter names, so a renamed parameter becomes a runtime `TypeError`; parse the config into a typed record and pass explicit arguments.
- When each key needs its own creation logic, map it to a small creator function (`Callable[[], PaymentProcessor]`) instead of a ready instance.
- Use `functools.singledispatch` when the key is the argument's type rather than a value.
- Not when the keys are a closed `Enum` used in one place: an exhaustive `match` reads better there, and a mapping keyed by the `Enum` itself is `design-open-closed`'s.
- When other packages add the keys, loading them is `design-plugin-loading`; when each value is an algorithm the caller picks, see `design-strategy`.
