---
id: design-lazy-loading
name: Lazy loading
description: "Load an expensive value that only some paths need on first use, cache it once in a cached module function, return it immutable, and stream large data with a generator."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 70
tags: [python, design, patterns]
---

# Lazy loading

## Description

Loading every model, large file or remote catalog at startup wastes time and memory on resources a given run may never use. Load such a value on first use instead, and cache the result so the cost is paid once. In Python the lightest forms are built in: a module-level function decorated with `functools.cache` or `functools.lru_cache` for a process-wide value, and a generator to load data incrementally. A lazy value that is not cached is just slow on every call.

## Bad Example

```python
def get_model() -> Model:
    return Model.load(MODEL_PATH)  # lazy but not cached: reloads on every call


@functools.cache
def get_settings() -> dict[str, str]:
    return {"mode": "batch", "level": "INFO"}


settings = get_settings()
settings["mode"] = "stream"  # mutates the copy every other caller shares
```

## Good Example

```python
@functools.cache
def get_model() -> Model:
    return Model.load(MODEL_PATH)  # loaded on first use, then reused


@dataclass(frozen=True)
class Settings:
    mode: str
    level: str


@functools.cache
def get_settings() -> Settings:
    return Settings(mode="batch", level="INFO")  # immutable, safe to share


@functools.lru_cache(maxsize=256)
def load_tile(tile_id: TileId) -> Tile:  # many distinct inputs: bound the cache
    return Tile.read(tile_path(tile_id))


def read_batches(path: Path, batch_size: int = 1000) -> Iterator[list[Event]]:
    batch: list[Event] = []
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            batch.append(Event.from_json(line))
            if len(batch) >= batch_size:
                yield batch
                batch = []
    if batch:
        yield batch
```

## Notes

- Use it for large datasets, models, optional features and connections that only some paths need.
- `functools.cache` is unbounded; prefer `lru_cache(maxsize=...)` when the inputs have many distinct values.
- Cached values are shared by every caller, so return tuples, frozensets or frozen dataclasses, or return a copy.
- Lazy initialization reached from several threads needs a lock around the first load.
- A generator computes values only as they are consumed: `next(...)` or a `break` stops the work at the first match.
- Not when the value is always needed, is small and fast, or when failing at startup is better than failing on first use.
- Per-instance lazy values with `functools.cached_property`, and why a cache decorator does not belong on a method, are python-properties in the python-coding skill; streaming with generators in general is python-generators there.
