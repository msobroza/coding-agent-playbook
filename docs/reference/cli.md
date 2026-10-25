# CLI

The engine installs three console scripts. `playbook` and `coding-agent-playbook`
are the same command; `playbook-hook` is the hook runtime's. Every section below is
generated from the commands' own argument parsers, so it matches the installed
version.

## playbook

```{argparse}
:module: coding_agent_playbook.cli.parser
:func: build_parser
:prog: playbook
```

## playbook-hook

`playbook-hook` has one subcommand for harnesses and two for people. Harnesses run
`dispatch` through the committed launcher, as
`<pinned python> -I -m coding_agent_playbook.hook_runtime dispatch <event> --harness
claude_code|opencode [--project-dir DIR] [--async]`. It is hand-parsed and never
exits 2, so a usage error can never pass for a deny. `--version` prints the engine
version. [Checking that they run](../hooks.md#checking-that-they-run) shows the
two subcommands below at work.

### playbook-hook simulate

```{argparse}
:module: coding_agent_playbook.hook_runtime.diagnostics.simulate
:func: build_parser
:prog: playbook-hook simulate
```

### playbook-hook doctor

```{argparse}
:module: coding_agent_playbook.hook_runtime.diagnostics.doctor
:func: build_parser
:prog: playbook-hook doctor
```
