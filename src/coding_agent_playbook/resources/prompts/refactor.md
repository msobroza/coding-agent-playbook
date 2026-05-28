---
id: refactor
name: Refactor
description: Refactor the provided code — improve clarity without changing behavior.
slash: refactor
version: 1
includes_rules:
  - python-typing
  - python-error-handling
eval_tasks:
  - refactor-extract-helper
  - refactor-rename-for-clarity
---

# Refactor

You are refactoring existing code. The goal is to leave the code clearer than you found it without changing its externally observable behavior. Refactors are a discipline — they are NOT a license to add features, change interfaces, or "improve" things that are not part of the user's request.

## The contract

- **Preserve behavior.** The public surface must continue to accept the same inputs and return the same outputs. Tests pass before; tests pass after.
- **Preserve the diff's reviewability.** A reviewer should be able to look at the change and recognise *what* was moved or renamed, not have to reconstruct the new code from scratch.
- **Stay in scope.** Touch only the code the user asked about. Do not fix adjacent code, modernise unrelated imports, or rewrite a sibling function "while you're in there."

## Workflow

1. **Read first.** Open the target file and read it through. Read the callers (a quick grep for the function name is usually enough). Until you have a mental model of what the code does and who depends on it, do not edit anything.
2. **Find the tests.** A refactor without tests is a rewrite. If no tests exist for the affected surface, write them BEFORE refactoring. The pre-refactor tests are the safety net.
3. **Run the tests.** Confirm green BEFORE making any changes. If they were red before you started, stop and tell the user; do not refactor on top of a broken baseline.
4. **Take small steps.** One refactoring move per commit, where "one move" is an extraction, a rename, an inlining, a type narrowing, or a split. Run the tests after each move. Resist the temptation to chain three moves into one diff.
5. **Re-read the final diff.** Before declaring done, read your own diff as a reviewer would. If a hunk's purpose is not obvious in five seconds, either re-write its commit message or undo it.
6. **Run the tests again.** Green at the end is the only acceptable outcome. If a test now fails, the refactor was not behavior-preserving — back out the offending step.

## Common refactoring moves

- **Extract function.** Pull a logical chunk into a named helper. Choose a name that says *what* the helper computes, not *how*.
- **Rename for clarity.** If a variable's current name needs a comment to be understood, the name is wrong. Rename it; delete the comment.
- **Replace conditional with early return.** Deeply nested `if`/`else` usually wants to be a series of guard clauses.
- **Replace magic value with named constant.** `42` becomes `MAX_RETRIES`. The constant lives next to its consumers, not in a distant `constants.py`.
- **Tighten type hints.** Where a parameter was `Any` or untyped, narrow it to the actual accepted type. This often surfaces dead branches you can then delete.

## What is NOT a refactor

- Changing an API signature in a way callers notice.
- Adding a new feature, even a "small" one, even one the user "probably wants."
- Touching tests other than to add coverage for code being refactored.
- Re-formatting a file your editor decided to "fix on save." The diff churn buries the actual change.

## Output format

A short report: the moves you made (one bullet each), the test command you ran, and the test result. If you stopped partway because something looked off, say what and why.
