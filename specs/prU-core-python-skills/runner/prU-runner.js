export const meta = {
  name: 'prU-runner',
  description: 'prU: run a machine\'s tickets in dependency order (implement, code-review sub-agents, fix, integrate each ticket at once), or the final full gate',
  phases: [
    { title: 'Implement', detail: 'the implement skill in an isolated worktree, focused tests, push ticket/<id>' },
    { title: 'Review', detail: 'the code-review skill as its Standards and Spec sub-agents, reports kept separate' },
    { title: 'Fix', detail: 'apply the review findings, push again' },
    { title: 'Integrate', detail: 'squash-merge one ticket, light gate, fast-forward push (rebase and retry when the other machine pushed first)' },
    { title: 'Full gate', detail: 'only with fullGate: the chunked full suite on the integration tip' },
  ],
}

// Every machine-specific value comes from args (built by plan.py args); see runner/README.md.
const P = args.paths
const W = P.orchestratorCheckout
const SC = P.scratch
const SV = P.sharedVenv
const TOOLS = P.tools
const BASE = args.base
const REPO = args.repo
const M = args.machine
const PAR = args.parallel || 3
const IMPLEMENT_SKILL = args.skills.implement
const CODE_REVIEW_SKILL = args.skills.codeReview
const tickets = args.tickets || []
const DONE = new Set(args.done || [])

// ---- small async primitives: a counting semaphore that hands a freed slot to the
// waiter with the highest priority (plan.py: how many unfinished tickets wait on this
// one), first come first served among equals; a mutex is a semaphore of 1 ----
function semaphore(n) {
  let free = n
  let arrival = 0
  const waiting = []
  return {
    acquire: (priority = 0) => new Promise(resolve => {
      if (free > 0) { free--; resolve(); return }
      waiting.push({ priority, order: arrival++, resolve })
      waiting.sort((a, b) => b.priority - a.priority || a.order - b.order)
    }),
    release: () => { const next = waiting.shift(); if (next) next.resolve(); else free++ },
  }
}
const slots = semaphore(PAR)
const MAX_BATCH = 6  // tickets one integrator merges and gates together

// ---- prompt pieces ----
const TICKET_SOURCE = (t) => `Your ticket is ${t.id} (GitHub issue #${t.issue}): ${t.title}. Its full text (summary, files, tests, acceptance criteria, dependencies) is the section "${t.id}" of specs/prU-core-python-skills/tickets.md in the repository (content tickets follow that file's content-ticket template and their skill's mapping-<skill>.md). The design decisions are specs/prU-core-python-skills.md; the runbook is specs/prU-core-python-skills/implementation-runbook.md.`

const venvOf = (name) => `${SC}/runs/${name}/venv`
const PYTHON = (name) => `- Python: first, from your worktree root, run ${TOOLS}/overlay-venv.sh <your worktree's absolute path, from pwd> ${venvOf(name)} ${SV} (a pip-less overlay on the shared venv; it prints the package path, which must be inside YOUR worktree). Then run tests ONLY with ${venvOf(name)}/bin/python -m pytest -p no:cacheprovider ... (hook tests spawn \`python -I\`, which ignores PYTHONPATH; the overlay makes those subprocesses import your worktree's code). Typecheck and lint with PYTHONPATH=<worktree>/src ${SV}/bin/mypy (plain mypy, no path argument: \`mypy .\` also takes catalog/ eval-sample fixtures and fails on them), ${SV}/bin/ruff check --no-cache, ${SV}/bin/ruff format --no-cache. The worktree guard rejects commands whose paths are shell variables or globs: write paths literally. Never create any other venv and never pip install. Keep every shell command under 10 minutes.`

