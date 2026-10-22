# Rule neighbors: which rule owns this

Some rules here border a rule of the python-coding or python-architecture skill, and some principle rules here look alike. This guide answers one question, "which rule owns this?", so each finding cites the right rule and each fix follows one home.

## Contents

- How to use this guide
- Shared with python-coding
- Shared with python-architecture
- Look-alike principle rules here

## How to use this guide

Find the situation in a table, then open both named rules: each owns only the part its column names. This guide only separates neighbors. Choosing a pattern from a signal in the code is the pattern table in this skill's SKILL.md. Which data shape to pick is choosing-a-data-shape.md in the python-coding skill, and which package code belongs in is where-code-goes.md in the python-architecture skill.

## Shared with python-coding

| Situation | Rule here and the part it owns | python-coding rule and the part it owns |
| --- | --- | --- |
| One shared instance: a client, a pool, settings | design-singleton: build it once in the entry point and pass it down; a bounded pool | python-coding's python-no-global-singletons: no module-level instance, lazy global or locator |
| Module state rebound by several functions | design-low-coupling: replace the shared global with values passed in and returned | python-coding's python-no-global-singletons: shared clients and configuration |
| A domain value with rules, such as money or a rate | design-value-objects: when a value deserves its own validated type | python-coding's python-frozen-dataclasses: how to freeze it, tuple fields, copying input |
| Fields with a shared prefix, parallel lists, a long signature | design-start-with-the-data: that a record is missing | python-coding's python-data-shapes: how the record is shaped once it exists |
| A function needs configuration and runtime arguments | design-function-builder: a builder that returns the configured function | python-coding's python-closures-and-partial: fitting a function to a narrower signature |
| An existing function has the wrong parameters for a seam | design-function-wrapper: a small translating function | python-coding's python-decorators: cross-cutting wrapping such as timing or logging |
| An expensive value that only some paths need | design-lazy-loading: load on first use, cache once, stream large data | python-coding's python-properties: no lru_cache on a method |
| A collaborator passed into a class or function | design-dependency-inversion: typing it as an abstraction its consumer owns | python-coding's python-dependency-injection and python-protocols: passing it in; Callable, Protocol or ABC |
| A caller reads an object's fields and decides for it | design-tell-dont-ask: moving the behavior to the owner of the data | python-coding's python-hide-internal-state: underscored storage behind methods |
| An if/elif over kinds of things | design-open-closed: an open set of variants, added by adding | python-coding's python-enums and python-match-fallback: a closed set matched once |
| A function with a boolean flag, or I/O inside a model | design-single-responsibility: one reason to change per unit | python-coding's python-function-signatures and python-pure-core: splitting the flag; effects in the shell |
| A wrapper around a third-party client | design-adapter: fitting its shape to your interface and translating its errors | python-coding's python-retries-and-timeouts: timeouts and bounded retries |
| A vague or misleading name | design-name-for-intent: sibling symmetry and verbs that match behavior | python-coding's python-meaningful-names: names a search finds |
| A class with one method and no state | design-lightest-construct: a function before a class | python-coding's python-small-units: how long that function may grow |
| Choosing a dataclass, a plain class or a dict for a record | design-lightest-construct: which construct, function, module, dataclass or class, the code needs | python-coding's python-data-shapes: how the record is shaped once that construct is chosen |

## Shared with python-architecture

| Situation | Rule here and the part it owns | python-architecture rule and the part it owns |
| --- | --- | --- |
| Deciding who creates an object | design-grasp-responsibilities: creator, a unit builds what it contains | python-architecture's arch-composition-root: where I/O implementations are built |
| A handler for an HTTP request or CLI command | design-grasp-responsibilities: the controller principle, a thin handler | python-architecture's arch-use-case-functions: the handler calls one use case |
| An abstraction at a layer boundary | design-dependency-inversion: the consumer owns a small abstraction | python-architecture's arch-ports: which collaborator gets a port |
| One entry point over a subsystem's call sequence | design-facade: hiding a subsystem behind a few operations | python-architecture's arch-use-case-functions: an application operation |
| Side effects after a core action | design-domain-events: an in-process dispatcher keyed by event class | python-architecture's arch-effects-after-commit: effects only after the commit |
| Plugins registered at startup | design-plugin-loading: explicit register calls and an allow-list | python-architecture's arch-composition-root: the entry point that makes the calls |
| Persistence kept off a domain object | design-grasp-responsibilities: pure fabrication, as a principle | python-architecture's arch-repository-port and arch-unit-of-work: the patterns |
| Behavior placed on domain objects | design-tell-dont-ask: behavior beside the data it reads | python-architecture's arch-rich-domain-model: rules on frozen domain types, no I/O |
| Two modules that import each other | design-low-coupling: how much one unit knows of another | python-architecture's arch-break-import-cycles: fixing the import edge |

## Look-alike principle rules here

| The question that separates them | Rule |
| --- | --- |
| Does the unit mix two jobs, and should it split at all? | design-single-responsibility |
| How do I split a class whose methods cluster around disjoint attributes? | design-split-god-class |
| Is a subclass reusing code rather than being a true subtype? | design-composition-over-inheritance |
| Does a subtype keep its base's contract? | design-liskov-substitution |
| Is the interface wider than what one consumer calls? | design-interface-segregation |
| Who owns the abstraction, and does the consumer import the implementation? | design-dependency-inversion |
| Does adding a variant force edits to existing code? | design-open-closed |
| Where should this behavior live: with the data it reads? | design-tell-dont-ask |
| How much must one unit know about another? | design-low-coupling |
| Who creates an object, handles an event, or holds a responsibility no domain object owns? | design-grasp-responsibilities |
| Is this knowledge written twice, or this structure built for a need nobody stated? | design-dry-yagni-kiss |
| Which construct: function, module, dataclass or class? | design-lightest-construct |
| Is a pattern answering a smell visible in today's code? | design-pattern-from-smell |
