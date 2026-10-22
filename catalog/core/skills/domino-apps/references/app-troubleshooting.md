# App troubleshooting

A decision guide for Domino 6.2 Apps: from what a viewer or the publisher sees
going wrong to where the cause shows and which rule fixes it. App failures
surface far from their cause (a hand-built prefix breaks only at the next
restart, a lost file only at the next scale event), so start from the symptom,
confirm the cause, then read the rule before changing code. Rules are named by
id; this guide never restates them.

## Where to look first

| Evidence | Where it is | What it tells you |
| --- | --- | --- |
| Execution logs | The App's logs in the Domino UI | The launch script's output and the server's stdout and stderr, every pod interleaved into one log |
| Support bundle | Downloaded from the App's run | The same logs plus the platform's own files for the run; attach it to a support request |
| Usage tab | The App's page in the Domino UI | CPU and memory over the last 15 days |
| Browser console and network panel | The viewer's browser | Blocked resources, failed fetches and the status code of each request |
| Deployment record | The repo (domino-app-deployment-record) | Which revision, environment, tier and starter the running App uses |

A log line is only useful if the App writes one: configure logging as
domino-app-logging says before you need it.

## The App never reaches Running

| What the logs show | Likely cause | Rules |
| --- | --- | --- |
| No output at all | The launch file was never run or exited at once: wrong file picked at publish, not executable, or a shell error before the server line | domino-app-launch-script |
| The server starts, but the App stays starting | It listens on loopback or on a framework's default port, not 0.0.0.0:8888 | domino-app-bind-host-port, then the framework rule |
| The server starts, then the process exits | The server was sent to the background, or the script returned after starting it | domino-app-launch-script |
| A package install or import error | Packages installed at start, or missing from the environment | domino-app-launch-script, domino-app-publish-from-commit |
| Nothing, and the run waits to be scheduled | No capacity for the hardware tier, or the project already runs its maximum of Apps | Ask an admin; see "Platform limits" below |

The framework rules are domino-app-dash, domino-app-flask, domino-app-streamlit
and domino-app-shiny; a Flask or Dash App also needs domino-app-production-server.

## Blank page, 404 or 502

| Symptom | Likely cause | Rules |
| --- | --- | --- |
| The page loads but stays blank; the console shows 404s for scripts or styles | Assets or API calls start at '/' and leave the App's prefix | domino-app-relative-urls, then the framework rule |
| 404 on a link, redirect or form post | A URL built without the prefix, or a redirect that drops it | domino-app-relative-urls, domino-app-url-prefix |
| Blank page or 404/502 after a restart or platform upgrade | A prefix assembled from owner, project and run id; the secure identity flag moved the App's path | domino-app-url-prefix |
| The console reports a blocked font, script, frame or API call | A content security policy or iframe restriction blocks an outside host | domino-app-external-resources |
| 502 on every request | Nothing answers on 0.0.0.0:8888, or the server crashed | domino-app-bind-host-port, domino-app-production-server |
| Works as a workspace preview, fails once published | The preview's port or proxy path leaked into the published code | domino-app-workspace-preview, domino-app-url-prefix |

A Dash App needs both of its prefixes and a Flask App its mount middleware:
domino-app-dash and domino-app-flask.

## 504, 413 and slow pages

| Symptom | Likely cause | Rules |
| --- | --- | --- |
| 504 after about five minutes | A handler runs past the proxy's read timeout (300 s by default) | domino-app-proxy-limits |
| 413 on upload | The request body is over the proxy's body cap (25 MiB by default) | domino-app-proxy-limits |
| Requests queue behind one another | The built-in development server, or too few workers | domino-app-production-server |
| Memory near the tier's limit, or growing slowly over days | Undersized tier, or a leak such as an unbounded per-viewer cache | Usage tab; domino-app-replica-state |
| A model call fails with 401 or 403 | The endpoint's access token is missing or sent the wrong way | domino-app-endpoint-auth |

Right-size the hardware tier from measured usage: when CPU or memory sits above
about 80 % of the tier, move up; a slow climb that never falls points to a leak.

## Lost data or sessions

| Symptom | Likely cause | Rules |
| --- | --- | --- |
| Saved files gone after a restart, stop or scale event | Runtime writes went to the container, which keeps nothing | domino-app-external-persistence |
| Two viewers' saves overwrite each other | A read-modify-write of one shared file | domino-app-concurrent-writes |
| A viewer's session resets or their data appears to vanish between clicks | Per-viewer state held in one process's memory while requests reach other workers or replicas | domino-app-replica-state, and domino-app-shiny for session affinity |
| Every viewer sees the same rows | Mounted data acts with the publisher's rights, not the viewer's | domino-app-publisher-data-rights |
| The App greets the wrong person, or everyone as one user | The viewer read from the wrong place or trusted without verification | domino-app-viewer-identity, domino-app-verify-viewer-jwt |

## It changed after a restart

| What changed | Likely cause | Rules |
| --- | --- | --- |
| Missing keys or different credentials | User-level variables and data credentials follow whoever last started the App | domino-app-starter-settings |
| Different code or behavior | It was republished from another revision or environment | domino-app-publish-from-commit, domino-app-deployment-record |
| Broken links or a blank page | The App's path changed with the secure identity flag | domino-app-url-prefix |
| Outside resources now blocked | An admin turned the content security policy on | domino-app-external-resources |

Compare the running App with its deployment record first: every setting that
lives in the Domino UI and not in the repo is a candidate.

## Platform limits

Some failures come from settings an admin owns, not from the App's code. Report
them rather than working around them:

- Apps or publishing are turned off for the deployment, or publishing is
  restricted to some users.
- The project already runs its maximum of Apps (by default 10 Apps per
  project, 4 of them running).
- A governance policy blocks publishing or viewing the App until it is
  approved.
- Autoscaling on a remote data plane needs a volume an admin has mapped.
- Platform feature flags apply without a restart, while configuration records
  apply only after the App restarts.
