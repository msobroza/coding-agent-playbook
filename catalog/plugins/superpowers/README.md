# superpowers (bundled plugin)

A vendored, self-contained port of the Superpowers skills library (MIT,
Copyright (c) 2025 Jesse Vincent; see `LICENSE` and `ATTRIBUTIONS.md` next to
this file).

The plugin ships only `skills/`: one Agent Skills directory per skill
(`SKILL.md` plus optional `scripts/` and `references/`). It has no runtime
dependency on the upstream plugin: cross-references between skills use plain
skill names, every supporting file lives inside its skill directory, and no
body links outside the plugin (SPEC §11.5).

It is layered like an overlay package but ships with the engine, so enabling it
needs no extra install. It is off by default: enable it in a consumer repo, then
run `playbook sync`.

```toml
overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]
```
