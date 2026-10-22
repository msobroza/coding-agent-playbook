---
id: domino-app-publish-from-commit
name: Publish from a commit
description: "Publish an App from a pushed, tagged revision and record each release in the repo; roll back by republishing an older tag."
version: 1
scope: scoped
globs:
  - "**/app.sh"
  - "**/start.sh"
applies_if:
  domino_project: true
section: publishing
priority: 60
tags: [domino, apps, git]
---

# Publish from a commit

## Description

A published App runs the code Domino can see: in a Git-based project, the branch or revision chosen in the publish dialog, as it was pushed; in a file-system project, the project files as last synced. What is open and edited in a workspace never reaches the App until it is committed and pushed, or saved and synced. Git LFS files are not available to the App.

Each publish stores a snapshot of the environment, the file references and the code paths, and the App's history can be browsed, but Domino offers no rollback button and no diff between versions. The repository is therefore the only place that can say what each published version holds and how to return to the previous one.

## Bad Example

```bash
# Edited app.sh and callbacks.py in the workspace, then published the branch head.
git status --short
#  M app.sh
#  M myapp/callbacks.py
# Nothing was committed or pushed: the App still runs the old code, or a teammate's
# later push lands in production unannounced.
```

## Good Example

```bash
git switch main
git pull --ff-only
git tag -a app-v1.4.0 -m "App release 1.4.0: export to CSV"
git push origin main app-v1.4.0
# Publish dialog: revision app-v1.4.0, environment revision as recorded in the README.
```

The release is then recorded through the repo's own changelog mechanism (`docs-changelog`, python-documentation skill), and the deployment record names the tag that runs (`domino-app-deployment-record`). Rolling back means republishing the previous tag, which the changelog names.

## Notes

- In a file-system project, files reach the project only after the workspace saves and stops; stop it before publishing (`domino-app-workspace-preview`).
- Project types and their limits are `domino-project-types` (domino-jobs skill).
- When behavior changes without a code change, compare the version snapshot with the deployment record: the environment or hardware tier is the usual cause.
- A tag is cheap; publish a tag, not a moving branch head, for any App others depend on.
