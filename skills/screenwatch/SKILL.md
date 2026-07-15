---
name: screenwatch
description: Analyze the screenwatch capture archive — build daily activity notes, track recurring workflow inefficiencies, and suggest optimizations. Use for "/screenwatch analyze [date]", "/screenwatch optimize [focus]", "/screenwatch status", or any question about what the user was doing on a past day / how to improve their workflow based on observed behavior.
---

# Screenwatch analysis

## Data layout
- `~/screenwatch/days/YYYY-MM-DD/log.jsonl` — one line per tick: `{t, epoch, app, window, url, img}`. `img: true` means a screenshot `HH-MM-SS.webp` (or `.jpg`) exists in the same folder. **Kept forever** — this is the durable record; only the frames are pruned.
- `~/screenwatch/days/YYYY-MM-DD/*.webp|*.jpg` — ~1568px-wide screenshots (pruned after 30 days).

**`ticks × 5` is NOT a duration.** The tick is *nominally* 5s, but the loop is `sleep 5` **plus** a `screencapture` and two `osascript` calls, so its real period is **~5.64s** (measured). Multiplying ticks by 5 silently loses ~11% of the day — 78 minutes on 2026-07-10. It has already produced one wrong note (2026-07-09 reported "9h 15m", which is exactly `6,659 × 5s`; the true figure is 10h 27m). Never do this arithmetic yourself — see below.

**Frames are not evenly spaced — never read activity level off frame density.** The capture loop writes an image only when `app|window|url` *changes*, or every 6th tick as a keyframe. So a steady 30s spacing means "same window for a while", not "idle"; 5s spacing means rapid app switching. Only ~35% of ticks carry a frame. Time and attention come from `log.jsonl`; frames are evidence for *what* was on screen, never for *how much* was happening.

**A gap in `log.jsonl` is an idle skip, not a crash.** The loop skips a tick entirely when there has been no keyboard/mouse input for 90s (`IDLE_SKIP_SECS`), writing neither frame nor log row. Gaps therefore mean "away from the machine". Report them as such. The daemon stopping is a *different* event and looks different: the log ends and never resumes.
- `~/screenwatch/notes/YYYY-MM-DD.md` — analysis output (kept forever; the durable record).
- `~/screenwatch/observations.md` — rolling ledger of recurring inefficiencies with occurrence counts.

