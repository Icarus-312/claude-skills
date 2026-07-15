#!/bin/bash
# Screenwatch nightly analysis — run by com.screenwatch.analysis launchd job at 04:30.
set -u
: "${HOME:?HOME must be set}"
BASE="${SCREENWATCH_BASE:-$HOME/screenwatch}"
LOG="$BASE/analysis-cron.log"

# Locate the claude CLI without a baked-in username. Override with CLAUDE_BIN.
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
for c in "$HOME/.local/bin/claude" "/opt/homebrew/bin/claude" "/usr/local/bin/claude"; do
  [ -n "$CLAUDE_BIN" ] && break
  [ -x "$c" ] && CLAUDE_BIN="$c"
done
if [ -z "$CLAUDE_BIN" ]; then
  echo "$(date '+%F %T') claude CLI not found; set CLAUDE_BIN" >> "$LOG"; exit 1
fi
echo "=== $(date '+%F %T') nightly analysis start ===" >> "$LOG"

# Skip if yesterday has no data (mini was off / capture paused)
Y=$(date -v-1d +%F)
if [ ! -s "$BASE/days/$Y/log.jsonl" ]; then
  echo "no data for $Y, skipping" >> "$LOG"
  exit 0
fi

# MCP servers write ./logs/ relative to cwd. Running from $BASE puts a
# teamwork-mcp combined.log/error.log at $BASE/logs, where it reads as
# screenwatch's own daemon log. Keep cwd off $BASE.
RUN="$BASE/.run"
mkdir -p "$RUN"
cd "$RUN" || exit 1

# Pass $Y explicitly. Bare "/screenwatch analyze" makes the skill re-derive the
# date, and by 04:30 the capture loop has already created today's folder — so it
# can analyze today's near-empty log instead of the day guarded above.
#
# WARNING: --dangerously-skip-permissions runs Claude unattended with no approval
# prompts, so it can read/write files and run tools on its own. It is scoped to
# the screenwatch analyze skill, but understand you are granting that. Remove the
# flag to be prompted (defeats the point of a nightly cron), or drop this cron
# entirely and run "/screenwatch analyze" by hand.
"$CLAUDE_BIN" -p "/screenwatch analyze $Y" \
  --dangerously-skip-permissions \
  >> "$LOG" 2>&1
rc=$?   # capture immediately: $(date) in the echo below would overwrite $?

# Rebuild the focus dashboard from the full archive. Pure Python, no model in
# the loop, so this costs nothing and cannot fail the analysis above -- it runs
# after rc is captured and its own failure is logged, not propagated.
/usr/bin/env python3 "$BASE/bin/build-dashboard.py" >> "$LOG" 2>&1 \
  || echo "dashboard build FAILED" >> "$LOG"

echo "=== $(date '+%F %T') exit=$rc ===" >> "$LOG"
exit "$rc"