const RULES = (t) => `House rules (from the repository owner; follow exactly):
- AUTHORIZATION: the owner (msobroza) said "start implementing", authorizing you to commit to the branch ticket/${t.id} and push THAT branch to origin. Never push to main or ${BASE}, never open pull requests, never create/edit/close GitHub issues.
- Use /usr/bin/git for every git command (an output-filtering shell hook may rewrite plain \`git\` output).
- Never write inside ${W} (the orchestrator's checkout). Scratch files and CLI probe repos go under ${SC}/runs/${t.id}/ (mkdir -p); probe the CLI only with \`playbook init --non-interactive\`, stdin </dev/null and a timeout.
${PYTHON(t.id)}
- Tests: the full suite runs once, at the end of the effort. You run typechecking, single test files, the directories your change touches, \`-m catalog\` when catalog content or catalog tests change, tests/unit when SPEC.md, README.md, MIGRATION.md, CONTEXT.md or docs/ change (doc pins), and tests/architecture plus tests/hook_runtime/test_import_budget.py whenever you add a module or an import. Never start the full suite yourself.
- Commits: Conventional Commits (commitizen enforces them); the main commit's subject is the ticket title; every body ends with "Refs: #${t.issue} (prU ${t.id})". NEVER add Co-Authored-By or any trailer, never --author, never change git config, never sign.
- Never commit harness files: CLAUDE.md, .claude/, AGENTS.md, .opencode/, .agents/, shared_skills/, .mcp.json.
- Push with exactly: /usr/bin/git push origin HEAD:refs/heads/ticket/${t.id}`

const START = (t) => t.existingBranch
  ? `A branch ticket/${t.id} already exists on origin from an interrupted run. Start from it: /usr/bin/git fetch origin ${BASE} ticket/${t.id} && /usr/bin/git checkout -B ticket/${t.id} origin/ticket/${t.id} && /usr/bin/git merge --no-edit origin/${BASE} (merge, never rebase: the branch is published). Check what it already does against the ticket and finish the rest.`
  : `Start in your isolated worktree with: /usr/bin/git fetch origin ${BASE} && /usr/bin/git checkout -B ticket/${t.id} origin/${BASE}`

// ---- schemas ----
const IMPL = {
  type: 'object',
  properties: {
    pushed: { type: 'boolean' }, head_sha: { type: 'string' },
    commits: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' },
    tests_run: { type: 'array', items: { type: 'string' } },
    acceptance: { type: 'array', items: { type: 'object', properties: { criterion: { type: 'string' }, met: { type: 'boolean' }, evidence: { type: 'string' } }, required: ['criterion', 'met', 'evidence'] } },
    open_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['pushed', 'head_sha', 'commits', 'summary', 'tests_run', 'acceptance', 'open_issues'],
}
const REVIEW = {
  type: 'object',
  properties: {
    axis: { type: 'string', enum: ['Standards', 'Spec'] },
    report: { type: 'string', description: 'your report exactly as the brief asks (under 400 words)' },
    findings: { type: 'array', items: { type: 'object', properties: {
      kind: { type: 'string', enum: ['hard-violation', 'judgement-call', 'missing-or-partial', 'scope-creep', 'looks-wrong'] },
      file: { type: 'string' }, quote: { type: 'string', description: 'the standard or spec line cited, or the hunk quoted' },
      issue: { type: 'string' }, fix: { type: 'string' } },
      required: ['kind', 'file', 'quote', 'issue', 'fix'] } },
    worst: { type: 'string', description: 'the worst issue on this axis, or "none"' },
  },
  required: ['axis', 'report', 'findings', 'worst'],
}
const FIX = {
  type: 'object',
  properties: { pushed: { type: 'boolean' }, head_sha: { type: 'string' }, fixed: { type: 'array', items: { type: 'string' } }, rejected: { type: 'array', items: { type: 'string' } }, tests_run: { type: 'array', items: { type: 'string' } } },
  required: ['pushed', 'head_sha', 'fixed', 'rejected', 'tests_run'],
}
const INTEG = {
  type: 'object',
  properties: {
    integrated: { type: 'boolean' }, integration_head: { type: 'string' }, attempts: { type: 'number' },
    gate: { type: 'array', items: { type: 'object', properties: { command: { type: 'string' }, result: { type: 'string' } }, required: ['command', 'result'] } },
    fixes: { type: 'array', items: { type: 'string' } }, cleanup: { type: 'string' },
    open_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['integrated', 'integration_head', 'attempts', 'gate', 'fixes', 'cleanup', 'open_issues'],
}
const INTEG_BATCH = {
  type: 'object',
  properties: {
    integration_head: { type: 'string' }, pushed: { type: 'boolean' }, attempts: { type: 'number' },
    tickets: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, integrated: { type: 'boolean' }, note: { type: 'string' } }, required: ['id', 'integrated', 'note'] } },
    gate: { type: 'array', items: { type: 'object', properties: { command: { type: 'string' }, result: { type: 'string' } }, required: ['command', 'result'] } },
    fixes: { type: 'array', items: { type: 'string' } }, cleanup: { type: 'string' },
    open_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['integration_head', 'pushed', 'attempts', 'tickets', 'gate', 'fixes', 'cleanup', 'open_issues'],
}