(On Windows the base is `%USERPROFILE%\screenwatch\` and `url` is usually empty — window titles carry the page title instead.)

## The numbers come from `aggregate.py`. You do not compute them.

```bash
python3 ~/screenwatch/bin/aggregate.py YYYY-MM-DD            # JSON
python3 ~/screenwatch/bin/aggregate.py YYYY-MM-DD --pretty   # human summary
```

**Use its output verbatim. Never compute a duration, total, switch count, or gap yourself** — not in your head, not with an ad-hoc python one-liner, not by subtracting two frame filenames. If a number you need is not in the JSON, **add it to `aggregate.py`**; do not derive it inline.

This is not a style preference, it is the fix for a real defect. This skill used to say *what* to compute but not *how*, so every nightly run reinvented the arithmetic — and they disagreed. 2026-07-09's note used `ticks × 5s` (9h 15m); 2026-07-10's note used something else (11.5h, where `ticks × 5s` would be 10.45h). Two consecutive nights, two different methods, notes that **cannot be compared to each other** — which is fatal, because `optimize` gates on a pattern recurring across `count >= 3` *days*. One definition of the math, or the ledger is measuring nothing.

What the JSON gives you:

| Field | Meaning |
|---|---|
| `tracked_secs` | active time. Each tick covers the **real gap to the next tick**, capped at the 90s idle threshold. |
| `idle_secs` | **all** gaps ≥ 90s — the true "away from machine" total. |
| `long_gaps` | the gaps ≥ 5 min — a **subset** of `idle_secs`, the ones worth naming in a timeline. |
| `conserved` | asserts `tracked + idle == wall-clock span`. **If this is ever `false`, stop** — the duration rule has drifted and every other number is suspect. |
| `by_app` / `by_domain` / `by_bucket` | totals. Prefer `by_domain`: see the warning below. |
| `switches`, `switches_per_hr`, `churn_bursts`, `churn_windows` | **app** switches, not window-retitles. |
| `blocks`, `long_gaps`, `churn_windows` | timestamped, so you can pick frames without recomputing anything. |

`idle_secs` and `long_gaps` are **different quantities** and must never be conflated or presented as one "idle" figure. On 2026-07-10 they are 248 min and 191 min respectively. Say which one you mean.

**Report time by DOMAIN, not by app.** An app name is a window, not an activity. Arc was the biggest "app" at 10h39m across the first three days, but 70% of that was YouTube + a Kajabi course + GoHighLevel — three unrelated kinds of time wearing one name. A per-app total is nearly meaningless on its own; `by_domain` is the answer. `by_bucket` (from `bin/categories.yaml`) is the summary.

## Cost discipline (important)
Metadata first, vision second. `aggregate.py` answers most questions (what apps, how long, how often switching, which URLs) for near-zero tokens — it is plain Python and never enters your context. Only Read screenshots where metadata can't tell the story, and read them individually. Target 10–30 images per analyzed day, never all of them. Never read raw JSONL into context.

## `analyze [date]` (default: yesterday if it has data, else today)

**Every time in the note must trace to a tick, and every number must come from `aggregate.py`.** A frame filename is *not* a timestamp for a session boundary — `17-11-21.jpg` proves only that something was on screen at 17:11:21. If a stated time does not equal a value in the JSON, it is wrong. Cross-check the finished note against the timeline table: an end time in prose that contradicts the table means the prose is the error.

Never assert that capture, work, or a call "stopped" at a time unless the log shows it. Check what follows: ticks after that time disprove a stop.

1. **Aggregate the log**: run `python3 ~/screenwatch/bin/aggregate.py <date>`. Confirm `"conserved": true`. That is the whole aggregation step — `blocks`, per-app/domain/bucket totals, switch rate, and churn bursts are all in the output already.
2. **Pick frames to actually look at**: block transitions, the longest blocks, and churn bursts. Read those screenshots.
3. **Look specifically for inefficiency evidence**: open menus/right-click menus (mouse used where a hotkey exists), manual file-dialog navigation, repeated copy-paste between the same two apps, hand-scrolling long documents for search, dated/suboptimal tooling, undismissed notification piles, re-doing something automatable, manual status-polling loops.
4. **Write `~/screenwatch/notes/YYYY-MM-DD.md`**: a short timeline (activity blocks with times), what was worked on, tool inventory, and an "Inefficiencies observed" list with concrete evidence (frame filenames). Also note *positive* patterns worth keeping. The header line must carry, straight from the JSON: `tracked_secs`, `idle_secs` **and** the `long_gaps` total, labelled distinctly; ticks; and a **time-by-domain** table (a time-by-app table may follow it, never replace it).
5. **Update `~/screenwatch/observations.md`**: `count` is *days observed*, not times seen. For each inefficiency:
   - No matching entry → add one at `count: 1, last: <analyzed date>`.
   - Matching entry whose `last:` is **older** than the analyzed date → increment count, set `last:` to the analyzed date.
   - Matching entry whose `last:` **already equals** the analyzed date → leave `count` untouched; only merge in new frame evidence.

   That last rule is load-bearing: `analyze` is re-runnable, and without it a second pass over the same day inflates counts. `optimize` gates on `count >= 3`, so an inflated ledger manufactures fake "confirmed patterns". `count` must never exceed the number of distinct days in `~/screenwatch/days/`.

   Format:
   `- [count: 3, last: 2026-07-08] Opens X via Spotlight → browser → typing URL; a pinned tab or launcher hotkey would be ~5s faster each time. (Seen: 2026-07-06/14-22-10.webp, ...)`

## `optimize [focus]`
1. Read `observations.md` and the last ~7 days of notes.
2. Entries with count ≥ 3 are confirmed patterns — turn each into a specific recommendation: the exact hotkey, the replacement tool (verify it's current via web search if unsure), or an automation you can build on the spot (shell script, launcher script command, browser extension, scheduled agent).
3. Rank by estimated time saved per week. Present the top 3–5; offer to implement the automatable ones.
4. If `focus` is given (e.g. "browser", "email"), filter to that area.
5. **Log every recommendation** to the recommendations note. Its path is the
   `recommendations_note` value in `~/screenwatch/config.yaml` (default
   `~/screenwatch/recommendations.md`); point it at an Obsidian vault path if you
   keep one. Create the file from the format below if missing. Append a
   `## YYYY-MM-DD` section with one entry per recommendation:
   `- **[status]** Short title — the fix, est. time saved/week, evidence (ledger entry / frames). Status one of: `proposed` | `accepted` | `done` | `rejected`.`
   Never delete or rewrite past entries — update a status in place when it changes (e.g. after implementing a fix, flip to `done`). If the note lives in an Obsidian vault, set `unread: true` and bump `updated:` in the frontmatter on every edit and wikilink tools/concepts (`[[Raycast]]`, `[[Notion]]`); skip that when it is a plain local file.

## `status`
Report whether the capture daemon is running, today's frame count and disk usage, and any recent errors in `~/screenwatch/daemon.log`.
