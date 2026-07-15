#!/usr/bin/env bash
# Screenwatch installer. Compiles the TCC-anchor app, lays down the scripts,
# templates the launchd jobs with YOUR paths, and walks the one permission grant
# macOS will not let a script do for you. Idempotent: re-run to update.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SKILL_DIR/src"
BASE="${SCREENWATCH_BASE:-$HOME/screenwatch}"
APP="$HOME/Applications/Screenwatch.app"
AGENTS="$HOME/Library/LaunchAgents"
CLAUDE_SKILLS="$HOME/.claude/skills/screenwatch"
LABEL_PREFIX="com.screenwatch"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { local a; read -r -p "  $1 [$2] " a; printf '%s' "${a:-$2}"; }

# ---------------------------------------------------------------- platform
say "Screenwatch installer"
[[ "$(uname -s)" == "Darwin" ]] || die "macOS only — needs screencapture, osascript, and launchd."

# ---------------------------------------------------------------- deps
say "Checking dependencies"
command -v python3 >/dev/null || die "python3 not found. Install Xcode CLT: xcode-select --install"
ok "python3 $(python3 -c 'import platform;print(platform.python_version())')"

command -v cc >/dev/null || die "no C compiler. Run: xcode-select --install"
ok "cc (for the app launcher)"

if python3 -c 'import yaml' 2>/dev/null; then
  ok "PyYAML"
else
  warn "PyYAML missing (aggregate.py needs it)."
  if [[ "$(ask 'pip install PyYAML now? (y/N)' n)" == [yY] ]]; then
    python3 -m pip install -r "$SKILL_DIR/requirements.txt" || die "pip install failed"
    ok "PyYAML installed"
  else
    warn "Skipped — install it before running analysis."
  fi
fi

if command -v ffmpeg >/dev/null && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q webp; then
  ok "ffmpeg with webp (frames ~40-60 KB)"
else
  warn "no ffmpeg+webp — will fall back to sips JPEG (larger frames, still fine)."
fi

CLAUDE_BIN="$(command -v claude || true)"
if [[ -n "$CLAUDE_BIN" ]]; then
  ok "claude CLI at $CLAUDE_BIN (nightly analysis available)"
else
  warn "claude CLI not found — capture + dashboard still work; nightly auto-analysis will not."
fi

# ---------------------------------------------------------------- config
say "Configuration"
echo "  Data + scripts live under a base directory."
BASE="$(ask 'Base directory' "$BASE")"
BASE="${BASE/#\~/$HOME}"

DASH_HOST="$(ask 'Dashboard bind address (127.0.0.1 = this machine only)' '127.0.0.1')"
DASH_PORT="$(ask 'Dashboard port' '8484')"
if [[ "$DASH_HOST" != "127.0.0.1" && "$DASH_HOST" != "localhost" ]]; then
  warn "The dashboard has NO authentication. $DASH_HOST exposes your full screen-activity history to anyone who can reach that address. Use only on a trusted network (e.g. a tailnet)."
  [[ "$(ask 'Continue with that bind address? (y/N)' n)" == [yY] ]] || die "aborted"
fi
REC_NOTE="$(ask 'Recommendations note path' "$BASE/recommendations.md")"

# ---------------------------------------------------------------- lay down files
say "Installing scripts to $BASE/bin"
mkdir -p "$BASE/bin" "$BASE/logs" "$BASE/days" "$BASE/notes" "$BASE/public"
cp "$SRC"/aggregate.py "$SRC"/build-dashboard.py "$SRC"/serve.py \
   "$SRC"/capture-loop.sh "$SRC"/nightly-analysis.sh "$BASE/bin/"
chmod +x "$BASE/bin/capture-loop.sh" "$BASE/bin/nightly-analysis.sh"
ln -sf "../dashboard.html" "$BASE/public/dashboard.html"
ln -sf "dashboard.html"    "$BASE/public/index.html"
ok "scripts installed"

# categories.yaml — user data, never clobber an edited one
if [[ -f "$BASE/bin/categories.yaml" ]]; then
  ok "categories.yaml exists — left as-is"
else
  cp "$SRC/categories.example.yaml" "$BASE/bin/categories.yaml"
  ok "categories.yaml seeded from example (edit it to match your apps/domains)"
fi

# config.yaml
if [[ -f "$BASE/config.yaml" ]]; then
  ok "config.yaml exists — left as-is"
else
  printf 'recommendations_note: %s\n' "$REC_NOTE" > "$BASE/config.yaml"
  ok "config.yaml written"
fi

# the skill itself
mkdir -p "$CLAUDE_SKILLS"
cp "$SKILL_DIR/SKILL.md" "$CLAUDE_SKILLS/SKILL.md"
ok "SKILL.md installed to ~/.claude/skills/screenwatch"

