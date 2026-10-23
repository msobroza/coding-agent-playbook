# Principles: cohesion, coupling, GRASP and SOLID

Use these principles to explain a finding and to decide where code should live. They apply to functions and modules as much as to classes, which matters in Python, where much good design involves no class at all. Treat each one as a lens with known exceptions, not as a law, and name the principle in a finding only when it explains the concrete cost. Each section names the rules of this skill that apply it.

## Contents

- Seven principles, as review questions
- Cohesion
- Coupling
- GRASP: who gets which responsibility
- SOLID, read through Python
- GRASP and SOLID side by side
- Related heuristics

## Seven principles, as review questions

Apply them in this order of priority; for each module, class and function, ask:

1. High cohesion: does each unit have one job? Extract a class when a class does two things, a function when a function does. Rules: `design-single-responsibility`, `design-split-god-class`.
2. Low coupling: are dependencies minimal, and does each method talk only to near collaborators? Move behavior to the unit that owns the data, and pass only what a function needs. Rules: `design-low-coupling`, `design-tell-dont-ask`.
3. Depend on abstractions: is a volatile collaborator typed as a role-named `Callable` alias or a small `Protocol`, rather than imported as a concrete class? Patterns follow from removing coupling. Rules: `design-dependency-inversion`, `design-interface-segregation`.
4. Composition over inheritance: is behavior reused by holding a collaborator, with inheritance kept for real substitution? Rules: `design-composition-over-inheritance`, `design-liskov-substitution`.
5. Separate creation from use: is each object built in one place, with a mapping instead of an if/elif that picks a constructor? Rules: `design-grasp-responsibilities` (creator), `design-dispatch-table`; the composition root itself is python-architecture's arch-composition-root.
6. Start with the data: are there prefixed fields, parallel lists, or methods far from their data? Rule: `design-start-with-the-data`.
7. Keep things simple: is anything over-built, speculative, or a second home for one piece of knowledge? Rules: `design-dry-yagni-kiss`, `design-lightest-construct`, `design-pattern-from-smell`.

## Cohesion

A unit is cohesive when everything in it serves one purpose and changes for one reason. Rules: `design-single-responsibility`, `design-split-god-class`.

- Measure: for a class, connect two methods when they share an instance attribute or one calls the other. The number of connected groups is LCOM4. One group is cohesive; two or more are candidate classes, which lcom4_clusters.py prints.
- Signs: a name joined with "and" or ending in `Manager`; a module that mixes parsing, business rules and printing; a test fixture that must build things the test never touches.
- Fix: split along the groups, then let the old name compose the parts or disappear.
- Exceptions: a facade or coordinator has low cohesion by design, because its job is to sequence others; keep it thin rather than splitting it. Plain data classes with no methods are trivially cohesive and need no measurement.

## Coupling

Coupling is how much one unit must know about another to work. From tightest to loosest:

1. Content: writing another object's internals (`station._buffer.clear()`).
2. Shared mutable global: several functions read and rebind the same module state.
3. External shape: a third-party API's types and calls spread through business code.
4. Control: a flag argument steers which branch the callee runs.
5. Stamp: a whole record is passed when one field is used.
6. Data: plain values passed as parameters.
7. Message: a published event the sender does not track.

Removing one form often introduces another. Replacing three config globals with seven parameters trades global coupling for a noisy signature; grouping those parameters into a small settings record passed in by the entry point is usually the balanced end point. Stamp coupling is often the clearer choice when the callee is conceptually about the record: do not shred a cohesive record into loose arguments just to rank lower. Rules: `design-low-coupling`; the forms at the loose end are `design-adapter` (external shape) and `design-domain-events` (message).

## GRASP: who gets which responsibility

GRASP (General Responsibility Assignment Software Patterns) is nine principles from responsibility-driven design that answer "where does this behavior belong?". SOLID is strongly object-oriented: Liskov substitution only matters once there is inheritance. GRASP's cohesion, coupling and expert apply to functions, modules and classes alike, which fits Python's mix of procedural, functional and object-oriented code.

- Information expert: give a responsibility to the unit that holds the data it needs. A `Harvest` that owns its crates computes `total_weight_kg()`; callers do not sum crate weights themselves. Exception: when the computation also needs outside rules (seasonal prices, regional tax), a separate function that receives the harvest and the rules keeps the record from growing into a god class. Rule: `design-tell-dont-ask`.
- Creator: let a unit create the objects it contains, records or uses closely, or the ones it has the initializing data for. `Harvest.add_crate(variety, weight_kg)` builds the `Crate`, so callers need not know its constructor. Exception: business objects never create collaborators that do I/O; the entry point builds them and passes them in. Rule: `design-grasp-responsibilities`.
- Controller: route a system event (an HTTP request, a CLI command, a queue message) to a thin handler that parses input, calls one operation, and maps the result or error back. It holds no business rules, and the domain never imports the delivery framework. Rule: `design-grasp-responsibilities`; the handler's place among the layers is python-architecture's arch-use-case-functions.
- Low coupling and high cohesion: these two judge every other choice. An assignment that raises coupling or splits a purpose across files needs a reason. Rules: `design-low-coupling`, `design-single-responsibility`.
- Polymorphism: when behavior varies by kind, let each kind carry its own behavior instead of testing kinds at the call site. The lightest carrier is a function: pass `price_rule: Callable[[Decimal], Decimal]` instead of switching on a `kind` string. Use methods behind a Protocol when each kind has several related behaviors. Exception: a closed `Enum` matched once, with an exhaustive `match`, is clearer than a class per member. Rules: `design-open-closed`, `design-strategy`.
- Indirection: put an intermediate between two units that should not know each other. A `Discount` value computed from a customer's history decouples order pricing from customer records; an adapter decouples your code from a vendor SDK. Every indirection costs the reader a hop, so add it only where it cuts a real dependency. Rule: `design-grasp-responsibilities`.
- Protected variations: place a stable interface at a point you expect to change, such as a payment provider, a storage engine or a message transport. Exception: speculative variation; without a second implementation, a test double or a known roadmap item, the interface is premature. Rule: `design-dependency-inversion`.
- Pure fabrication: when a responsibility belongs to no domain concept, invent a unit for it rather than overloading a domain class. A `ReadingArchive` that writes sensor readings to storage is not a domain noun, but it keeps `Sensor` free of persistence. Dispatchers are fabrications too; repositories and units of work as patterns are the python-architecture skill's. Rule: `design-grasp-responsibilities`.

