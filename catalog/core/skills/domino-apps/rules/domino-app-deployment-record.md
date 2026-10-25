---
id: domino-app-deployment-record
name: Deployment record
description: "Record every out-of-repo App setting (launch file, environment revision, tier, revision, URL, access, starter) in a deployment table per stage."
scope: scoped
globs:
  - "**/README.md"
  - "**/app.sh"
  - "docs/**/*.md"
applies_if:
  domino_project: true
section: publishing
priority: 61
tags: [domino, apps, docs]
---

# Deployment record

## Description

No manifest in the repository describes a Domino App. Its launch file, compute environment and revision, hardware tier, code branch or revision, custom URL path, deep linking, sharing mode, identity options and autoscaling settings are all chosen in the Domino UI, and the autoscaling settings persist across launches. Each App can pin its own environment revision and tier, but an environment edited in place silently changes every App that uses its moving latest revision.

Without a written record, nobody can rebuild the App, review a change of setting, or tell why it behaves differently after a republish.

## Bad Example

```markdown
## Deployment

Published as a Domino App.
```

## Good Example

```markdown
## Deployment

| Setting              | dev                    | prod                       |
| -------------------- | ---------------------- | -------------------------- |
| Code                 | branch `dev`           | tag `app-v1.4.0`           |
| Launch file          | `app.sh`               | `app.sh`                   |
| Environment          | `sales-app-env` rev 7  | `sales-app-env` rev 6      |
| Hardware tier        | small                  | medium                     |
| URL path             | `sales-dev`            | `sales`                    |
| Sharing mode         | Restricted, team only  | Restricted, discoverable   |
| Identity options     | none                   | none                       |
| Autoscaling          | off                    | 1-4 replicas               |
| Started by           | sales-app service user | sales-app service user     |
```

One branch and one environment revision per stage, published side by side; prod runs a tag on a pinned revision. A change to any row is a commit, reviewed like code.

## Notes

- Pinning packages inside the environment is domino-pinned-environments, and choosing a fixed environment revision instead of the moving latest one is domino-environment-revisions (both domino-jobs skill); clone an environment for a change rather than editing it in place.
- The account that starts and restarts the App belongs in the table, because its user variables and data rights apply (`domino-app-starter-settings`).
- The sharing mode and identity options get their own README block (`domino-app-sharing-mode`).
- What else a README needs is docs-readme-essentials (python-documentation skill).
- When behavior changes without a code change, compare this table with the version snapshot of the last publish.
