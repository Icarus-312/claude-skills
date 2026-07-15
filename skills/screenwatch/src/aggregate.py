#!/usr/bin/env python3
"""The screenwatch math. One definition, used by everything.

    python3 aggregate.py 2026-07-10          # JSON to stdout
    python3 aggregate.py 2026-07-10 --pretty # human-readable summary

Why this file exists
--------------------
SKILL.md used to say *what* to compute but not *how*, so every nightly analysis
run reinvented the arithmetic. It shows: the 2026-07-09 note reports 9h15m
tracked (= ticks x 5s, exactly), and the 2026-07-10 note reports 11.5h on the
same kind of data (ticks x 5s would be 10.45h). Two consecutive nights, two
different methods, notes that cannot be compared to each other -- which is fatal
for a tool whose whole job is spotting patterns *across* days, and whose
`observations.md` ledger gates recommendations on `count >= 3` days.

So the model no longer does arithmetic. It calls this.

The duration rule
-----------------
A tick's duration is the REAL gap to the next tick, not the nominal TICK
constant. The capture loop is `sleep 5` plus a screencapture and two osascript
calls, so its true period is ~5.64s (measured). Multiplying ticks by 5 loses
~11% of the day (78 minutes on 2026-07-10) and leaves that time belonging to
nobody.

A gap >= IDLE_GAP is the loop's away-from-machine skip: the tick before it is
credited only the nominal TICK and the remainder becomes idle. An idle gap is
never absorbed into the block preceding it, or a machine left untouched for an
hour reads as an hour of deep focus.

Together those two rules make `tracked + idle == wall-clock span` exactly, so no
time can silently vanish. `conserved` in the output asserts it every run.
"""

import argparse
import fnmatch
import gzip
import json
import os
import sys
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

TICK = 5            # nominal seconds per tick (INTERVAL in capture-loop.sh).
                    # NOT a duration -- see the module docstring. Used only to
                    # cap the tick that precedes an idle gap.
IDLE_GAP = 90       # >= this many seconds between ticks == away (IDLE_SKIP_SECS)
CHURN_WINDOW = 120  # seconds
CHURN_SWITCHES = 6  # more than this many app switches in the window == burst
LONG_GAP = 300      # gaps >= 5 min are the ones worth naming in a timeline

UNSORTED = "Unsorted"
BASE = os.path.expanduser("~/screenwatch")


# ---------------------------------------------------------------- bucketing

def load_rules(path=None):
    """Ordered bucket rules from categories.yaml. Returns (rules, bucket_order)."""
    path = path or os.path.join(BASE, "bin", "categories.yaml")
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML required: python3 -m pip install pyyaml")
    with open(path) as f:
        doc = yaml.safe_load(f)
    rules = doc.get("buckets", [])
    order, seen = [], set()
    for r in rules:
        if r["bucket"] not in seen:
            seen.add(r["bucket"])
            order.append(r["bucket"])
    order.append(UNSORTED)
    return rules, order


def _match(pattern, value):
    """Case-insensitive equality, with '*' as a wildcard."""
    if not value:
        return False
    p, v = pattern.lower(), value.lower()
    return fnmatch.fnmatch(v, p) if "*" in p else p == v


def classify(rules, app, domain, title):
    """First matching rule wins. A rule with several keys requires all of them."""
    for r in rules:
        if "app" in r and not any(_match(p, app) for p in r["app"]):
            continue
        if "domain" in r and not any(_match(p, domain) for p in r["domain"]):
            continue
        if "title" in r and not any(p.lower() in (title or "").lower() for p in r["title"]):
            continue
        if any(k in r for k in ("app", "domain", "title")):
            return r["bucket"]
    return UNSORTED


# ---------------------------------------------------------------- loading

def host_of(url):
    if not url:
        return ""
    try:
        return urlparse(url).netloc
    except ValueError:
        return ""


