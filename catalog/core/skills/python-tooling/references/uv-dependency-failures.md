# uv: which dependency or lock failure, and which rule fixes it

In a uv project, uv changes the declaration in pyproject.toml, the lock in uv.lock and the environment together. Every dependency change needs the user's agreement first (python-uv-workflow); the rows below route a failure to the uv command and the rule that holds the detail.

Rule ids are given bare and all belong to this skill.

## Lock and sync failures

| What you see | Fix | Rule |
| --- | --- | --- |
| CI's locked sync says the lockfile needs to be updated | pyproject.toml changed without the lock: run `uv lock` with no upgrade flag, then commit both files together | python-uv-workflow |
| A merge conflict in uv.lock | Resolve pyproject.toml, then regenerate the lock with `uv lock`; never hand-merge the lock | python-uv-workflow |
| Code that passes in CI fails locally after a pull | `uv sync` brings the environment back in step with the lock | python-uv-workflow |
| "No solution found when resolving dependencies" after `uv add` | Report uv's explanation and propose a bound; never pin exactly or raise `requires-python` to force it | python-pyproject-dependencies |
| The interpreter does not satisfy `requires-python` or `.python-version` | Ask the user; never edit either file | python-pyproject-dependencies |

## Import and environment failures

| What you see | Fix | Rule |
| --- | --- | --- |
| ModuleNotFoundError from a tool or script run outside the project environment | Run it through `uv run` | python-uv-workflow |
| ModuleNotFoundError for a package the change now imports | Ask, then `uv add`, or `uv add --dev` for a development tool; declare it where python-pyproject-dependencies says, with a lower bound | python-uv-workflow |
| mypy reports missing library stubs | Propose the stub package; once agreed, `uv add --dev` puts it in the dev group (python-pyproject-dependencies) | mypy-type-checking |
| A one-off tool that belongs to no dependency group | `uvx` runs it without adding it | python-uv-workflow |
| `uv` is not found | Stop and ask the user; never run an installer | python-uv-workflow |

## Guard denials and declaration choices

| What you see | Fix | Rule |
| --- | --- | --- |
| The dependency guard denies `pip install`, `uv pip install` or a uv.lock edit | `uv add` or `uv remove`, after the user agreed | python-uv-workflow |
| The dependency guard asks before a new direct dependency | Say why the task needs it; the user decides | python-uv-workflow |
| Where does a new dependency go? | A runtime import goes in `[project].dependencies`; a development, test or lint tool in a dependency group; an optional feature users install in `[project.optional-dependencies]` | python-pyproject-dependencies |
| An exact `==` pin in a library | Use a lower bound; the lock pins the exact version | python-pyproject-dependencies |
| One package needs a newer version | `uv lock --upgrade-package <name>`; upgrade the whole lock only when the user asks | python-uv-workflow |
