---
id: design-plugin-loading
name: Plugin loading
description: "Let other packages add variants through explicit register(registry) calls from the entry point or installed entry points, never by importing module names read from config."
scope: scoped
globs:
  - "**/*.py"
section: common-patterns
priority: 64
tags: [python, design, patterns]
---

# Plugin loading

## Description

Use plugins when other packages or deployments must add variants after the code has shipped (new exporters, new data processors, new integrations) without editing it. Hard-coded imports and an if/elif per type couple the application to every feature it supports. A plugin system combines three parts: a registry that maps a key to a factory, a Protocol every plugin satisfies, and a loader. Keep each part explicit: the entry point builds the registry, each plugin module exposes a `register(registry)` function, and the loader imports only modules it knows.

## Bad Example

```python
# loader.py: module names come straight from config, and importing registers.
def load_plugins(config_path: Path) -> None:
    with config_path.open(encoding="utf-8") as config_file:
        names: list[str] = json.load(config_file)["plugins"]
    for name in names:
        importlib.import_module(name)  # runs whatever module the config names


# plugins/parquet_exporter.py: registers into a global dict as an import side effect.
exporters[ExportFormat.PARQUET] = export_parquet
```

## Good Example

```python
class Exporter(Protocol):
    def export(self, rows: Sequence[ReportRow], target: Path) -> None: ...


class ExporterRegistry:
    def __init__(self) -> None:
        self._exporters: dict[str, Exporter] = {}

    def register(self, name: str, exporter: Exporter) -> None:
        self._exporters[name] = exporter


ALLOWED_PLUGINS: Final[Mapping[str, str]] = {
    "csv": "reports.plugins.csv_exporter",
    "parquet": "reports.plugins.parquet_exporter",
}


def load_plugin(name: str, registry: ExporterRegistry) -> None:
    module_name = ALLOWED_PLUGINS.get(name)
    if module_name is None:
        raise UnknownPluginError(f"plugin {name!r} not allowed; known: {sorted(ALLOWED_PLUGINS)}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise PluginLoadError(f"plugin {name!r} failed to load") from error
    module.register(registry)


def load_installed_plugins(registry: ExporterRegistry) -> None:
    for entry_point in entry_points(group="reports.exporters"):
        try:
            register = entry_point.load()  # each distribution names its register function
        except (ImportError, AttributeError) as error:
            raise PluginLoadError(f"plugin {entry_point.name!r} failed to load") from error
        register(registry)


# main.py: the entry point builds the registry and loads plugins once.
registry = ExporterRegistry()
for plugin_name in settings.plugins:
    load_plugin(plugin_name, registry)
load_installed_plugins(registry)
```

Each plugin module exposes one function, `def register(registry: ExporterRegistry) -> None`, and installed distributions declare it under `[project.entry-points."reports.exporters"]` in their `pyproject.toml`.

## Notes

- Never pass a module name from config or user input to `importlib.import_module` unless it is on an allow-list: importing runs arbitrary code.
- Prefer explicit `register(registry)` calls over registration as an import side effect into a global; the registry the entry point built is the only shared state, and tests build their own.
- A plugin that fails to load raises an error that names it; never skip it with a logged warning, or a missing variant surfaces far from its cause.
- `@runtime_checkable` Protocol checks confirm only that the method names exist, so a plugin with wrong signatures passes them; the type checker on the plugin's `register` function is the real conformance check.
- Not when every variant lives in this repository: a dispatch table is enough, and explicit imports are simpler to trace. Avoid plugins on hot paths and between features that depend on each other.
- Looking up a registered variant, the unknown-key error and validating the config record are `design-dispatch-table`'s; a plugin often supplies a strategy (`design-strategy`) or adapts a vendor API to your Protocol (`design-adapter`).
