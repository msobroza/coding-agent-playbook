---
id: design-adapter
name: Adapter
description: "Wrap a third-party API whose shape does not fit your code in a function or a composing class that implements your interface; never subclass the vendor class."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 67
tags: [python, design, patterns]
---

# Adapter

## Description

Your code expects one interface (`get(key) -> str | None`) and an existing library or legacy system offers another (`client.fetch_entry(key).text`). Calling the vendor API directly couples every caller to it, and its types and exceptions leak into business code. An adapter translates one shape into the other while the complexity stays the same. When one call needs adapting, a function bound with `functools.partial` is enough; when several methods do, write a class that holds the vendor object (composition) and implements your Protocol.

## Bad Example

```python
class SettingsAdapter(VendorConfigClient):  # inherits the vendor class
    def get(self, key: str, default: str | None = None) -> str | None:
        entry = self.fetch_entry(key)
        return entry.text if entry is not None else default
```

`VendorConfigClient` may already have a `get` with other semantics: the override breaks every caller that expects the original, and the adapter exposes the whole vendor interface next to yours.

## Good Example

```python
class Settings(Protocol):
    def get(self, key: str, default: str | None = None) -> str | None: ...


class VendorSettings:  # holds the vendor client and implements Settings
    def __init__(self, client: VendorConfigClient) -> None:
        self._client = client

    def get(self, key: str, default: str | None = None) -> str | None:
        try:
            entry = self._client.fetch_entry(key)
        except VendorConnectionError as error:
            raise SettingsUnavailableError(key) from error
        return entry.text if entry is not None else default


experiment = Experiment(settings=VendorSettings(client))
```

With one method to adapt, a function and `partial` replace the class:

```python
SettingGetter = Callable[[str], str | None]


def get_from_vendor(client: VendorConfigClient, key: str) -> str | None:
    entry = client.fetch_entry(key)
    return entry.text if entry is not None else None


experiment = Experiment(get_setting=partial(get_from_vendor, client))
experiment = Experiment(get_setting=loaded_settings.get)  # a dict already fits
```

## Notes

- Wrap, do not subclass, a class you do not own: composition keeps the adapter's and the adaptee's interfaces apart.
- Translate vendor exceptions into your own at the adapter, so business code never catches a vendor type.
- Outbound calls get explicit timeouts there, and only idempotent calls a small, bounded retry on transient errors: see python-retries-and-timeouts in the python-coding skill.
- Designing against your own interface pays off when a source already fits it: a `dict` satisfies `Settings` and `dict.get` satisfies `SettingGetter`, with no adapter code.
- Not when both sides are your own code: change one of them instead. Translating the arguments of one of your own functions to fit a seam is design-function-wrapper.
- A facade simplifies a complex subsystem behind fewer calls; an adapter only changes the shape. A bridge separates two dimensions that vary independently.
