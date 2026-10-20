---
status: accepted
---

# Forge CLIs are reached only through `playbook forge`, chosen per call from git config

Agents and users need to act on a repo's forge (open a pull request, read its checks) whether it is GitHub or GitLab. We add one runtime command, `playbook forge <operation>`: on every call it reads the current branch's push remote from git config, maps that remote's host to a forge, and runs the forge's CLI (`gh` or `glab`) with translated arguments, relying on the CLI's own login. It is the only engine code that contacts a forge. Hooks, `sync`, `check`, `validate` and `playbook ci` never do, and the engine never reads or stores a forge token. The engine's own rules and skills, and the vendored skills it amends, name only `playbook forge`, so their text is the same for every forge; vendored content kept byte-faithful (the superpowers plugin) stays as shipped.

## Considered Options

- **Render `gh …` or `glab …` into generated files at sync time.** The text goes stale after `git remote set-url` until the next sync, and every forge-specific passage is written twice.
- **Only report which CLI to use and let the agent write the native command.** Cheap, but the model translates the flags itself, and models know `glab` less well than `gh`.
- **Call the forges' REST APIs from Python.** The engine would handle tokens and duplicate the CLIs' login, host and pagination logic.

## Consequences

- The guards recognise every forge CLI in every repo, whatever forge the repo uses, and recognise `playbook forge` operations that send data (a body file, an implicit push) from the same per-forge tables the command uses.
- "No outbound network by default" still holds: a forge is contacted only when someone runs `playbook forge`.
- `playbook forge` never writes CI secrets or variables. A skill that needs one set guides the human through the forge instead, so no credential value ever passes through the engine.
- `playbook forge` translates and does not decide tracker policy: an operation a forge or its plan lacks (sub-issues, blocking links) exits with a distinct "unsupported" status, and the skill applies its own text fallback.
