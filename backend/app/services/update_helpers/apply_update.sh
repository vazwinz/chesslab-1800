#!/bin/sh
# AURA's in-place updater for Linux. The app starts it detached ("Atualizar agora", see
# backend/app/services/updater.py) right before closing itself, after unpacking and checking the
# new version next to its own folder (--new). It waits for AURA to exit, swaps the folders (one
# rename each; if the second fails the old folder is put back) and starts AURA again. The data
# folder (~/.local/share/aura) is never touched. POSIX sh, no bashisms (Ubuntu runs it with dash).
#
#   sh apply_update.sh --app DIR --new DIR --pid PID --version X --result FILE
#                      [--log FILE] [--wait-seconds 60] [--no-start]
#
# --result receives {"ok", "step", "code", "version"}; "step" says where it stopped:
# wait (AURA did not close) or swap (the folders could not be exchanged).
APP="" NEW="" PID="" VERSION="" RESULT="/dev/null" LOG="/dev/null" WAIT=60 START=1
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP=$2; shift 2 ;;
    --new) NEW=$2; shift 2 ;;
    --pid) PID=$2; shift 2 ;;
    --version) VERSION=$2; shift 2 ;;
    --result) RESULT=$2; shift 2 ;;
    --log) LOG=$2; shift 2 ;;
    --wait-seconds) WAIT=$2; shift 2 ;;
    --no-start) START=0; shift ;;
    *) echo "apply_update.sh: unknown option $1" >&2; exit 2 ;;
  esac
done

APP=$(cd "$APP" 2>/dev/null && pwd -P) || APP=${APP%/}  # the real path, as /proc/<pid>/exe shows it

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" >>"$LOG" 2>/dev/null; }
result() { printf '{"ok": %s, "step": "%s", "code": null, "version": "%s"}\n' "$1" "$2" "$VERSION" >"$RESULT"; }
start_aura() {
  [ "$START" = 1 ] && [ -x "$APP/AURA" ] || return 0
  log "starting $APP/AURA"
  (cd "$APP" && nohup "$APP/AURA" >/dev/null 2>&1 </dev/null &)
}
alive() { kill -0 "$PID" 2>/dev/null; }
# the pid is AURA's only while it runs from the app folder (it may have been reused since)
ours() { case "$(readlink "/proc/$PID/exe" 2>/dev/null)" in "$APP"/*) return 0 ;; esac; return 1; }

log "update to $VERSION: $NEW replaces $APP, AURA pid $PID"
i=0
while alive && ours; do
  if [ "$i" -ge $((WAIT * 4)) ]; then
    log "AURA ($PID) still running after ${WAIT}s: stopping it"
    kill -9 "$PID" 2>/dev/null
    sleep 1
    break
  fi
  i=$((i + 1))
  sleep 0.25
done
if alive && ours; then log "AURA ($PID) did not stop"; result false wait; exit 1; fi

OLD="$(dirname "$APP")/.$(basename "$APP")-old"
rm -rf "$OLD"
if [ ! -x "$NEW/AURA" ]; then log "no program at $NEW/AURA"; result false swap; start_aura; exit 1; fi
if ! mv "$APP" "$OLD"; then log "could not move $APP away"; result false swap; start_aura; exit 1; fi
if ! mv "$NEW" "$APP"; then
  log "could not move $NEW into place: putting the old version back"
  mv "$OLD" "$APP"
  result false swap
  start_aura
  exit 1
fi
[ -e "$APP/aura.png" ] || cp "$OLD/aura.png" "$APP/aura.png" 2>/dev/null  # the menu entry's icon
rm -rf "$OLD"
rmdir "$(dirname "$NEW")" 2>/dev/null
result true done
log "update to $VERSION done"
start_aura
exit 0
