---
id: design-facade
name: Facade
description: "When callers repeat the same sequence of calls into a subsystem, put the sequence behind one function or a small facade holding the collaborators it was given, exposing only the operations callers use and no subsystem types."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: specialized-patterns
priority: 87
tags: [python, design, patterns]
---

# Facade

## Description

A facade gives a complex subsystem a few high-level operations, so application code (a UI, a handler, a job) no longer builds connections, formats messages or looks up devices itself. Changes inside the subsystem then touch the facade only, and callers import one module instead of the subsystem's internals. Start with one function that runs the sequence; move to a facade class when several operations share the same collaborators. The facade receives those collaborators; it does not create or register them.

## Bad Example

```python
class SpeakerPanel:
    def __init__(self, service: DeviceService, speaker_id: str) -> None:
        self._service = service
        self._speaker_id = speaker_id

    def toggle(self, *, on: bool) -> None:
        # The panel knows devices, connections and the wire format.
        device = self._service.get_device(self._speaker_id)
        connection = Connection(device.host, device.port)
        message = Message(sender=self._speaker_id, content="on" if on else "off")
        connection.send(message.encode())
```

## Good Example

```python
class DeviceFacade:
    def __init__(self, service: DeviceService, speaker_id: str) -> None:
        self._service = service
        self._speaker_id = speaker_id

    def power_speaker(self, *, on: bool) -> None:
        device = self._service.get_device(self._speaker_id)
        message = Message(sender=self._speaker_id, content="on" if on else "off")
        Connection(device.host, device.port).send(message.encode())

    def device_names(self) -> list[str]:  # plain values, no subsystem types
        return [device.name for device in self._service.devices]


def main() -> None:
    service = DeviceService()
    service.register_device(Speaker(id="speaker-1"))  # setup stays in the entry point
    facade = DeviceFacade(service, speaker_id="speaker-1")
    panel = SpeakerPanel(power_speaker=facade.power_speaker, names=facade.device_names)
    panel.run()
```

`SpeakerPanel.__init__` now takes `power_speaker: Callable[..., None]` and `names: Callable[[], list[str]]` instead of the service and speaker id, so the panel imports nothing from the device subsystem.

## Notes

- Bind a facade to controller functions with bound methods or `functools.partial(power_speaker, facade)`, so the UI gets simple callables.
- A module that exposes a few functions over its internals is already a facade.
- A facade that grows a method for every subsystem feature becomes a god class: keep only the operations callers use, and split it by caller when it grows (design-split-god-class).
- Adapter versus facade: an adapter changes one interface into the shape you expect (design-adapter); a facade makes a large subsystem look small.
- Not when the subsystem is already simple, when callers genuinely need fine-grained control, or when the subsystem's API changes faster than the facade can follow.