## SOLID, read through Python

SOLID was written for class hierarchies. Its intent survives in Python, but the idioms differ.

| Principle | Python reading | When it does not apply | Rule |
| --- | --- | --- | --- |
| Single responsibility | One reason to change per function, class and module; split I/O from computation | Short scripts and notebooks; a coordinator whose one job is sequencing | `design-single-responsibility` |
| Open/closed | Add a variant by adding a function, a mapping entry or a registered plugin, not by editing a ladder | A closed enum with an exhaustive `match`: one edit site with type-checker help beats a registry | `design-open-closed` |
| Liskov substitution | Subclasses and Protocol implementers accept the same inputs, return compatible outputs and raise no new error kinds | Not a reason to avoid subclassing; it is the test a subclass must pass | `design-liskov-substitution` |
| Interface segregation | Consumers declare small Protocols with only the methods they call | Do not split a cohesive interface into one-method Protocols for symmetry | `design-interface-segregation` |
| Dependency inversion | Business code depends on `Callable` aliases or Protocols at I/O seams; the composition root picks concrete classes | Pure in-process collaborators can be injected as concrete types; framework types are fine at the edge | `design-dependency-inversion` |

Injection and inversion are different things. Passing a dependency in (injection) already makes code testable. Typing it as an abstraction the consumer owns (inversion) also frees the consumer from the implementation's module. Inject everywhere I/O happens, and add inversion where the implementation is volatile or must be faked.

A Protocol is structural, cheap and owned by the consumer, so it is the default seam. An ABC is the right tool when implementations share code, when missing overrides should fail at instantiation, or when a library documents a base class as its extension point; a working ABC hierarchy does not need converting. `@runtime_checkable` checks only that the method names exist, not their signatures, so an `isinstance` check against a Protocol is no validation. The choice between them is python-coding's python-protocols.

## GRASP and SOLID side by side

| GRASP | Closest SOLID principle | Rule here |
| --- | --- | --- |
| High cohesion | Single responsibility | `design-single-responsibility` |
| Low coupling | Dependency inversion | `design-low-coupling` |
| Polymorphism | Open/closed, Liskov substitution | `design-open-closed` |
| Protected variations | Dependency inversion | `design-dependency-inversion` |
| Information expert | none | `design-tell-dont-ask` |
| Creator | none | `design-grasp-responsibilities` |
| Controller | none (architectural) | `design-grasp-responsibilities` |
| Indirection | none (a design tactic) | `design-grasp-responsibilities` |
| Pure fabrication | none (a design tactic) | `design-grasp-responsibilities` |

The overlap is real, but GRASP gives more practical guidance on placing a responsibility, especially where no class hierarchy is involved.

## Related heuristics

- Tell, do not ask: ask an object to do the thing (`dock.release_bike()`) rather than reading its fields and acting on them (`if dock.bikes_free > 0: dock.bikes_free -= 1`); the object can then guard its own invariants. Rule: `design-tell-dont-ask`.
- Law of Demeter: a method talks to its parameters, its own attributes and objects it creates, not to strangers reached through them. Exceptions: fluent APIs that return the same kind of object, value objects, and data-transfer records whose structure is the contract. Rule: `design-tell-dont-ask`.
- Composition over inheritance: inheritance remains right for framework base classes, exception hierarchies, ABC extension points and genuinely substitutable subtypes; when subclasses differ only in values, use configuration instead. Rule: `design-composition-over-inheritance`.
- Duplicate knowledge, not just code: extract when two copies encode the same rule and must change together. Two snippets that merely look alike may diverge, so wait for a third copy before abstracting them. Rule: `design-dry-yagni-kiss`.
- Least machinery: if the abstractions, factories and wrappers outnumber the lines doing real work, the design is ahead of its requirements. Prefer the version that is easy to change later over the one that anticipates every change now. Rules: `design-dry-yagni-kiss`, `design-pattern-from-smell`.
- Start with the data: most cohesion and coupling problems trace back to a missing or misshapen record. Fix the data shape first, then revisit the functions and classes around it. Rule: `design-start-with-the-data`.
