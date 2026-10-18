---
id: python-coding
name: python-coding
description: "Library-agnostic Python conventions."
playbook:
  use_when: "writing, changing or reviewing Python code"
  files: "Any Python file"
---

# Python coding

Library-agnostic conventions for Python code in this repo. The always-loaded Python house style keeps its eight rules; each reference in this skill owns one other topic, with its reasons and examples.

## Picking references

The references index in this file lists only the references that apply to this repo, most important first, each with the one line it requires. Open every reference whose line matches the change and read it in full before writing code; most edits need one to three.

- New functions, classes or records: data shapes, typing, docstrings.
- Code that touches files, the network, the clock or a database: dependency injection, pure core, context managers, timeouts and retries.
- Code that raises, catches or logs an exception: error handling.