// ---- prompts ----
const implementPrompt = (t) => `${IMPLEMENT_SKILL}

---
${TICKET_SOURCE(t)}
${START(t)}
Use /tdd (Skill tool, "mattpocock-skills:tdd") at the ticket's seams. Do NOT run /code-review yourself: the workflow runs it (its Standards and Spec sub-agents, in fresh context) right after you push, because an agent inside a workflow cannot start sub-agents. Push when your focused tests, mypy and ruff pass.

${RULES(t)}
Return the structured result (pushed=true only if the push succeeded).`

const reviewPrompt = (t, axis) => `You are the ${axis.toUpperCase()} SUB-AGENT of the /code-review skill below, reviewing prU ticket ${t.id} (issue #${t.issue}). Read-only: do not edit, commit or push anything, and do not start agents.

How this run maps onto the skill (the workflow plays the skill's lead agent):
- Steps 1-3 are done for you. Step 4 already started you and the ${axis === 'Standards' ? 'Spec' : 'Standards'} sub-agent in parallel; follow ONLY the ${axis} sub-agent part of step 4 (its brief and word limit). The workflow does step 5 (aggregation) and keeps the two axes separate.
- Fixed point: origin/${BASE}. "HEAD" means origin/ticket/${t.id}. First run /usr/bin/git fetch -q origin ${BASE} ticket/${t.id}; the diff command is /usr/bin/git diff origin/${BASE}...origin/ticket/${t.id} and the commit list /usr/bin/git log origin/${BASE}..origin/ticket/${t.id} --oneline. Never check anything out in ${W}; read full files with /usr/bin/git show origin/ticket/${t.id}:<path>.
${axis === 'Standards'
  ? `- Standards sources in this repo (step 3): CONTEXT.md (the glossary: use its terms, avoid its _Avoid_ words), docs/adr/*.md, catalog/README.md, the always rules under catalog/core/rules/always/ (house style and code legibility), pyproject.toml tool settings, and the owner's clean-code conventions already in your context (small functions and files, shallow nesting, explicit types on every signature, errors carrying the offending value and the expected shape, distinctive names, one home per piece of logic, a test for every new function and a regression test for every bug fix, comments say why). Plus the smell baseline of step 3, which is in the skill text below.`
  : `- Spec source (step 2): issue #${t.issue} (read it with gh issue view ${t.issue} --repo ${REPO}; the tracker is GitHub, and docs/agents/issue-tracker.md does not exist in this repo, which is expected: never ask anyone to run a setup command), the section "${t.id}" of specs/prU-core-python-skills/tickets.md, and the decisions it cites in specs/prU-core-python-skills.md. Quote the spec line for each finding.`}
- Return your report as the brief asks (under 400 words) in "report", and the same findings, one per item, in "findings" (kind: ${axis === 'Standards' ? 'hard-violation or judgement-call' : 'missing-or-partial, scope-creep or looks-wrong'}).

${TICKET_SOURCE(t)}

---- The /code-review skill, verbatim ----
${CODE_REVIEW_SKILL}`

const fixPrompt = (t, reviews) => `Apply the /code-review results for prU ticket ${t.id} (issue #${t.issue}). In your isolated worktree: /usr/bin/git fetch origin ticket/${t.id} && /usr/bin/git checkout -B fix-${t.id} origin/ticket/${t.id} (a branch of its own: checking out ticket/${t.id} here would move it under the implementer's worktree). Push it with the ticket's push command below; it updates origin's ticket/${t.id}.
${TICKET_SOURCE(t)}
The two axes are separate on purpose: satisfy both, and never let one excuse the other.
${reviews.map(r => `## ${r.axis}\n${r.report}\nFindings: ${JSON.stringify(r.findings, null, 1)}`).join('\n\n')}
Fix every hard violation and every Spec finding (missing or partial: implement it; scope creep: remove it unless a decision asks for it; looks wrong: fix it). Judgement calls (baseline smells) are heuristics: apply one when it clearly improves the code, otherwise reject it with a reason; a documented repo standard overrides the baseline. Reject any finding that is wrong, and say why. Add or adjust tests (test-first where it fits). Run mypy, ruff and the touched test directories (never the full suite). Commit (a Conventional Commits subject such as "fix(<area>): address review findings for ${t.id}") and push.

${RULES(t)}
Return the structured result.`

const LIGHT_TESTS = (py, range) => `run the LIGHT tests: list the changed files (/usr/bin/git diff --name-only ${range}); map each src/coding_agent_playbook/<pkg>/... to tests/<pkg>/ and each changed test file to its directory; run ${py} -m pytest -q -p no:cacheprovider --no-cov over those directories; add ${py} -m pytest -q -p no:cacheprovider --no-cov -m catalog when anything under catalog/ or tests/catalog changed, and tests/unit when SPEC.md, README.md, MIGRATION.md, CONTEXT.md or docs/ changed. ALWAYS also run ${py} -m pytest -q -p no:cacheprovider --no-cov tests/architecture tests/hook_runtime/test_import_budget.py: the import contracts and the hook import budgets break from changes anywhere, and a per-directory gate missed them before. One command per directory group, each with timeout 600000 (split a group that times out).`

// One integrator merges every ticket waiting for integration (up to MAX_BATCH) and gates them
// once: a single-ticket gate took ~25 min on an 8 GB machine, longer than the other machine's
// push interval, so re-gating after each rejected push could loop for hours (2026-10-22).
const batchIntegratePrompt = (batch, n) => {
  const venv = venvOf(`integrate-${M}-${n}`)
  const list = batch.map(b => ({ id: b.t.id, issue: b.t.issue, title: b.t.title, head: b.sha }))
  return `You are the INTEGRATOR for a batch of ${batch.length} prU ticket(s) on machine ${M}. The owner (msobroza) said "start implementing", authorizing fast-forward pushes to ${BASE} only (never force-push, never main, no PRs, no issue edits). Another machine integrates into the same branch at the same time.
Tickets, in this order (highest priority first): ${JSON.stringify(list, null, 1)}
1. In your isolated worktree: /usr/bin/git fetch origin && /usr/bin/git checkout -B integrate-${M}-${n} origin/${BASE}. A ticket whose "(#<issue>)" commit is already on origin/${BASE} is done: integrated=true, note "already integrated".
2. For each other ticket, in order: check origin/ticket/<id> (if its head is newer than the listed one, use it and say so in its note); /usr/bin/git merge --squash origin/ticket/<id>; resolve conflicts keeping both sides' intent (import lists: union, then ruff --fix for I and F401; tests/cli/golden/cli_surface.json: never merge by hand, re-record it with ${venv}/bin/python -m tests.cli.cli_surface after resolving the code, and review its diff); commit ONE commit per ticket: subject = "<title> (#<issue>)", body = a short summary then the line "Closes #<issue>". NEVER add Co-Authored-By or any trailer, never --author, never change git config, never sign. If a ticket cannot be merged after a real attempt, drop its partial merge (/usr/bin/git reset --hard HEAD), mark it integrated=false with the reason, and go on.
3. Light gate, ONCE for the whole batch. From your worktree root: ${TOOLS}/overlay-venv.sh <your worktree's absolute path> ${venv} ${SV}. Then ${SV}/bin/ruff check --no-cache . ; ${SV}/bin/ruff format --no-cache --check . ; PYTHONPATH=<worktree>/src ${SV}/bin/mypy ; then ${LIGHT_TESTS(venv + '/bin/python', `origin/${BASE} HEAD`)} Fix failures with small "fix: ..." commits (body ends "Refs: prU integration batch ${M}-${n}"); a failure that is pre-existing on origin/${BASE} goes to open_issues. If one ticket breaks the gate and you cannot fix it quickly, rebuild the batch without it (/usr/bin/git reset --hard origin/${BASE}, redo step 2 for the others; never revert, because its "(#<issue>)" subject would stay in the history) and mark it integrated=false with the failure.
4. Push with exactly: /usr/bin/git push origin HEAD:refs/heads/${BASE}. If it is rejected (the other machine pushed first): /usr/bin/git fetch origin && /usr/bin/git rebase origin/${BASE}. If the rebase applies WITHOUT conflicts, push again at once and do NOT rerun the gate: the commits you rebased onto passed their own gate, and the full suite at the end checks the combination. If it had conflicts, resolve them as in step 2, rerun ruff and only the tests of the conflicted files' directories, then push. At most 6 attempts; report attempts.
5. Cleanup: for each integrated ticket, remove (/usr/bin/git worktree remove --force) only the worktrees whose branch is ticket/<id> or fix-<id> and whose status is clean, then delete those local branches. If a removal is refused, leave it and say so in cleanup.
${PYTHON(`integrate-${M}-${n}`)}
Never write inside ${W}. Return integration_head, pushed, attempts, and for EVERY ticket of the batch {id, integrated, note}: integrated=true only when its squash commit is on origin/${BASE} after your push, or was already there.`
}

const fullGatePrompt = () => `You are the FINAL GATE for prU on machine ${M}: run the full CI-parity gate once on the integration tip. Authorized: fast-forward pushes to ${BASE} only (never force-push, never main, no PRs, no issue edits).
1. In your isolated worktree: /usr/bin/git fetch origin && /usr/bin/git checkout -B final-gate origin/${BASE}. Build the overlay: ${TOOLS}/overlay-venv.sh <your worktree's absolute path> ${venvOf('final-gate')} ${SV}.
2. ${SV}/bin/ruff check --no-cache . ; ${SV}/bin/ruff format --no-cache --check . ; PYTHONPATH=<worktree>/src ${SV}/bin/mypy
3. The full pytest as numbered chunks whose coverage adds up in ./.coverage (never export COVERAGE_FILE: nested pytest runs inside tests inherit it). Each line is ONE Bash command with timeout 600000, from your worktree root, in order:
   ${venvOf('final-gate')}/bin/python ${TOOLS}/suite_chunk.py check
${[...Array(12).keys()].map(i => `   ${venvOf('final-gate')}/bin/python ${TOOLS}/suite_chunk.py ${i + 1}`).join('\n')}
   ${venvOf('final-gate')}/bin/python ${TOOLS}/suite_chunk.py report
   If check reports a test file outside the chunks, add its path to the right chunk of tools/suite_chunk.py in a "fix:" commit. If a chunk times out, run its paths in smaller groups with ${venvOf('final-gate')}/bin/python -m pytest -o addopts= -q -p no:cacheprovider --cov=coding_agent_playbook --cov-append --cov-report= <paths>.
4. Fix failures with small "fix: ..." commits (body ends "Refs: prU final gate"), rerunning only the failed chunk, then push with exactly /usr/bin/git push origin HEAD:refs/heads/${BASE} (on rejection: fetch, rebase, rerun the failed parts, push).
${PYTHON('final-gate')}
Never write inside ${W}. Return the structured result (integrated = the gate is green and pushed).`

// ---- one ticket, end to end ----
async function ticketChain(t) {
  // startAt 'integrate': an earlier run already implemented, reviewed and fixed it (plan.py --integrate-only).
  if (t.startAt === 'integrate') return integrateTicket(t, 'its current head (reviewed and fixed in an earlier run)', {})
  await slots.acquire(t.priority || 0)
  let impl, reviews = [], fix = null
  try {
    impl = await agent(implementPrompt(t), { label: `implement:${t.id}`, phase: 'Implement', agentType: 'general-purpose', effort: 'medium', isolation: 'worktree', schema: IMPL })
    if (!impl || !impl.pushed) return { t, status: 'failed', stage: 'implement', impl }
    reviews = (await parallel(['Standards', 'Spec'].map(axis => () =>
      agent(reviewPrompt(t, axis), { label: `code-review-${axis.toLowerCase()}:${t.id}`, phase: 'Review', effort: 'medium', schema: REVIEW })))).filter(Boolean)
    log(`${t.id} code-review: ${reviews.map(r => `${r.axis} ${r.findings.length} finding(s), worst: ${r.worst}`).join(' | ')}`)
    if (reviews.some(r => r.findings.length)) {
      fix = await agent(fixPrompt(t, reviews), { label: `fix:${t.id}`, phase: 'Fix', agentType: 'general-purpose', effort: 'medium', isolation: 'worktree', schema: FIX })
      if (!fix || !fix.pushed) return { t, status: 'failed', stage: 'fix', impl, reviews, fix }
    }
  } finally {
    slots.release()  // integration waits on its own lock, so the next ticket can start implementing
  }
  return integrateTicket(t, (fix && fix.head_sha) || impl.head_sha, { impl, reviews, fix })
}

// Tickets that finish review and fix queue here; whenever no integrator is running, the next
// one takes the whole queue (highest priority first, up to MAX_BATCH), so integration keeps
// pace with several implementers instead of serializing one ticket per gate.
const integrationQueue = []
let integrating = false
let batchCount = 0
function integrateTicket(t, sha, earlier) {
  return new Promise(resolve => {
    integrationQueue.push({ t, sha, earlier, resolve })
    pumpIntegration()
  })
}

async function pumpIntegration() {
  if (integrating || integrationQueue.length === 0) return
  integrating = true
  // Let tickets queued in the same instant (a restart's integrate-only tickets) join this batch.
  for (let i = 0; i < 20; i++) await Promise.resolve()
  integrationQueue.sort((a, b) => (b.t.priority || 0) - (a.t.priority || 0))
  const batch = integrationQueue.splice(0, MAX_BATCH)
  batchCount += 1
  const res = await agent(batchIntegratePrompt(batch, batchCount), { label: `integrate:${batch.map(b => b.t.id).join('+')}`, phase: 'Integrate', agentType: 'general-purpose', effort: 'medium', isolation: 'worktree', schema: INTEG_BATCH })
  for (const item of batch) {
    const r = res && (res.tickets || []).find(x => x.id === item.t.id)
    const ok = !!(r && r.integrated)
    log(`${item.t.id}: ${ok ? 'integrated at ' + res.integration_head : 'NOT integrated' + (r ? ': ' + r.note : '')}`)
    const integ = res ? { integration_head: res.integration_head, attempts: res.attempts, gate: res.gate, fixes: res.fixes, cleanup: res.cleanup, open_issues: [...(res.open_issues || []), ...(r && r.note ? [r.note] : [])] } : null
    item.resolve({ t: item.t, status: ok ? 'integrated' : 'failed', stage: 'integrate', ...item.earlier, integ })
  }
  integrating = false
  pumpIntegration()
}

// ---- dependency-ordered scheduling ----
const byId = new Map(tickets.map(t => [t.id, t]))
const started = new Map()
function run(id) {
  if (started.has(id)) return started.get(id)
  const t = byId.get(id)
  const p = (async () => {
    const pending = t.deps.filter(d => !DONE.has(d))
    const outside = pending.filter(d => !byId.has(d))
    if (outside.length) return { t, status: 'blocked', reason: `waits for tickets not in this run and not yet integrated: ${outside.join(', ')}` }
    const upstream = await Promise.all(pending.map(run))
    const bad = upstream.filter(r => r.status !== 'integrated').map(r => r.t.id)
    if (bad.length) return { t, status: 'blocked', reason: `dependencies not integrated in this run: ${bad.join(', ')}` }
    return ticketChain(t)
  })()
  started.set(id, p)
  return p
}

// Highest priority first, so the first free slots go to the critical chain.
const order = [...tickets].sort((a, b) => (b.priority || 0) - (a.priority || 0))
const results = await Promise.all(order.map(t => run(t.id)))
let gate = null
if (args.fullGate) {
  phase('Full gate')
  gate = await agent(fullGatePrompt(), { label: 'full-gate', phase: 'Full gate', agentType: 'general-purpose', effort: 'medium', isolation: 'worktree', schema: INTEG })
}

const brief = r => ({
  id: r.t.id, issue: r.t.issue, status: r.status, stage: r.stage, reason: r.reason,
  head: r.impl && r.impl.head_sha, impl_open_issues: r.impl && r.impl.open_issues,
  reviews: (r.reviews || []).map(v => ({ axis: v.axis, findings: v.findings.length, worst: v.worst })),
  fixed: r.fix ? r.fix.fixed : [], rejected: r.fix ? r.fix.rejected : [],
  integration: r.integ ? { head: r.integ.integration_head, attempts: r.integ.attempts, gate: r.integ.gate, fixes: r.integ.fixes, cleanup: r.integ.cleanup, open_issues: r.integ.open_issues } : undefined,
})
return {
  machine: M,
  integrated: results.filter(r => r.status === 'integrated').map(r => r.t.id),
  blocked: results.filter(r => r.status === 'blocked').map(r => ({ id: r.t.id, reason: r.reason })),
  failed: results.filter(r => r.status === 'failed').map(r => ({ id: r.t.id, stage: r.stage })),
  tickets: results.map(brief),
  fullGate: gate,
}
