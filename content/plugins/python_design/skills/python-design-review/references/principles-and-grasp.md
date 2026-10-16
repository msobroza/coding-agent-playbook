# Principles: cohesion, coupling, GRASP and SOLID

Use these principles to explain a finding and to decide where code should live. They apply to functions and modules as much as to classes, which matters in Python, where much good design involves no class at all. Treat each one as a lens with known exceptions, not as a law. Name the principle in a finding only when it explains the concrete cost.

## Cohesion

A unit is cohesive when everything in it serves one purpose and changes for one reason.

- **Measure:** for a class, connect two methods when they share an instance attribute or one calls the other. The number of connected groups is LCOM4. One group is cohesive. Two or more are candidate classes (scripts/lcom4_clusters.py prints the groups when it is present).
- **Signs:** a name joined with "and" or ending in `Manager`; a module that mixes parsing, business rules and printing; a test fixture that must build things the test never touches.
- **Fix:** split along the groups, then let the old name compose the parts or disappear.
- **Exceptions:** a facade or coordinator has low cohesion by design, because its job is to sequence others. Keep it thin rather than splitting it. Plain data classes with no methods are trivially cohesive and need no measurement.

## Coupling

Coupling is how much one unit must know about another to work. From tightest to loosest:

1. **Content:** writing another object's internals (`station._buffer.clear()`).
2. **Shared mutable global:** several functions read and rebind the same module state.
3. **External shape:** a third-party API's types and calls spread through business code.
4. **Control:** a flag argument steers which branch the callee runs.
5. **Stamp:** a whole record is passed when one field is used.
6. **Data:** plain values passed as parameters.
7. **Message:** a published event the sender does not track.

Removing one form often introduces another. Replacing three config globals with seven parameters trades global coupling for a noisy signature, and grouping those parameters into a small settings dataclass passed in by the entry point is usually the balanced end point. Stamp coupling is often the clearer choice when the callee is conceptually "about" the record. Do not shred a cohesive record into loose arguments just to rank lower.

## GRASP: who gets which responsibility

These nine patterns from responsibility-driven design answer "where does this behavior belong?". They fit Python well because they speak about modules and functions as easily as about classes.

**Information expert.** Give a responsibility to the unit that holds the data it needs. A `Harvest` that owns its crates computes `total_weight_kg()`; callers do not sum crate weights themselves. Exception: when the computation also needs outside rules (seasonal prices, regional tax), a separate function that receives the harvest and the rules keeps the record from growing into a god class.

**Creator.** Let a unit create the objects it contains, records or uses closely, or the ones it has the initializing data for. `Harvest.add_crate(variety, weight_kg)` builds the `Crate`, so callers need not know its constructor. Exception: collaborators that do I/O are never created by business objects; the composition root creates them and passes them in.

**Controller.** Route a system event (an HTTP request, a CLI command, a queue message) to a thin handler that translates it and calls the domain. The handler parses input, calls one operation, and maps the result or error back. It holds no business rules, and the domain never imports the delivery framework.

**Low coupling and high cohesion.** These two judge every other choice. A responsibility assignment that raises coupling or splits a purpose across files needs a reason.

**Polymorphism.** When behavior varies by kind, let each kind carry its own behavior instead of testing kinds at the call site. In Python the lightest carrier is a function: pass `price_rule: Callable[[Decimal], Decimal]` instead of switching on a `kind` string. Use methods behind a Protocol when each kind has several related behaviors. Exception: a closed `Enum` matched once, with an exhaustive `match`, is clearer than a class per member.

**Indirection.** Put an intermediate between two units that should not know each other. A `Discount` value computed from a customer's history decouples order pricing from customer records; an adapter decouples your code from a vendor SDK. Every indirection costs a hop for the reader, so add it only where it cuts a real dependency.

**Protected variations.** Place a stable interface at a point you expect to change, such as a payment provider, a storage engine or a message transport. Callers depend on the interface. Exception: speculative variation. Without a second implementation, a test double or a known roadmap item, the interface is premature.

**Pure fabrication.** When a responsibility belongs to no domain concept, invent a unit for it rather than overloading a domain class. `ReadingArchive` that writes sensor readings to storage is not a domain noun, but it keeps `Sensor` free of persistence. Repositories, unit-of-work objects and dispatchers are all fabrications.

## SOLID, read through Python

SOLID was written for class hierarchies. Its intent survives in Python, but the idioms differ.

| Principle | Python reading | When it does not apply |
| --- | --- | --- |
| Single responsibility | One reason to change per function, class and module; split I/O from computation | Short scripts and notebooks; a coordinator whose one job is sequencing |
| Open/closed | Add a variant by adding a function, a dict entry or a registered plugin, not by editing a ladder | A closed enum with an exhaustive `match`: one edit site with type-checker help beats a registry |
| Liskov substitution | Subclasses and Protocol implementers accept the same inputs, return compatible outputs and raise no new error kinds | Not a reason to avoid subclassing; it is the test a subclass must pass |
| Interface segregation | Consumers declare small Protocols with only the methods they call | Do not split a cohesive interface into one-method Protocols for symmetry |
| Dependency inversion | Business code depends on `Callable` aliases or Protocols at I/O seams; the composition root picks concrete classes | Pure in-process collaborators can be injected as concrete types; framework types are fine at the edge |

Injection and inversion are different things. Passing a dependency in (injection) already makes code testable. Typing it as an abstraction the consumer owns (inversion) additionally frees the consumer from the implementation's module. Use injection everywhere I/O happens, and add inversion where the implementation is volatile or must be faked.

On Protocols and ABCs: a Protocol is structural, cheap and owned by the consumer, so it is the default seam. An ABC is the right tool when implementations share code, when missing overrides should fail at instantiation, or when a library documents a base class as its extension point. A working ABC hierarchy does not need converting. `@runtime_checkable` only checks that the method names exist, not their signatures, so do not treat an `isinstance` check against a Protocol as validation.

## Related heuristics

- **Tell, do not ask.** Ask an object to do the thing (`dock.release_bike()`) rather than reading its fields and acting on them (`if dock.bikes_free > 0: dock.bikes_free -= 1`). The object can then guard its own invariants.
- **Law of Demeter.** A method talks to its parameters, its own attributes and objects it creates, not to strangers reached through them. Exceptions: fluent APIs that return the same kind of object, value objects, and data-transfer records whose structure is the contract.
- **Composition over inheritance.** Reuse behavior by holding a collaborator. Inheritance remains right for framework base classes, exception hierarchies, ABC extension points and genuinely substitutable subtypes. When subclasses differ only in values, use configuration instead.
- **Duplicate knowledge, not just code.** Extract when two copies encode the same rule and must change together. Two snippets that merely look alike may diverge, so wait for a third copy before abstracting them.
- **Least machinery.** If the abstractions, factories and wrappers outnumber the lines doing real work, the design is ahead of its requirements. Prefer the version that is easy to change later over the one that anticipates every change now.
- **Start with the data.** Most cohesion and coupling problems trace back to a missing or misshapen record. Fix the data shape first, then revisit the functions and classes around it.
