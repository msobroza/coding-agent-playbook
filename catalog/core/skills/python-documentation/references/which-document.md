# Which document does this change need

Find the row for the situation: it names the file or path to update, the page kind where there is one, and the rule that says how. This page only routes; the rules hold the reasons and the examples.
Rules of another skill are named with their skill in parentheses.
A rule marked "where the repo uses Sphinx", "where the repo uses MkDocs" or "where the repo has a CITATION.cff" applies only there; without it, the row's action still stands on its own.
Never add a docs tool, theme, host, test runner or pre-commit hook to follow a row.

## A code change

| The change | Update in the same change | Rule |
| --- | --- | --- |
| A new or changed public function, class or parameter | Its docstring; where the repo builds an API reference, its registration in that reference | python-docstrings (python-coding); sphinx-api-reference where the repo uses Sphinx, mkdocs-api-reference where the repo uses MkDocs |
| A renamed or removed CLI flag, config key, environment variable or default | Every README section, how-to page and example that shows it, and the changelog input | docs-same-change, docs-changelog |
| A new install step or a new Python floor | The README install section and CONTRIBUTING | docs-readme-essentials, docs-contributing-guide |
| A new, renamed or removed top-level package, entry point or external system | `docs/architecture.md` | docs-architecture-overview |
| A changed dev command, tool or CI job | CONTRIBUTING | docs-contributing-guide |
| An edited example or docstring example | Run it as written, or through the repo's doctest command | docs-runnable-examples |
| A deprecation | A Deprecated changelog entry, with a `DeprecationWarning` in the code | docs-changelog |
| A release | The release heading, or the repo's release tool; the version and date in CITATION.cff | docs-changelog; docs-citation-file where the repo has a CITATION.cff |
| Any docs edit, before committing | `playbook docs-check`, with every finding fixed | docs-check-in-ci |

## A piece of reasoning

| What to record | Where | Rule |
| --- | --- | --- |
| Why a line looks odd | A comment next to it | docs-record-why |
| A hard-to-reverse choice that had a real alternative | `docs/adr/NNNN-slug.md` | docs-record-why, docs-document-layout |
| A domain term | `CONTEXT.md`, or `CONTEXT-MAP.md` when the repo has several contexts | docs-document-layout |
| A spec, design or PRD | `docs/specs/YYYY-MM-DD-<slug>.md` | docs-document-layout |
| A plan and its tickets | `docs/plans/YYYY-MM-DD-<slug>.md` and its `docs/plans/YYYY-MM-DD-<slug>/NN-<ticket>.md` files | docs-document-layout |
| A research finding | `docs/research/<slug>.md` | docs-document-layout |
| Framework setup notes | `docs/agents/` | docs-document-layout |
| A throwaway prototype | `.scratch/`, never committed | docs-document-layout |
| Why the system is shaped this way | `docs/architecture.md` for the map, an explanation page for depth | docs-architecture-overview, docs-page-kinds |
| The why of this change | The commit message | docs-record-why |

## A reader's need

| The reader wants | Page kind | Rule |
| --- | --- | --- |
| To learn from zero | Tutorial | docs-page-kinds |
| To reach one goal | How-to guide | docs-page-kinds |
| To look up an exact signature or option | Reference generated from docstrings | docs-page-kinds; sphinx-api-reference where the repo uses Sphinx, mkdocs-api-reference where the repo uses MkDocs |
| To understand background or trade-offs | Explanation | docs-page-kinds |
| To know what the project is and how to start | The README | docs-readme-essentials, docs-page-kinds |
| To contribute | CONTRIBUTING | docs-contributing-guide, docs-page-kinds |

## Never, whatever the row

- Create a changelog, CONTRIBUTING, CITATION.cff or `docs/architecture.md` unasked: propose it to the user instead.
- Hand-edit a generated changelog section or generated API stubs.
- Rewrite an accepted ADR: a new ADR supersedes it.
- Bypass a failing docs check.
- Commit docs build output.
- Deploy or publish docs inside a change.
