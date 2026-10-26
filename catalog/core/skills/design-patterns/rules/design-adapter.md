---
id: design-adapter
name: Adapter
description: "Wrap a third-party API whose shape does not fit your code in a function or a composing class that implements your interface; never subclass the vendor class."
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 67
tags: [python, design, patterns]
---

# Adapter

## Description

Your code expects one interface (`get(key) -> str | None`) and an existing library or legacy system offers another (`client.fetch_entry(key).text`). Calling the vendor API directly couples every caller to it, and its types and exceptions leak into business code. An adapter translates one shape into the other while the complexity stays the same. When one call needs adapting, a function that closes over the vendor client is enough; when several methods do, write a class that holds the vendor object (composition) and implements your Protocol.

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

With one method to adapt, a closure typed with your alias replaces the class:

```python
SettingGetter = Callable[[str], str | None]


def vendor_getter(client: VendorConfigClient) -> SettingGetter:
    def get_setting(key: str) -> str | None:
        try:
            entry = client.fetch_entry(key)
        except VendorConnectionError as error:
            raise SettingsUnavailableError(key) from error
        return entry.text if entry is not None else None

    return get_setting


experiment = Experiment(get_setting=vendor_getter(client))
experiment = Experiment(get_setting=loaded_settings.get)  # a dict already fits
```

## Notes

- Wrap, do not subclass, a class you do not own: composition keeps the adapter's and the adaptee's interfaces apart.
- Translate vendor exceptions into your own at the adapter, so business code never catches a vendor type.
- Prefer a closure over `functools.partial` for a typed seam: see `design-strategy` for why `partial` blurs the signature.
- Outbound calls get explicit timeouts there, and only idempotent calls a small, bounded retry on transient errors: see `python-retries-and-timeouts` in the python-coding skill.
- Designing against your own interface pays off when a source already fits it: a `dict` satisfies `Settings` and `dict.get` satisfies `SettingGetter`, with no adapter code.
- Not when both sides are your own code: change one of them instead. Translating the arguments of one of your own functions to fit a seam is `design-function-wrapper`.
- A facade simplifies a complex subsystem behind fewer calls; an adapter only changes the shape. A bridge separates two dimensions that vary independently.
