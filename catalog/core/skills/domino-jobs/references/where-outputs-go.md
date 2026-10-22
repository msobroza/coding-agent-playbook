# Where a job's outputs go

A Domino run starts in a fresh container. When it ends, the project type decides what is copied back, and Dataset mounts keep what was written to them in place; everything else is lost with the container. Use the tables below to decide where a file goes and whether it survives the run, then read the rule named in the last column. Paths are the Domino 6.2 defaults: code reads the variable, never the literal (domino-paths-from-env).

Contents: where each location comes from; will this file survive the run; where each kind of output goes; which files become results; limits next to each location; when an output goes wrong.

## Where each location comes from

| Location | DFS project | Git-based project | Flow task | Variable | Rules |
| --- | --- | --- | --- | --- | --- |
| Working directory | `/mnt`, or `/mnt/<owner>/<project>` once another project is imported | `/mnt/code`, the repository checkout | as its project type | `DOMINO_WORKING_DIR` | domino-paths-from-env |
| Synced output root | the working directory | `/mnt/artifacts` | not kept | `DOMINO_ARTIFACTS_DIR` (Git-based) | domino-project-types |
| Local datasets | `/domino/datasets/local/<name>` | `/mnt/data/<name>` | the chosen snapshot, read-only, at the plain dataset path | `DOMINO_DATASETS_DIR` | domino-paths-from-env, domino-dataset-snapshots |
| Shared and imported datasets | under the imported data directory | `/mnt/imported/data/<name>` | as local datasets | `DOMINO_IMPORTED_DATA_DIR` | domino-dataset-snapshots |
| Dataset snapshot | `snapshots/<name>/<number>` under the datasets directory | `snapshots/<name>/<number>` under the datasets directory | no `snapshots` segment | the datasets variables above | domino-dataset-snapshots |
| Task inputs and outputs | none | none | `/workflow/inputs/<name>`, `/workflow/outputs/<name>` | none (fixed paths) | domino-flow-task-io |
| Which case applies | `DOMINO_IS_GIT_BASED` is not `"true"` | `DOMINO_IS_GIT_BASED` is `"true"` | `DOMINO_IS_WORKFLOW_JOB` is `"true"` | both arrive as text | domino-paths-from-env |

The 6.2 pages also spell the Git-based dataset root `/mnt/local`, and one suggests replacing `/mnt` with `DOMINO_WORKING_DIR` for artifacts, which points at the code checkout in Git-based projects. Read the variables and log the resolved roots on the first run of a deployment.

## Will this file survive the run?

| A file written to | DFS project | Git-based project | Flow task | Rules |
| --- | --- | --- | --- | --- |
| The working directory | kept, unless `.dominoignore` matches it | lost: a job neither commits nor pushes code edits | lost | domino-project-types |
| The artifacts directory | kept (it sits beside the project files) | kept | lost | domino-project-types |
| A read-write dataset | written in place, never copied | written in place, never copied | not allowed: Flows mount read-only snapshots | domino-run-scoped-writes, domino-flow-task-io |
| `/workflow/outputs/<name>` | not used | not used | kept, and required for every declared output | domino-flow-task-io |
| `/tmp`, the home directory | lost | lost | lost | domino-project-types |

Files are copied back when a run succeeds, fails or is stopped, so a stopped run still syncs half-written files: write them atomically (domino-run-scoped-writes). An Error state is a platform failure; do not count on its outputs. The file store keeps every version, so a secret written to a synced path stays there (domino-secrets-in-env-vars).

## Where each kind of output goes

