# State sources

A state source is where the consumer config and the lockfile live. The engine's
own, `filesystem`, reads `.coding-agent-playbook.toml`, the local overrides file and
the lockfile in the consumer repo.

The engine registers `filesystem` in the `coding_agent_playbook.state_sources`
group, but version 1 reads no other source: the commands build the filesystem
source themselves, and `[storage] state_source = "filesystem"` is the only option.
The group and the class below are the seam for another source later, such as a
central database of lockfiles.

## The contract

```{eval-rst}
.. autoclass:: coding_agent_playbook.config.files.StateSource
   :members:
```
