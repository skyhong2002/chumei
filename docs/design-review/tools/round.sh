#!/bin/bash
# Build the current worktree, serve it, and capture one round's new set.
#   CM_REVIEW=/tmp/cm-review PORT=18732 docs/design-review/tools/round.sh N
# Resumes an interrupted capture (RESUME=1) up to three times.
set -e
N=$1; R=${CM_REVIEW:-/tmp/cm-review}; PORT=${PORT:-18732}; PY=${CM_PYTHON:-$R/venv/bin/python}
W=$(cd "$(dirname "$0")/../../.." && pwd); T=$W/docs/design-review/tools
cd "$W"
"$PY" "$T/build_preview.py" WORKTREE "$R/builds/new"
for pid in $(pgrep -f "preview_server.py $R/builds/new " || true); do kill "$pid"; done
sleep 1
(CHUMEI_PREVIEW_NOW=2026-11-12T15:30:00+08:00 PYTHONPATH=$T/frozen nohup "$PY" "$T/preview_server.py" "$R/builds/new" "$PORT" > "$R/new-server.log" 2>&1 &)
for i in $(seq 1 30); do curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
cd "$T"
for try in 1 2 3; do
  RESUME=1 nice "$PY" capture.py site "http://127.0.0.1:$PORT" "$R/sets/new-r$N" --session-file "$R/builds/new/session.txt" > "$R/cap$N.log" 2>&1 || true
  [ "$(ls "$R/sets/new-r$N" | wc -l)" -ge 88 ] && break; sleep 60
done
ls "$R/sets/new-r$N" | wc -l
