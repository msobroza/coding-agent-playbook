---
id: python-coding
name: python-coding
description: "Line- and function-level Python conventions."
playbook:
  use_when: "writing, changing or reviewing Python code"
  files: "Any Python file"
  sections:
    - id: errors
      title: "Error handling"
      impact: CRITICAL
      summary: "Catch narrowly, never swallow an exception, derive domain errors from one base and translate them once at the boundary."
      open_when: "Code adds or changes try/except, raise, an exception class, or where a failure becomes an exit code or log line."
    - id: shape
      title: "Code shape"
      impact: HIGH
      summary: "Small units and shallow nesting, so each unit fits in one read."
      open_when: "Writing or growing a function, class or module, adding a nesting level, or a file passing about 300 lines."
    - id: types
      title: "Names, types, docs"
      impact: HIGH
      summary: "Annotate every signature precisely, name callable and identifier types, accept abstract inputs, and document public names with an intent line and a usage example."
      open_when: "Naming a module, class, function or variable, writing a signature or annotation, or a public docstring."
    - id: effects
      title: "Effects and resources"
      impact: HIGH
      summary: "Inject I/O collaborators, keep business logic pure, bind resources to with blocks, and give outbound calls timeouts and bounded retries."
      open_when: "Code opens a file, connection or client, builds SQL, calls a remote service, reads the clock or keeps module state."
    - id: async
      title: "Asyncio"
      impact: HIGH
      summary: "Run independent awaits together, give every task an owner, bound fan-out and total wait, and stream with async generators."
      open_when: "Code adds or changes async def, await, create_task, gather, a TaskGroup, a semaphore or an async for loop."
    - id: pydantic
      title: "Pydantic validation"
      impact: HIGH
      summary: "Validate untrusted data once where it enters, declare constraints in the model, and load configuration into one typed settings object."
      open_when: "Code adds a Pydantic model, Field, validator, serializer or BaseSettings, or parses external JSON or environment config."
    - id: classes
      title: "Classes and data shapes"
      impact: MEDIUM
      summary: "Model records as dataclasses, type seams with small Protocols, prefer attributes and properties to getters, and use Enums for closed sets."
      open_when: "Code declares a dataclass, Protocol, ABC, Enum, property or getter, or uses a dict, long tuple or bare string as a record."
    - id: functions
      title: "Control flow"
      impact: MEDIUM
      summary: "Flatten nesting with guard clauses, end every match with a raising fallback, keep signatures short, and build small callables with partial, closures and decorators."
      open_when: "A function nests ifs over two deep, takes a bool flag or many parameters, or uses match, a decorator, partial or lambda."
    - id: idioms
      title: "Idioms and performance"
      impact: MEDIUM
      summary: "Follow the small house idioms and import conventions, pick collections by their dominant operation, and write comprehensions, generators and str.join where they read best; measure before trading clarity for speed."
      open_when: "Code writes an import statement, a file path, an f-string, a membership test, a dict .get, or a loop that builds a list or string."
---

# Python coding

Line- and function-level conventions for Python code in this repo, including validating untrusted input with Pydantic where the repo uses it. The always-loaded Python house style keeps its rules; each rule in this skill owns one other topic, with its reasons and examples.

## Picking rules

The rules index in this file lists only the rules that apply to this repo, grouped by section, most important first, each with the one line it requires. Open every rule whose line matches the change and read it in full before writing code; most edits need one to three.

- New functions, classes or records: data shapes, typing, docstrings.
- Class design, inheritance, protocols or abstract base classes: classes and protocols.
- Code that touches files, the network, the clock or a database: dependency injection, pure core, context managers, timeouts and retries.
- `async def` code, tasks or anything awaited: asyncio.
- Parsing untrusted input or loading settings into models: Pydantic boundaries.
- Imports, loops over large or hot data, lookups, dict defaults and string building: imports, collection choice, optional keys, comprehensions, generators, string joining.
- Code that raises, catches or logs an exception: error handling.
