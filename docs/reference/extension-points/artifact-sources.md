# Artifact sources

An artifact source is where the engine reads rules, prompts, skills, hooks and eval
samples from. The engine's own, `filesystem`, walks the engine's catalog, the
layers in `overlays_enabled` and the consumer repo's `playbook/` directory.

The engine registers `filesystem` in the `coding_agent_playbook.artifact_sources`
group, but version 1 reads no other source: the commands build the filesystem
source themselves, and `[storage] artifact_source = "filesystem"` is the only
option. The group and the class below are the seam for another source later, such
as a registry behind company authentication.

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.catalog.source.ArtifactSource
   :members:
```
