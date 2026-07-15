#!/bin/bash
# screenwatch capture loop (macOS). Run via launchd through the Screenwatch.app
# wrapper (see SETUP-AGENT-PROMPT.md — permissions need the app bundle).
set -u
: "${HOME:?HOME must be set}"   # BASE and the frame-prune -delete both hang off it

BASE="${SCREENWATCH_BASE:-$HOME/screenwatch}"
INTERVAL=5
IDLE_SKIP_SECS=90       # skip capture if no keyboard/mouse input for this long
RETAIN_DAYS=30          # prune frames older than this (log.jsonl + notes never pruned)
WIDTH=1568              # AI vision max useful long edge — bigger is wasted
WEBP_QUALITY=35         # ~40-60KB/frame, verified legible
JPEG_QUALITY=55         # fallback when ffmpeg is unavailable

# launchd doesn't inherit your shell PATH — find ffmpeg the hard way
FFMPEG=""
for c in "$(command -v ffmpeg 2>/dev/null)" /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
  [ -n "$c" ] && [ -x "$c" ] && FFMPEG="$c" && break
done
# some ffmpeg builds ship without a webp encoder — fall back to sips JPEG
if [ -n "$FFMPEG" ] && ! "$FFMPEG" -hide_banner -encoders 2>/dev/null | grep -q 'webp'; then
  FFMPEG=""
fi

last_prune_day=""

get_meta() {
  # Prints: app <TAB> window_title. Only System Events here — browser
  # dictionaries are referenced in get_url so a missing browser can't
  # break compilation of this script.
  osascript <<'EOS' 2>>"$BASE/daemon.log"
tell application "System Events"
  set p to first application process whose frontmost is true
  set appName to name of p
  set winTitle to ""
  try
    set winTitle to name of front window of p
  end try
end tell
return appName & tab & winTitle
EOS
}

get_url() {
  # $1 = frontmost app name. Separate per-browser scripts: AppleScript
  # resolves an app's dictionary at COMPILE time, so mentioning an
  # uninstalled browser is a syntax error that kills the whole script.
  case "$1" in
    "Google Chrome"|"Brave Browser"|"Arc"|"Microsoft Edge"|"Vivaldi")
      osascript -e "tell application \"$1\" to get URL of active tab of front window" 2>/dev/null ;;
    "Safari")
      osascript -e 'tell application "Safari" to get URL of front document' 2>/dev/null ;;
  esac
}

while true; do
  sleep "$INTERVAL"

  idle=$(ioreg -c IOHIDSystem 2>/dev/null | awk '/HIDIdleTime/ {print int($NF/1000000000); exit}')
  if [ "${idle:-0}" -ge "$IDLE_SKIP_SECS" ]; then continue; fi

  day=$(date +%F)
  dir="$BASE/days/$day"
  mkdir -p "$dir"
  ts=$(date +%H-%M-%S)
  epoch=$(date +%s)

  meta=$(get_meta)
  app=$(printf '%s' "$meta" | cut -f1)
  win=$(printf '%s' "$meta" | cut -f2)
  url=$(get_url "$app")

  # Dedupe: unchanged app+window+url → metadata every tick, image every 6th.
  state="$app|$win|$url"
  saved=0
  if [ "$state" != "${last_state:-}" ] || [ $(( ${tick:-0} % 6 )) -eq 0 ]; then
    # NOTE: never a dot-prefixed temp name — screencapture refuses hidden
    # paths with an error identical to a permissions denial.
    tmp="$dir/tmp-capture.png"
    if screencapture -x -m -t png "$tmp" 2>>"$BASE/daemon.log"; then
      if [ -n "$FFMPEG" ]; then
        "$FFMPEG" -y -loglevel error -i "$tmp" \
          -vf "scale=$WIDTH:-2" -quality "$WEBP_QUALITY" "$dir/$ts.webp" 2>>"$BASE/daemon.log"
        out="$dir/$ts.webp"
      else
        sips -s format jpeg -s formatOptions "$JPEG_QUALITY" \
          --resampleWidth "$WIDTH" "$tmp" --out "$dir/$ts.jpg" >/dev/null 2>&1
        out="$dir/$ts.jpg"
      fi
      rm -f "$tmp"
      [ -s "$out" ] && saved=1
    fi
  fi
  last_state="$state"
  tick=$(( ${tick:-0} + 1 ))

  APP="$app" WIN="$win" URL="$url" TS="$ts" EPOCH="$epoch" IMG="$saved" \
  python3 - >> "$dir/log.jsonl" <<'EOF'
import json, os
print(json.dumps({
  "t": os.environ["TS"], "epoch": int(os.environ["EPOCH"]),
  "app": os.environ["APP"], "window": os.environ["WIN"],
  "url": os.environ["URL"], "img": os.environ["IMG"] == "1",
}))
EOF

  # Prune frames only. log.jsonl is the durable record and is never deleted:
  # it costs ~1.2 MB/day against ~250 MB/day of images, and it is the only
  # structured source for time/focus analysis. Day dirs are left in place —
  # an image-less dir still holds its log.
  if [ "$day" != "$last_prune_day" ]; then
    find "$BASE/days" -mindepth 2 -type f \( -name '*.jpg' -o -name '*.webp' \) \
      -mtime +"$RETAIN_DAYS" -delete 2>/dev/null
    last_prune_day="$day"
  fi
done