| Output | DFS project | Git-based project | Flow task | Rules |
| --- | --- | --- | --- | --- |
| Reports, plots, small tables | `results/` under the working directory | `results/` under the artifacts directory | a declared output | domino-project-types, domino-job-results |
| `dominostats.json` | the working directory root | the artifacts root (the docs are silent; check the columns appear) | not kept | domino-job-stats-file |
| `email.html` | the project root | the artifacts root | not kept | domino-job-email-report |
| `manifest.json` | beside the results it describes | beside the results it describes | a declared output | domino-run-manifest |
| Logs | stdout; its tail lands in `results/stdout.txt` | stdout | stdout | domino-job-logging |
| Spot checkpoints | `checkpoints/` under the artifacts directory; confirm on the first run (the docs name only the Git-based path) | `checkpoints/` under the artifacts directory | not kept | domino-spot-checkpoints |
| Big or many files | a run-keyed dataset directory | a run-keyed dataset directory | a declared output; a Flow writes no dataset | domino-datasets-for-large-data, domino-run-scoped-writes |
| Extracts from databases, APIs, drives | a dataset file with its query record | a dataset file with its query record | a declared output | domino-materialize-external-data |
| Caches, virtual environments, scratch | listed in `.dominoignore` | outside the artifacts directory | anywhere but the outputs | domino-job-results |
| Secrets | never written to a file | never written to a file | never written to a file | domino-secrets-in-env-vars |

## Which files become results?

| | DFS project | Git-based project | Flow task | Rules |
| --- | --- | --- | --- | --- |
| Saved after the run | every new or changed file not in `.dominoignore` | every new or changed file under the artifacts directory | the declared outputs | domino-job-results, domino-project-types |
| Shown in the results view and success email | the files `.dominoresults` lists, or all of them | the files `.dominoresults` lists, or all of them | not documented | domino-job-results |
| Compared between runs | files matched by name | files matched by name | not documented | domino-job-results |

Keep result names stable from run to run; Domino versions files itself. A custom `email.html` must be listed when `.dominoresults` exists (domino-job-email-report).

## Limits next to each location

| Location and its default limits | DFS project | Git-based project | Flow task | Rules |
| --- | --- | --- | --- | --- |
| Project files: 10,000 files per project, 8 GB per transferred file, sync not designed for more than about 10 GB or 100,000 files, a 15-minute timeout on the copy into a run; cluster workers cannot see them | the working directory and imported projects, copied in and back | the checkout and imported projects copied in; the artifacts directory copied in and back | copied in like any job; nothing copied back | domino-datasets-for-large-data |
| Datasets: mounted, not copied; no file-count or file-size limit | read-write or read-only by the user's dataset role | read-write or read-only by the user's dataset role | one read-only snapshot per dataset | domino-datasets-for-large-data, domino-flow-task-io |
| Dataset snapshots: immutable; taking one copies the data and grows with its size | read-only, by number | read-only, by number | the chosen one, read-only, at the plain dataset path | domino-dataset-snapshots |
| Results compared between runs: example admin caps of 250 files and about 1 MB of diffs | applies | applies | not documented | domino-job-results |
| Flow outputs: one file per declared output name; a missing one fails the task | not used | not used | applies | domino-flow-task-io |

## When an output goes wrong

| Symptom | Likely cause | Rules |
| --- | --- | --- |
| The job Succeeded but its files are gone | Git-based project writing beside the code, or a path `.dominoignore` matches | domino-project-types, domino-job-results |
| A Flow task fails after its code finished | a declared output missing or misnamed under `/workflow/outputs` | domino-flow-task-io |
| A Flow task reads nothing where a job read data | inputs and snapshots sit at Flow paths, not artifact or snapshot paths | domino-flow-task-io, domino-dataset-snapshots |
| Debug dumps or scratch files appear in Results | they were written to a synced location; list what readers see in `.dominoresults` and ignore scratch | domino-job-results, domino-job-logging |
| Dashboard columns stay empty | `dominostats.json` not written every run, not flat and finite, or in the wrong root | domino-job-stats-file |
| The custom email is not sent | `email.html` in the wrong root, or missing from `.dominoresults` | domino-job-email-report |
| Start or end of the run is slow, or the copy times out | many or big files in project files | domino-datasets-for-large-data |
| One run overwrote another's output | concurrent runs writing one shared dataset path | domino-run-scoped-writes |
| A result cannot be reproduced | the run read a changing dataset root or an outside source | domino-dataset-snapshots, domino-materialize-external-data, domino-run-manifest |
| A spot job restarts from the beginning | no checkpoint under the artifacts directory, or none resumed at startup | domino-spot-checkpoints |
