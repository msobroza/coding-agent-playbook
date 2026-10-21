#!/bin/sh
# overlay-venv.sh <worktree> <dest> <shared-venv>
# A pip-less venv whose interpreter imports <worktree>/src first, then the shared venv's
# packages. Hook tests run `python -I -m ...`, which ignores PYTHONPATH, so without this
# they import whatever checkout the shared venv's editable install points at.
# Prints the package path the overlay imports; it must lie inside <worktree>.
set -eu
WT=$1
DEST=$2
SHARED=$3
[ -x "$SHARED/bin/python" ] || { echo "no python in shared venv: $SHARED" >&2; exit 2; }
[ -d "$WT/src/coding_agent_playbook" ] || { echo "not a checkout: $WT" >&2; exit 2; }
[ -x "$DEST/bin/python" ] || "$SHARED/bin/python" -m venv --without-pip "$DEST"
purelib() { "$1" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"; }
SITE=$(purelib "$DEST/bin/python")
SHARED_SITE=$(purelib "$SHARED/bin/python")
printf '%s\n' "$WT/src" > "$SITE/00_src.pth"
printf '%s\n' "$SHARED_SITE" > "$SITE/01_shared.pth"
# Subprocess coverage startup hook, when the shared venv has one (coverage >= 7.x ships it).
if [ -f "$SHARED_SITE/a1_coverage.pth" ]; then cp "$SHARED_SITE/a1_coverage.pth" "$SITE/"; fi
cd / && "$DEST/bin/python" -I -c "import coding_agent_playbook, os; print(os.path.dirname(coding_agent_playbook.__file__))"
