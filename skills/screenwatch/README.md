# screenwatch

A local, on-device time tracker for macOS. A background daemon samples your
frontmost app, window title, and browser URL every ~5 seconds (plus a compressed
screenshot when the context changes), and a Claude Code skill turns that archive
into daily activity notes, a recurring-inefficiency ledger, and a focus
dashboard. Everything stays on your machine — no account, no cloud, no telemetry.

The core idea: **an app name is not an activity.** "Arc — 6 hours" tells you
nothing; the same browser holds a client call, a course, and YouTube. Screenwatch
buckets time by *domain* and category, so you see where it actually went.

## What you get

- **`/screenwatch analyze [date]`** — a timeline, time-by-domain table, tool
  inventory, and an "inefficiencies observed" list with screenshot evidence.
- **`/screenwatch optimize [focus]`** — turns patterns seen on ≥3 days into
  concrete fixes (a hotkey, a better tool, an automation), ranked by time saved.
- **`/screenwatch status`** — is capture running, today's frame count, disk use.
- **A focus dashboard** at `http://127.0.0.1:8484/` — stacked focus split, a
  per-day timeline, top apps vs top domains, and focus-quality metrics.

All durations come from one file, `aggregate.py` — the single definition of the
math, so the numbers never drift between the skill and the dashboard.

## Prerequisites

- **macOS** (uses `screencapture`, `osascript`, `launchd`) — not portable to
  Linux/Windows.
- **python3** + **PyYAML** (the installer offers to `pip install` it).
- **Xcode Command Line Tools** (`cc`, to compile the tiny capture-app launcher).
- **ffmpeg** with a webp encoder — optional; falls back to `sips` JPEG.
- **claude CLI** — optional; only the 4:30am auto-analysis needs it. Capture and
  the dashboard work without it.

## Install

```bash
cd skills/screenwatch
./install.sh
```

The wizard checks dependencies, asks for your base directory and dashboard
bind address, compiles + ad-hoc-signs `Screenwatch.app`, installs the scripts and
three launchd jobs with your paths, and walks you through the one permission
grant macOS won't let a script do (Screen Recording + Automation). Re-run it any
time to update; it never clobbers your edited `categories.yaml` or `config.yaml`.

## Configure

Edit `~/screenwatch/bin/categories.yaml` to match your apps and domains — it ships
with placeholder buckets, not anyone's real workflow. Rules are ordered,
first-match-wins; anything unmatched shows as `Unsorted` on the dashboard so
misclassified time can't hide. Rebuild after editing:

```bash
python3 ~/screenwatch/bin/build-dashboard.py
```

`~/screenwatch/config.yaml` sets where `/screenwatch optimize` logs its
recommendations (default a local Markdown file; point it at an Obsidian vault
note if you keep one). Environment overrides: `SCREENWATCH_BASE`,
`SCREENWATCH_HOST`, `SCREENWATCH_PORT`, `CLAUDE_BIN`.

## What this skill can access on your machine

Be clear-eyed: this is a screen recorder. Specifically it:

- **Captures screenshots of your entire screen** every time the active
  app/window/URL changes (and one keyframe per ~30s). They are downscaled webp/jpg
  saved under `~/screenwatch/days/<date>/` and **pruned after 30 days**. Whatever
  is on screen — messages, credentials, private docs — is in those frames.
- **Reads the frontmost window title and browser URL** via AppleScript, logged to
  `~/screenwatch/days/<date>/log.jsonl`. **The log is kept forever** (it is small
  and is the record analysis runs on); only the images are pruned.
- **Skips capture after 90s of no keyboard/mouse input**, so idle/away time isn't
  recorded.
- **Serves the dashboard on `127.0.0.1:8484` by default** — reachable only from
  your machine. It has **no authentication**, so binding it to a LAN/tailnet
  address (via `SCREENWATCH_HOST`) exposes your full activity history to anyone
  who can reach that address. The installer warns before letting you do this.
- **Runs the nightly analysis with `claude -p --dangerously-skip-permissions`**
  (only if you have the claude CLI and keep that cron). That runs Claude
  unattended with no approval prompts, scoped to the analyze skill. Remove the
  flag in `nightly-analysis.sh`, or drop the `com.screenwatch.analysis` launchd
  job, to disable it.
- **Sends nothing off your machine.** No network calls except the Claude API when
  *you* (or the optional cron) run an analysis.

To stop and remove everything:

```bash
launchctl bootout gui/$(id -u)/com.screenwatch
launchctl bootout gui/$(id -u)/com.screenwatch.dashboard
launchctl bootout gui/$(id -u)/com.screenwatch.analysis
rm -rf ~/screenwatch ~/Applications/Screenwatch.app \
       ~/Library/LaunchAgents/com.screenwatch*.plist \
       ~/.claude/skills/screenwatch
```

Then remove "Screenwatch" from System Settings > Privacy & Security > Screen
Recording and Automation.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No frames appear | macOS is waiting on the Screen Recording grant. Allow it, then `launchctl kickstart -k gui/$(id -u)/com.screenwatch`. |
| `daemon.log` shows osascript errors | Grant Automation for Screenwatch, or the target browser isn't in `get_url`'s case list (Chrome/Brave/Arc/Edge/Vivaldi/Safari supported). |
| Dashboard 503 / "no build" | Needs at least one day of data. Wait a day or run `python3 ~/screenwatch/bin/build-dashboard.py`. |
| Everything is `Unsorted` | You haven't edited `categories.yaml` to your own apps/domains yet. |
| `conserved: false` in aggregate output | A duration bug — stop and check; every downstream number is suspect. |

## License

MIT — see the repo [LICENSE](../../LICENSE).
