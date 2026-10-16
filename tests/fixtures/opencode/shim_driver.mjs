// Drives a rendered OpenCode shim through a scripted scenario (tests/adapters/test_opencode_shim_node.py).
// argv: <shim path> <responses dir>; stdin: the JSON step list. Each step is one of
//   {hook, input, output}   call that server hook, as OpenCode V1 would, and await it
//   {setup: true}           call the V2 setup() stub
//   {respond: {event, out, code}}  replace the fake dispatcher's canned answer for an event
// stdout: {results: [{threw, input, output, ms}], errors: [console.error lines]}.
import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { pathToFileURL } from "node:url"

const [shimPath, responses] = process.argv.slice(2)
const steps = JSON.parse(readFileSync(0, "utf8"))
const errors = []
console.error = (...parts) => { errors.push(parts.join(" ")) }

const plugin = (await import(pathToFileURL(shimPath).href)).default
const hooks = await plugin.server()
const results = []
for (const step of steps) results.push(await run(step))
// Exit once stdout has flushed (a pipe write is async), even while a killed dispatcher's pipes linger.
process.stdout.write(JSON.stringify({ results, errors }), () => process.exit(0))

async function run(step) {
  if (step.respond) {
    const { event, out, code } = step.respond
    writeFileSync(join(responses, `${event}.out`), out)
    writeFileSync(join(responses, `${event}.code`), String(code))
    return {}
  }
  const started = Date.now()
  let threw = null
  try {
    await (step.setup ? plugin.setup() : hooks[step.hook](step.input, step.output))
  } catch (e) {
    threw = String(e?.message ?? e)
  }
  return { threw, input: step.input ?? null, output: step.output ?? null, ms: Date.now() - started }
}
