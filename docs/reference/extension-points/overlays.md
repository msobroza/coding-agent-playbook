# Overlays

An overlay is an organization's package that adds a layer on top of core: rules,
prompts, skills, eval samples and hooks, laid out like the engine's
`catalog/core/`. A later layer wins over an earlier one by id.

## Ship one

1. Put the content under `<package>/resources/`, in the kind directories
   `rules/`, `prompts/`, `skills/`, `eval_samples/` and `hooks/`.
2. Install the package next to the engine in the consumer repo.
3. List the package's import name in the consumer config's top-level
   `overlays_enabled`:

```toml
# .coding-agent-playbook.toml
overlays_enabled = ["playbook_rules_acme"]
```

Code an overlay ships, such as a hook handler, goes through the other
[extension points](index.md). `playbook validate` run in an overlay's own checkout,
which has no consumer config, checks the checkout's `src/<package>/resources/`.

## The entry-point group

The `coding_agent_playbook.overlays` group is declared, but the engine does not read
it: an overlay is found by its package name in `overlays_enabled`, and its
`resources/` is read through `importlib.resources`.
