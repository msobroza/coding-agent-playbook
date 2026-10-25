---
id: python-str-join
name: String joining
description: "Assemble a string from many parts with str.join, not += in a loop; use an f-string for a fixed handful of pieces."
scope: scoped
globs:
  - "**/*.py"
section: idioms
priority: 78
tags: [python, performance, strings]
---

# Join many parts with str.join

## Description

Strings are immutable, so `result += part` inside a loop builds a new string on every pass and copies everything assembled so far. `"".join(parts)` sizes the result once and copies each part once. It also reads better: the separator and the parts are named in one expression, and there is no trailing separator to trim afterwards.

## Bad Example

```python
def format_tags(tags: list[str]) -> str:
    line = ""
    for tag in tags:
        line += tag + ", "  # a new string every pass
    return line[:-2]  # and a trailing separator to trim


report = ""
for event in events:
    report += f"[{event.time}] {event.message}\n"
```

## Good Example

```python
def format_tags(tags: list[str]) -> str:
    return ", ".join(tags)


report = "\n".join(f"[{event.time}] {event.message}" for event in events)
label = ", ".join(name for name in names if name)  # filter while joining
```

## Notes

- An f-string is the right tool for a fixed handful of pieces: `f"{first} {last}"` beats `" ".join([first, last])`.
- Every part passed to `join` must already be a `str`; convert numbers in the generator (`",".join(str(count) for count in counts)`).
- For bytes, use `b"".join(chunks)`.
- When text is written piece by piece to a file or socket, write each piece to it directly; `io.StringIO` is an alternative when a function needs a file-like target, but `join` is usually enough.