def read_day(date, base=None):
    """Load one day's ticks, sorted. Handles log.jsonl and log.jsonl.gz."""
    base = base or BASE
    p = os.path.join(base, "days", date, "log.jsonl")
    if not os.path.exists(p):
        p += ".gz"
    if not os.path.exists(p):
        return []
    opener = gzip.open if p.endswith(".gz") else open
    rows = []
    with opener(p, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # a torn last line during a live write
    rows.sort(key=lambda r: r["epoch"])
    return rows


# ---------------------------------------------------------------- the math

def build_blocks(rows, rules):
    """Collapse ticks into activity blocks. Returns (blocks, idles).

    See the module docstring for the duration rule. A block breaks on any change
    of app|window|url, and also on an idle gap.
    """
    blocks, idles = [], []
    cur = None

    for i, r in enumerate(rows):
        app = r.get("app") or ""
        win = r.get("window") or ""
        url = r.get("url") or ""
        dom = host_of(url)
        key = (app, win, url)

        gap = rows[i + 1]["epoch"] - r["epoch"] if i + 1 < len(rows) else TICK
        idle_after = gap >= IDLE_GAP
        dur = TICK if idle_after else max(gap, 1)

        if cur and cur["key"] == key:
            cur["ticks"] += 1
            cur["secs"] += dur
            cur["end"] = r["epoch"] + dur
        else:
            if cur:
                blocks.append(cur)
            cur = {
                "key": key, "app": app, "window": win, "url": url,
                "domain": dom or app,
                "bucket": classify(rules, app, dom, win),
                "start": r["epoch"], "end": r["epoch"] + dur,
                "ticks": 1, "secs": dur,
            }

        if idle_after:
            blocks.append(cur)
            cur = None
            idles.append({"start": r["epoch"] + TICK,
                          "end": rows[i + 1]["epoch"],
                          "secs": gap - TICK})

    if cur:
        blocks.append(cur)
    return blocks, idles


def app_runs(blocks):
    """Merge consecutive blocks of the same app.

    A *block* breaks whenever app|window|url changes -- including a window merely
    retitling itself. Claude Code rewrites ghostty's title as it works, and every
    browser tab change is a new block; counting those as context switches gives
    ~1500 "switches" a day (one per 26s), which is a status line updating, not a
    context switch. A switch is a change of APP. Idle breaks a run: coming back
    to the same app is a fresh run, not a continuation of the one you left.
    """
    runs = []
    for b in blocks:
        if runs and runs[-1]["app"] == b["app"] and runs[-1]["end"] == b["start"]:
            runs[-1]["end"] = b["end"]
            runs[-1]["secs"] += b["secs"]
        else:
            runs.append({"app": b["app"], "start": b["start"],
                         "end": b["end"], "secs": b["secs"]})
    return runs


def churn_windows(runs):
    """Non-overlapping CHURN_WINDOW spans holding > CHURN_SWITCHES app switches."""
    starts = [r["start"] for r in runs[1:]]        # each run boundary is one switch
    out, used_until = [], -1
    for i, s in enumerate(starts):
        if s < used_until:
            continue
        j = i
        while j < len(starts) and starts[j] - s <= CHURN_WINDOW:
            j += 1
        if (j - i) > CHURN_SWITCHES:
            out.append({"start": s, "switches": j - i})
            used_until = s + CHURN_WINDOW
    return out


def app_pairs(runs):
    """Ordered A -> B app transitions, most frequent first.

    This is the evidence behind the recurring 'ferrying' inefficiencies (copying
    a link from one app into another, mid-call scrambles). It lives here rather
    than being re-derived by hand in each analysis -- deriving it inline is the
    exact defect this module exists to prevent.
    """
    pairs = Counter()
    for a, b in zip(runs, runs[1:]):
        if a["app"] != b["app"]:
            pairs[f'{a["app"]} -> {b["app"]}'] += 1
    return [{"pair": p, "n": n} for p, n in pairs.most_common(15)]


def short_bounces(runs, limit=30):
    """App runs shorter than `limit` seconds: touched an app and immediately left.

    A pile of these is what a 'scramble' actually looks like in the data.
    """
    b = [r for r in runs if r["secs"] < limit]
    return {
        "count": len(b),
        "secs": sum(r["secs"] for r in b),
        "top_apps": [{"name": n, "n": c} for n, c in
                     Counter(r["app"] for r in b).most_common(8)],
    }


# ---------------------------------------------------------------- assembly

def hhmmss(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M:%S")


def hhmm(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


def aggregate(date, base=None, rules=None):
    """Every number the skill or the dashboard is allowed to state, computed once."""
    base = base or BASE
    if rules is None:
        rules, _ = load_rules()

    rows = read_day(date, base)
    if not rows:
        return None

    blocks, idles = build_blocks(rows, rules)
    runs = app_runs(blocks)
    churn = churn_windows(runs)

    tracked = sum(b["secs"] for b in blocks)
    idle = sum(i["secs"] for i in idles)
    span = rows[-1]["epoch"] - rows[0]["epoch"] + TICK

    by_app, by_domain, by_bucket = Counter(), Counter(), Counter()
    for b in blocks:
        by_app[b["app"]] += b["secs"]
        by_domain[b["domain"]] += b["secs"]
        by_bucket[b["bucket"]] += b["secs"]

    longest = max(runs, key=lambda r: r["secs"]) if runs else None
    hrs = tracked / 3600 or 1

    return {
        "date": date,
        "first_tick": hhmmss(rows[0]["epoch"]),
        "last_tick": hhmmss(rows[-1]["epoch"]),
        "ticks": len(rows),
        "frames": sum(1 for r in rows if r.get("img")),

        "tracked_secs": tracked,
        "idle_secs": idle,                 # ALL gaps >= 90s: the true "away" total
        "span_secs": span,
        # Asserts tracked + idle == wall-clock span. If this is ever false the
        # duration rule has drifted and every number below is suspect.
        "conserved": abs(span - (tracked + idle)) <= 1,

        "by_app": [{"name": n, "secs": s} for n, s in by_app.most_common()],
        "by_domain": [{"name": n, "secs": s} for n, s in by_domain.most_common()],
        "by_bucket": [{"name": n, "secs": s} for n, s in by_bucket.most_common()],

        "switches": max(len(runs) - 1, 0),          # APP switches, not block breaks
        "switches_per_hr": round((len(runs) - 1) / hrs),
        "churn_bursts": len(churn),
        "churn_windows": [{"start": hhmmss(c["start"]), "switches": c["switches"]}
                          for c in churn],
        # Evidence for the "ferrying" / "scramble" inefficiencies, so the analysis
        # never has to hand-count them from raw ticks.
        "app_pairs": app_pairs(runs),
        "short_bounces": short_bounces(runs),
        "longest_run": ({"app": longest["app"], "secs": longest["secs"],
                         "start": hhmm(longest["start"])} if longest else None),

        # long_gaps is a SUBSET of idle_secs -- the gaps worth naming in a
        # timeline. Do not confuse the two: on 2026-07-10 long_gaps sums to
        # 191 min while idle_secs is 248 min. They are different quantities.
        "long_gaps": [{"start": hhmm(i["start"]), "end": hhmm(i["end"]),
                       "secs": i["secs"]} for i in idles if i["secs"] >= LONG_GAP],

        # Every block, so frames can be chosen without recomputing anything.
        "blocks": [{"start": hhmmss(b["start"]), "app": b["app"],
                    "window": b["window"], "url": b["url"],
                    "secs": b["secs"], "bucket": b["bucket"]} for b in blocks],
    }


def fmt_hm(secs):
    h, m = int(secs // 3600), int((secs % 3600) // 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def main():
    ap = argparse.ArgumentParser(description="Screenwatch aggregation. The math lives here.")
    ap.add_argument("date", help="YYYY-MM-DD")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--pretty", action="store_true", help="human summary instead of JSON")
    a = ap.parse_args()

    d = aggregate(a.date, os.path.expanduser(a.base))
    if not d:
        sys.exit(f"no data for {a.date}")

    if not a.pretty:
        print(json.dumps(d, indent=2))
        return

    print(f"{d['date']}  {d['first_tick']} -> {d['last_tick']}")
    print(f"  {d['ticks']:,} ticks · {d['frames']:,} frames")
    print(f"  tracked {fmt_hm(d['tracked_secs'])} · idle {fmt_hm(d['idle_secs'])} "
          f"· span {fmt_hm(d['span_secs'])} · conserved={d['conserved']}")
    print(f"  {d['switches']} app switches ({d['switches_per_hr']}/hr) · "
          f"{d['churn_bursts']} churn bursts · longest run "
          f"{fmt_hm(d['longest_run']['secs'])} ({d['longest_run']['app']})")
    print("  buckets: " + ", ".join(f"{b['name']} {fmt_hm(b['secs'])}" for b in d["by_bucket"]))
    print("  top apps: " + ", ".join(f"{x['name']} {fmt_hm(x['secs'])}" for x in d["by_app"][:5]))
    print("  top domains: " + ", ".join(f"{x['name']} {fmt_hm(x['secs'])}" for x in d["by_domain"][:5]))
    print(f"  long gaps (>=5m): {len(d['long_gaps'])}, "
          f"{fmt_hm(sum(g['secs'] for g in d['long_gaps']))} "
          f"(subset of idle {fmt_hm(d['idle_secs'])})")


if __name__ == "__main__":
    main()
