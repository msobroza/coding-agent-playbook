---
id: python-tooling
name: python-tooling
description: "Framework and tool wiring conventions for this repo."
playbook:
  use_when: "wiring or reviewing FastAPI apps, routers, dependency providers or error handlers"
  files: "FastAPI apps, routers, dependency providers and error handlers"
---

# Python tooling

Conventions tied to one named framework or developer tool. A reference applies only when the repo uses its framework or tool, so the references index in this file lists just the ones detected here, each with the one line it requires.

## Picking references

Open the reference for each framework or tool the change touches and read it in full before writing code. Library-agnostic conventions stay in the python-coding skill; a reference here adds only what its framework or tool changes.
