---
status: superseded by ADR 0012
---

# A second prompt set that points to skills, chosen per repo

The core prompts list rules (`includes_rules`) but never point the agent to the skills that would help it check or improve its work, and they cannot change during the pilot because eval samples grade them. We add a second prompt set: `catalog/core/prompts/v2/` holds a version of each core prompt under the same name, and a committed config key `prompts = "v2"` selects it. A v2 prompt names the core skills to load for its task (only those active in the repo), the framework capability to use when something is unclear, and the framework capabilities and decision guides that check the result. v1 stays the default until the pilot ends, so graded prompts and their evals are untouched.

## Considered Options

- **Separate prompts named `*-v2`.** Both versions would appear in the skill listing, doubling its cost, and users would choose between near-duplicates on every task.
- **Rewrite the v1 prompts now.** The graded prompts would change during the eval freeze, and no comparison would remain to show whether the skill guidance helps.

## Consequences

- v2 keeps v1's `includes_rules`, so the opt-in eval comparison can measure the skill guidance alone; when v2 becomes the default after the pilot, v1 can be retired.
- A prompt names framework skills only through capabilities, so the same v2 text works with mattpocock_skills, superpowers, another framework or none.
- The core skills to load sit under `## Skills for this task`, not a second `## Before you start`: the Claude Code and OpenCode adapters already insert a block of that name for the included rules.
- The non-interactive workflows (characterize, make-testable, review-architecture, find-injected-vulnerability) record an assumption instead of stopping to ask, and ask only when the request names nothing they can act on, so an eval run never stalls on a question.
