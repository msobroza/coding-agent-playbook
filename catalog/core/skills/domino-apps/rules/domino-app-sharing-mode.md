---
id: domino-app-sharing-mode
name: Sharing mode
description: "Choose the App's sharing mode deliberately and document its audience, data, limits and support contact in the README."
version: 1
scope: scoped
globs:
  - "**/README.md"
applies_if:
  domino_project: true
section: publishing
priority: 62
tags: [domino, apps, docs, security]
---

# Sharing mode

## Description

An App's link travels: it is pasted into chats, tickets and slide decks far beyond the group it was made for, and anyone holding it can try to open the App. Only two things protect it: the sharing mode chosen at publish time (restricted to named viewers, or open to anyone in Domino; a restricted App can still be discoverable, with access requests sent to its owners) and the App's own checks on each viewer. Edit rights do not come from the sharing mode at all: every collaborator of the project can edit and republish the App. Where an admin allows it, viewers who are not signed in can be admitted too.

A secret link is not access control; the README states who the App is for and what it exposes, so the mode can be reviewed.

## Bad Example

```markdown
## Access

The link is private, please share it carefully.
```

## Good Example

```markdown
## Access

- Audience: the EMEA sales team (about 40 people).
- Sharing mode: Restricted, discoverable; owners approve access requests.
- Data: aggregated weekly sales from the `sales-weekly` Dataset; no customer names.
- Known limits: figures lag one day; exports cap at 10,000 rows.
- Support: the sales-analytics team alias, not an individual.
- Extended identity: off. The App never acts as the viewer.
```

Operations that touch sensitive records still check the viewer in code (`domino-app-verify-viewer-jwt`), whatever the mode.

## Notes

- Use the open mode only for tools meant for everyone in Domino; re-check the mode after every clone, rename or republish.
- When extended identity is on, the README says why the App must act as the viewer (`domino-app-viewer-token`).
- Anonymous viewers are possible where an admin allows them (`domino-app-viewer-identity`).
- Keep the project's collaborator list as short as the set of people allowed to change the App.
- The rest of the README follows docs-readme-essentials (python-documentation skill).