# ---------------------------------------------------------------- build the app
say "Building the capture app (TCC anchor)"
mkdir -p "$APP/Contents/MacOS"
cc -O2 -o "$APP/Contents/MacOS/screenwatch" "$SRC/app-launcher.c" || die "compile failed"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.screenwatch</string>
  <key>CFBundleName</key><string>Screenwatch</string>
  <key>CFBundleExecutable</key><string>screenwatch</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>NSAppleEventsUsageDescription</key>
  <string>Screenwatch reads the frontmost app, window title, and browser URL to log activity.</string>
</dict></plist>
PLIST
codesign --force --sign - "$APP" 2>/dev/null && ok "compiled + ad-hoc signed" || warn "codesign failed (app still runs)"

# ---------------------------------------------------------------- launchd
say "Installing launchd jobs"
mkdir -p "$AGENTS"
render() {  # template -> installed plist, substituting HOME and label
  sed -e "s#__HOME__#$HOME#g" -e "s#__LABEL__#$2#g" "$SKILL_DIR/launchd/$1" > "$AGENTS/$2.plist"
}
render capture.plist.template   "$LABEL_PREFIX"
render analysis.plist.template  "$LABEL_PREFIX.analysis"
render dashboard.plist.template "$LABEL_PREFIX.dashboard"

# non-default host/port -> inject env into the dashboard job
if [[ "$DASH_HOST" != "127.0.0.1" || "$DASH_PORT" != "8484" ]]; then
  /usr/libexec/PlistBuddy \
    -c "Add :EnvironmentVariables dict" \
    -c "Add :EnvironmentVariables:SCREENWATCH_HOST string $DASH_HOST" \
    -c "Add :EnvironmentVariables:SCREENWATCH_PORT string $DASH_PORT" \
    "$AGENTS/$LABEL_PREFIX.dashboard.plist" >/dev/null 2>&1 || true
fi
ok "3 launchd jobs written to ~/Library/LaunchAgents"

# ---------------------------------------------------------------- permissions
say "Screen Recording + Automation permission (one-time, manual)"
cat <<EOF
  macOS will NOT let a script grant these. The capture app needs:
    1. Screen Recording  — to save screenshots
    2. Automation        — to read the frontmost window title / browser URL

  The first time the daemon runs, macOS pops a prompt for each. If you miss them:
    System Settings > Privacy & Security > Screen Recording  -> enable "Screenwatch"
    System Settings > Privacy & Security > Automation        -> enable "Screenwatch"
EOF
open "$APP" 2>/dev/null || true
read -r -p "  Press Enter once you've allowed both (or to continue and grant later) "

# ---------------------------------------------------------------- start
say "Starting services"
boot() { launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
         launchctl bootstrap "gui/$(id -u)" "$AGENTS/$1.plist" 2>/dev/null \
           && ok "loaded $1" || warn "could not load $1 (check the plist)"; }
boot "$LABEL_PREFIX"
boot "$LABEL_PREFIX.dashboard"
launchctl enable "gui/$(id -u)/$LABEL_PREFIX.analysis" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENTS/$LABEL_PREFIX.analysis.plist" 2>/dev/null || true
ok "nightly analysis scheduled (04:30)"

# ---------------------------------------------------------------- verify
say "Verifying"
sleep 8   # let a couple capture ticks land
TODAY="$(date +%F)"
if [[ -s "$BASE/days/$TODAY/log.jsonl" ]]; then
  ok "capture is writing $BASE/days/$TODAY/log.jsonl"
else
  warn "no ticks yet. If macOS is still waiting on the Screen Recording grant, allow it, then: launchctl kickstart -k gui/$(id -u)/$LABEL_PREFIX"
fi

if curl -fsS "http://$DASH_HOST:$DASH_PORT/" >/dev/null 2>&1; then
  ok "dashboard responding at http://$DASH_HOST:$DASH_PORT/"
else
  warn "dashboard not answering yet (needs at least one day of data to build)."
fi

if python3 "$BASE/bin/aggregate.py" "$TODAY" --base "$BASE" >/dev/null 2>&1; then
  ok "aggregate.py runs against today's log"
fi

command -v shellcheck >/dev/null && shellcheck "$SRC/capture-loop.sh" "$SRC/nightly-analysis.sh" >/dev/null 2>&1 \
  && ok "shellcheck clean" || true

say "Done."
echo "  Dashboard : http://$DASH_HOST:$DASH_PORT/"
echo "  In Claude : /screenwatch status   ·   /screenwatch analyze $TODAY"
echo "  Buckets   : edit $BASE/bin/categories.yaml, then rebuild:"
echo "              python3 $BASE/bin/build-dashboard.py"
