---
id: python-coding
name: python-coding
description: "Library-agnostic Python conventions."
playbook:
  use_when: "writing, changing or reviewing Python code"
  files: "Any Python file"
---

# Python coding

Library-agnostic conventions for Python code in this repo. The always-loaded Python house style keeps its seven rules; each rule in this skill owns one other topic, with its reasons and examples.

## Picking rules

The rules index in this file lists only the rules that apply to this repo, most important first, each with the one line it requires. Open every rule whose line matches the change and read it in full before writing code; most edits need one to three.

- New functions, classes or records: data shapes, typing, docstrings.
- Class design, inheritance, protocols or abstract base classes: classes and protocols.
- Code that touches files, the network, the clock or a database: dependency injection, pure core, context managers, timeouts and retries.
- `async def` code, tasks or anything awaited: asyncio.
- Loops over large or hot data, lookups and string building: performance idioms.
- Code that raises, catches or logs an exception: error handling.
