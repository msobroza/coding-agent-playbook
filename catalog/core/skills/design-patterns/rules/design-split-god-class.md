---
id: design-split-god-class
name: Split a god class
description: "Split a class whose methods cluster around disjoint attributes into one class per cluster, composed by the original."
scope: scoped
globs:
  - "**/*.py"
section: responsibilities
priority: 42
tags: [python, design, cohesion]
---

# Split a god class

## Description

A god class does everything: unrelated reasons to change collide in one file and one test fixture. Find its natural boundaries by grouping methods by the data they use, name each group, and extract one focused class per group; the original then composes the parts or disappears.

Signs of a god class:

- Its methods cluster into groups that share no attributes and never call each other.
- Its name is joined with "and", or ends in `Manager`.
- It has many instance variables, and prefixed fields (`customer_name`, `customer_email`) signal a missing class.
- Most methods use only a small part of its state.

## Bad Example

```python
class TelescopeController:
    def __init__(self, mount: Mount, smtp: SmtpClient, observer_email: str) -> None:
        self.mount = mount
        self.smtp = smtp
        self.observer_email = observer_email

    def slew(self, target: Coordinates) -> None:  # uses mount
        self.mount.point_at(target)

    def track(self, rate: TrackingRate) -> None:  # uses mount
        self.mount.set_rate(rate)

    def notify_done(self, target: Coordinates) -> None:  # uses smtp, observer_email
        self.smtp.send(to=self.observer_email, body=f"Observed {target}")
```

## Good Example

```python
class MountControl:
    def __init__(self, mount: Mount) -> None:
        self._mount = mount

    def slew(self, target: Coordinates) -> None:
        self._mount.point_at(target)

    def track(self, rate: TrackingRate) -> None:
        self._mount.set_rate(rate)


class ObservationNotifier:
    def __init__(self, smtp: SmtpClient, observer_email: str) -> None:
        self._smtp = smtp
        self._observer_email = observer_email

    def notify_done(self, target: Coordinates) -> None:
        self._smtp.send(to=self._observer_email, body=f"Observed {target}")


class TelescopeSession:  # the slim original composes the parts
    def __init__(self, control: MountControl, notifier: ObservationNotifier) -> None:
        self._control = control
        self._notifier = notifier

    def observe(self, target: Coordinates, rate: TrackingRate) -> None:
        self._control.slew(target)
        self._control.track(rate)
        self._notifier.notify_done(target)
```

## Notes

- Procedure: read the class and its callers; group methods by the attributes they touch and the methods they call; name each group by its responsibility; give each group its own class with only the `__init__` parameters it needs; let the original compose the parts; update the callers and their imports.
- Measure: connect two methods when they share an instance attribute or one calls the other; the number of connected groups is LCOM4. One group is cohesive; two or more are candidate classes. Run this skill's `lcom4_clusters.py` script to list the groups, and open the code at every hit before acting on it: its output is a candidate, not a verdict.
- The script skips Protocol classes and classes with fewer than two methods, leaves stub-only methods, classmethods, staticmethods and dunders such as `__init__` out of the graph, and counts a property read as an attribute access.
- A record with many fields splits the same way: extract each cohesive group of fields into its own small record held by the original.
- Add characterization tests before moving code, so the split changes structure and not behavior.
- No attribute or method count is a hard limit: the clusters, not a number, decide the split.
- Propose the split with each new class and the updated original; apply it only when asked to change code.
- Exceptions: a facade or coordinator is loosely connected by design (keep it thin), and plain data classes with no methods need no measurement.
- Review smell id: low-cohesion-class.
