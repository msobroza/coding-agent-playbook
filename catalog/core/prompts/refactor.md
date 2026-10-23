---
id: refactor
name: Refactor
description: Refactor the provided code — improve clarity without changing behavior.
slash: refactor
version: 1
includes_rules:
  - python-typing
  - python-error-handling
  - python-dependency-injection
  - python-pure-core
eval_samples:
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
2. **Find the tests.** A refactor without tests is a rewrite. If no tests exist for the affected surface, write characterization tests BEFORE refactoring: tests that pin what the code does today, odd outputs included, not what you think it should do. If they expose a likely bug, keep the current behavior pinned and mention the bug in your report; fixing it is a separate change. These pre-refactor tests are the safety net.
3. **Run the tests.** Confirm green BEFORE making any changes. If they were red before you started, stop and tell the user; do not refactor on top of a broken baseline.
4. **Take small steps.** One refactoring move per commit, where "one move" is an extraction, a rename, an inlining, a type narrowing, or a split. When several smells compete, start with the one that hurts most, usually the one that blocks testing. Run the tests after each move. Resist the temptation to chain three moves into one diff.
5. **Re-read the final diff.** Before declaring done, read your own diff as a reviewer would. If a hunk's purpose is not obvious in five seconds, either re-write its commit message or undo it.
6. **Run the tests again.** Green at the end is the only acceptable outcome. If a test now fails, the refactor was not behavior-preserving — back out the offending step.

## Common refactoring moves

- **Extract function.** Pull a logical chunk into a named helper. Choose a name that says *what* the helper computes, not *how*.
- **Rename for clarity.** If a variable's current name needs a comment to be understood, the name is wrong. Rename it; delete the comment.
- **Replace conditional with early return.** Deeply nested `if`/`else` usually wants to be a series of guard clauses.
- **Replace magic value with named constant.** `42` becomes `MAX_RETRIES`. The constant lives next to its consumers, not in a distant `constants.py`.
- **Tighten type hints.** Where a parameter was `Any` or untyped, narrow it to the actual accepted type. This often surfaces dead branches you can then delete.

## Design moves

Use these when the user asks to decouple, untangle or make code testable, and only for the smell in front of you. A move that changes a signature is still a refactor when every caller is updated in the same change. If an existing test or code outside the repo calls the old signature, keep that entry point as a thin wrapper that wires the production dependencies and delegates; never edit the test to fit.

- **Inject a dependency.** A collaborator built inside a class or function, a singleton, or a hidden config lookup becomes a parameter. Update every caller and the composition root (the one place that builds concrete objects) in the same step.
- **Break an import cycle** by moving the shared type into a lower module or depending on a `Protocol`. A function-local import only hides the cycle.
- **Move behavior to its data.** A method that mostly reads another object's fields belongs on that object. Replace `a.b.c.method()` chains and reach-ins to another class's `_private` attributes with a method on the direct collaborator.
- **Split I/O from logic.** Extract the computation into a pure function that takes values and returns values; leave file, network, printing, clock and randomness calls in a thin shell that calls it.
- **Turn a stateless one-method class into a function.**
- **Replace a flag parameter.** When a `bool` selects between two behaviors, split it into two named functions; when it only tweaks one, make it keyword-only. Parameters that always travel together become one parameter object named for the domain concept.
- **Dispatch from a table, not a growing chain.** An `if`/`elif` chain mapping a key to a value or function becomes a dict, keyed by an `Enum` when the set is closed. An `isinstance` chain becomes `match` with a fallback case that raises. A subclass that differs only in constants becomes configuration of one class.
- **Upgrade the data shape.** Parallel lists become one list of dataclasses; dict records with fixed keys become dataclasses; string constants become an `Enum` that keeps the serialized values; a stored field derived from others becomes a `@property`; a function returning different types by case returns one type, or `T | None`.
- **Swap in the idiom.** Repeated `try`/`finally` cleanup becomes a context manager; a long boolean condition becomes a named predicate; an append-in-a-loop accumulator becomes a comprehension; a recursive re-prompt for input becomes a loop.
- **Translate errors at the boundary.** Gather scattered `except` blocks at the layer edge, where driver, HTTP-client and lookup errors become domain exceptions. Replace a sentinel return (`None`, `-1`) with an exception only when every caller changes in the same diff.

Making sequential `await`s run concurrently changes ordering and failure behavior. That is a behavior change: call it out instead of slipping it into a refactor.

## Decline patterns without a growth signal

A pattern pays for itself only against a concrete growth signal: a variant that is actually being added, a second implementation that exists today, a test that cannot be written without the seam. Without one, decline. A two-arm conditional over a stable choice stays an `if`; a single implementation gets no `Protocol`, registry or strategy hierarchy. If the user asked for such a pattern, leave the code as it is and explain in your report why the pattern does not pay for itself yet.

## What is NOT a refactor

- Changing an API signature in a way callers outside the change notice.
- Adding a new feature, even a "small" one, even one the user "probably wants."
- Touching tests other than to add coverage for code being refactored.
- Re-formatting a file your editor decided to "fix on save." The diff churn buries the actual change.

## Output format

A short report: the moves you made (one bullet each), any pattern you declined and why, any likely bug your characterization tests pinned, the test command you ran, and the test result. If you stopped partway because something looked off, say what and why.
