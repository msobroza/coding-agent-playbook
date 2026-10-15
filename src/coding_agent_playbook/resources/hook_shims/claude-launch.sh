@@SENTINEL_LINE@@
# Claude Code launcher for playbook-hook (specs/prK-lifecycle-hooks.md §C.2.7). Machine-independent:
# the interpreter comes from the per-worktree pin that `playbook sync` writes under the git dir.
# Exit status is 0, or 2 only for a dispatcher-decided deny (signalled as 10), so a broken install
# can never block a tool call. --strict-launch (overlay strict mode) exits 1 on failure instead.
strict=
if [ "${1:-}" = --strict-launch ]; then strict=1; shift; fi
root=${0%/.claude/hooks/playbook/launch.sh}
[ "$root" != "$0" ] || root=${CLAUDE_PROJECT_DIR:-$PWD}
gitdir=$root/.git
if [ -f "$gitdir" ]; then                       # linked worktree: .git holds "gitdir: <path>"
  IFS= read -r line < "$gitdir" || :
  gitdir=${line#gitdir: }
  case $gitdir in /* | [A-Za-z]:*) ;; *) gitdir=$root/$gitdir ;; esac
fi
state=$gitdir/playbook-hooks
py=
if [ -r "$state/interpreter" ]; then IFS= read -r py < "$state/interpreter" || :; fi
if [ -n "$py" ] && [ -x "$py" ]; then
  "$py" -I -m coding_agent_playbook.hook_runtime "$@"
  rc=$?
  case $rc in 0) exit 0 ;; 10) exit 2 ;; esac   # a raw 2 (usage, interpreter error) is NOT a deny
  why="dispatcher exited $rc"
  printf '%s %s %s\n' "$(date +%s)" "${2:-?}" "$why" 2>/dev/null >> "$state/launcher.log"
else
  why="no interpreter pin"
fi
if [ -n "$strict" ]; then exit 1; fi              # onFailure:"block" turns this into a block
if [ "${2:-}" = session_start ]; then
  printf '{"systemMessage":"playbook lifecycle hooks are INACTIVE (%s). Run: playbook-hook doctor","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"playbook lifecycle hooks are not active this session; apply the AGENTS.md Guardrails section yourself."}}\n' "$why"
fi
exit 0
