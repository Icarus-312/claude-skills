#!/usr/bin/env python3
"""Build the screenwatch focus dashboard from the metadata archive.

Reads every ~/screenwatch/days/<date>/log.jsonl (plain or .gz), buckets each
tick via categories.yaml, and writes a self-contained dashboard.html.

This file owns PRESENTATION ONLY. Every duration, total, switch count and gap
comes from aggregate.py, which is the single definition of the math -- the same
one the screenwatch skill is required to call. Never compute a time here.

    python3 build-dashboard.py [--base ~/screenwatch] [--days N]
"""

import argparse
import html
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aggregate import (  # noqa: E402  -- the math, one definition, no drift
    TICK, UNSORTED,
    load_rules, read_day, build_blocks, app_runs, churn_windows,
)

# Ordered (light, dark) palette assigned to buckets by their position in
# categories.yaml, so ANY set of bucket names renders -- the colors are not keyed
# to specific names. Categorical slots in the palette's fixed CVD-safe order;
# Unsorted is always gray, the absence of an identity rather than another slot.
# Validated with the dataviz validator: the 5 identity slots PASS in both modes.
# Light aqua/yellow are sub-3:1 and dark worst-adjacent CVD sits in the 10.3 floor
# band, so both modes owe secondary encoding -- hence direct labels on every
# bucket, 2px gaps between segments, and the table view at the bottom. Buckets
# past the 5th cycle the palette; give a 6th bucket a distinct name in the table.
PALETTE = [
    ("#2a78d6", "#3987e5"),   # slot 1  blue
    ("#1baf7a", "#199e70"),   # slot 2  green
    ("#eda100", "#c98500"),   # slot 3  amber
    ("#008300", "#008300"),   # slot 4  deep green
    ("#4a3aa7", "#9085e9"),   # slot 5  violet
]
GRAY = ("#898781", "#898781")
UNSORTED = "Unsorted"


def color_map(order):
    """{bucket: (light, dark)} for the buckets actually present, in order."""
    m, i = {}, 0
    for b in order:
        if b == UNSORTED:
            m[b] = GRAY
        else:
            m[b] = PALETTE[i % len(PALETTE)]
            i += 1
    return m


def color_vars(order, dark):
    """The `--c-<slug>` custom-property declarations for one theme."""
    cm = color_map(order)
    bar = cm.get(next((b for b in order if b != UNSORTED), None), PALETTE[0])
    decls = [f"--c-{slug(b)}:{pair[1 if dark else 0]}" for b, pair in cm.items()]
    decls.append(f"--c-bar:{bar[1 if dark else 0]}")
    return "; ".join(decls) + ";"


# ---------------------------------------------------------------- svg helpers

def esc(s):
    return html.escape(str(s), quote=True)


def fmt_hm(secs):
    h, m = int(secs // 3600), int((secs % 3600) // 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def fmt_h(secs):
    return f"{secs / 3600:.1f}h"


def tip(text):
    return f' data-tip="{esc(text)}"'


# ---------------------------------------------------------------- render

def stacked_bar(bucket_secs, order, total, width=980, height=46):
    """100% stacked bar: the headline 'where does it all go'. 2px surface gaps."""
    if not total:
        return ""
    parts, x = [], 0.0
    for b in order:
        s = bucket_secs.get(b, 0)
        if not s:
            continue
        w = (s / total) * width
        pct = s / total * 100
        parts.append(
            f'<rect class="seg" x="{x:.1f}" y="0" width="{max(w - 2, 1):.1f}" height="{height}" rx="4" '
            f'fill="var(--c-{slug(b)})"{tip(f"{b} — {fmt_hm(s)} ({pct:.0f}%)")}/>'
        )
        x += w
    return (f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Share of tracked time by focus bucket">{"".join(parts)}</svg>')


def ranked_bars(items, total, width=500, row=27, label_w=150, value_w=62):
    """Horizontal ranked bars with a direct value label on every row.

    The viewBox width must be close to the element's real rendered CSS width or
    the uniform SVG scale shrinks the type with it: a 980-unit box inside a
    ~500px column renders 12px labels at ~6px. These sit two-up, so the box is
    sized for the column, not the page.
    """
    if not items:
        return ""
    plot = width - label_w - value_w
    mx = max(v for _, v in items) or 1
    out, h = [], row * len(items)
    for i, (name, secs) in enumerate(items):
        y = i * row
        w = (secs / mx) * plot
        pct = (secs / total * 100) if total else 0
        out.append(
            f'<text class="rowlab" x="{label_w - 10}" y="{y + row/2}" text-anchor="end">{esc(name[:24])}</text>'
            f'<rect class="seg" x="{label_w}" y="{y + 4}" width="{max(w,2):.1f}" height="{row - 11}" rx="4" '
            f'fill="var(--c-bar)"{tip(f"{name} — {fmt_hm(secs)} ({pct:.1f}% of tracked)")}/>'
            f'<text class="rowval" x="{label_w + w + 8:.1f}" y="{y + row/2}">{fmt_hm(secs)}</text>'
        )
    return (f'<svg class="chart" viewBox="0 0 {width} {h}" role="img" '
            f'aria-label="Ranked time by name">{"".join(out)}</svg>')


def day_timeline(days, order, width=980, row=34, gap=8, lab=54):
    """One 24h band per day. Colored by bucket; idle renders as a hole (surface)."""
    if not days:
        return ""
    plot = width - lab - 8
    h = len(days) * (row + gap)
    out = []

    for hh in range(0, 25, 3):                       # hour grid + ticks
        x = lab + (hh / 24) * plot
        out.append(f'<line class="grid" x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h - gap}"/>')
        out.append(f'<text class="axis" x="{x:.1f}" y="{h}" text-anchor="middle">{hh:02d}</text>')

    for i, d in enumerate(days):
        y = i * (row + gap)
        midnight = d["midnight"]
        out.append(f'<text class="rowlab" x="{lab - 12}" y="{y + row/2}" text-anchor="end">{d["date"][5:]}</text>')
        out.append(f'<rect class="track" x="{lab}" y="{y}" width="{plot}" height="{row}" rx="5"/>')
        for b in d["blocks"]:
            x0 = ((b["start"] - midnight) / 86400) * plot
            w = ((b["end"] - b["start"]) / 86400) * plot
            if w <= 0:
                continue
            when = datetime.fromtimestamp(b["start"]).strftime("%H:%M")
            what = b["url"] or b["window"] or b["app"]
            head = f'{when} · {b["app"]} · {b["bucket"]} · {fmt_hm(b["secs"])}'
            body = what[:90]
            # class="tseg", NOT "seg": the 2px surface stroke that separates
            # stacked-bar segments would completely paint over a sliver this
            # thin (a 40s block is under 1px wide at this scale), erasing the
            # very activity the band exists to show. Dense marks get no stroke.
            out.append(
                f'<rect class="tseg" x="{lab + x0:.2f}" y="{y}" width="{max(w, 0.8):.2f}" height="{row}" '
                f'fill="var(--c-{slug(b["bucket"])})"'
                f'{tip(head + chr(10) + body)}/>'
            )
    return (f'<svg class="chart" viewBox="0 0 {width} {h + 14}" role="img" '
            f'aria-label="Per-day timeline colored by focus bucket">{"".join(out)}</svg>')


def slug(b):
    return b.lower().replace(" ", "-")


def legend(order, bucket_secs, total):
    out = []
    for b in order:
        s = bucket_secs.get(b, 0)
        if not s:
            continue
        pct = s / total * 100 if total else 0
        out.append(
            f'<div class="lg"><span class="sw" style="background:var(--c-{slug(b)})"></span>'
            f'<span class="lgname">{esc(b)}</span>'
            f'<span class="lgval">{fmt_h(s)} · {pct:.0f}%</span></div>'
        )
    return f'<div class="legend">{"".join(out)}</div>'


# The charset meta must land in the first 1024 bytes: the HTML parser's encoding
# prescan reads it wherever it sits, which keeps the em-dashes intact when the
# file is opened straight off disk or served by something that omits the header
# (python -m http.server does). Harmless when Artifact sets its own.
PAGE = """<meta charset="utf-8">
<title>Screenwatch — Where My Time Actually Goes</title>
<style>
  :root {{
    --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --line:#c3c2b7; --ring:rgba(11,11,11,.10);
    {cvars_light}
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
      --grid:#2c2c2a; --line:#383835; --ring:rgba(255,255,255,.10);
      {cvars_dark}
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --line:#383835; --ring:rgba(255,255,255,.10);
    {cvars_dark}
  }}
  :root[data-theme="light"] {{
    --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --line:#c3c2b7; --ring:rgba(11,11,11,.10);
    {cvars_light}
  }}
  body {{ background:var(--bg); color:var(--ink); margin:0;
    font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  .wrap {{ max-width:1060px; margin:0 auto; padding:40px 24px 80px; }}
  h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:-.01em; }}
  .sub {{ color:var(--ink2); margin:0 0 28px; font-size:14px; }}
  .card {{ background:var(--surface); border:1px solid var(--ring); border-radius:12px;
    padding:22px 24px; margin-bottom:18px; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted);
    margin:0 0 4px; font-weight:600; }}
  .note {{ color:var(--ink2); font-size:13px; margin:0 0 18px; }}
  .chart {{ width:100%; height:auto; overflow:visible; display:block; }}
  .seg {{ stroke:var(--surface); stroke-width:2; }}
  .tseg {{ shape-rendering:crispEdges; }}
  .track {{ fill:var(--grid); }}
  .grid {{ stroke:var(--grid); stroke-width:1; }}
  .axis, .rowlab, .rowval {{ fill:var(--muted); font-size:12px; dominant-baseline:middle; }}
  .rowlab {{ fill:var(--ink2); }}
  .rowval {{ fill:var(--ink); font-weight:600; font-variant-numeric:tabular-nums; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:8px 22px; margin-top:16px; }}
  .lg {{ display:flex; align-items:center; gap:7px; font-size:13px; }}
  .sw {{ width:11px; height:11px; border-radius:3px; flex:none; }}
  .lgname {{ color:var(--ink); }}
  .lgval {{ color:var(--ink2); font-variant-numeric:tabular-nums; }}
  .hero {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:18px; }}
  .tile {{ flex:1 1 150px; background:var(--surface); border:1px solid var(--ring);
    border-radius:12px; padding:18px 20px; }}
  .tval {{ font-size:28px; font-weight:600; letter-spacing:-.02em; }}
  .tlab {{ color:var(--muted); font-size:12px; text-transform:uppercase;
    letter-spacing:.06em; margin-top:3px; }}
  .tsub {{ color:var(--ink2); font-size:12px; margin-top:6px; }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  @media (max-width:780px) {{ .cols {{ grid-template-columns:1fr; }} }}
  .scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th, td {{ text-align:left; padding:7px 12px 7px 0; border-bottom:1px solid var(--grid);
    white-space:nowrap; }}
  th {{ color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase;
    letter-spacing:.06em; }}
  td.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .callout {{ border-left:3px solid var(--c-learning); padding:2px 0 2px 14px;
    color:var(--ink2); font-size:14px; margin:0; }}
  .callout b {{ color:var(--ink); }}
  #tip {{ position:fixed; pointer-events:none; opacity:0; transition:opacity .1s;
    background:var(--ink); color:var(--bg); padding:7px 10px; border-radius:7px;
    font-size:12px; line-height:1.4; max-width:340px; white-space:pre-line; z-index:9; }}
  footer {{ color:var(--muted); font-size:12px; margin-top:26px; }}
  code {{ font-size:12px; background:var(--grid); padding:1px 5px; border-radius:4px; }}
</style>

<div class="wrap">
  <h1>Where my time actually goes</h1>
  <p class="sub">{span} · {ndays} days · {total} tracked, {idle} idle · built from {ticks:,} metadata ticks</p>

  <div class="hero">{tiles}</div>

  <div class="card">
    <h2>Focus split</h2>
    <p class="note">Share of tracked time. Buckets come from <code>bin/categories.yaml</code> — edit it and rebuild.</p>
    {stack}
    {legend}
  </div>

  {insight}

  <div class="card">
    <h2>Day timeline</h2>
    <p class="note">Each band is one day, midnight to midnight. Gray = idle or machine off — the capture loop skips a tick after 90s of no input, so holes mean away, not crashed.</p>
    <div class="scroll">{timeline}</div>
  </div>

  <div class="cols">
    <div class="card">
      <h2>Top apps</h2>
      <p class="note">What the OS sees. This is the view that misleads.</p>
      <div class="scroll">{apps}</div>
    </div>
    <div class="card">
      <h2>Top domains</h2>
      <p class="note">What you were actually doing.</p>
      <div class="scroll">{domains}</div>
    </div>
  </div>

  <div class="card">
    <h2>Focus quality</h2>
    <p class="note">Screen time is one number; whether it was fragmented is the other. A churn burst is more than 6 app switches inside 2 minutes.</p>
    <div class="scroll">{quality}</div>
  </div>

  <div class="card">
    <h2>Table view</h2>
    <p class="note">Every number above, as text — identity never rests on color alone.</p>
    <div class="scroll">{table}</div>
  </div>

  <footer>Generated {now} from <code>~/screenwatch/days/*/log.jsonl</code> · time is measured tick-to-tick (the loop's real period is ~5.6s, not the nominal {tick}s) and never from frame count · a gap ≥ 90s is idle, not a crash · rebuild with <code>python3 bin/build-dashboard.py</code></footer>
</div>

<div id="tip"></div>
<script>
  const tipEl = document.getElementById('tip');
  document.addEventListener('mouseover', e => {{
    const t = e.target.closest('[data-tip]');
    if (!t) return;
    tipEl.textContent = t.getAttribute('data-tip');
    tipEl.style.opacity = 1;
  }});
  document.addEventListener('mousemove', e => {{
    if (tipEl.style.opacity === '0' || !tipEl.style.opacity) return;
    const p = 14, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    let x = e.clientX + p, y = e.clientY + p;
    if (x + w > innerWidth - 8) x = e.clientX - w - p;
    if (y + h > innerHeight - 8) y = e.clientY - h - p;
    tipEl.style.left = x + 'px'; tipEl.style.top = y + 'px';
  }});
  document.addEventListener('mouseout', e => {{
    if (e.target.closest('[data-tip]')) tipEl.style.opacity = 0;
  }});
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.expanduser("~/screenwatch"))
    ap.add_argument("--days", type=int, default=0, help="only the last N days (0 = all)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    base = os.path.expanduser(a.base)
    rules, order = load_rules(os.path.join(base, "bin", "categories.yaml"))
    out_path = a.out or os.path.join(base, "dashboard.html")

    day_dirs = sorted(
        d for d in os.listdir(os.path.join(base, "days"))
        if os.path.isdir(os.path.join(base, "days", d))
    )
    if a.days:
        day_dirs = day_dirs[-a.days:]

    days = []
    bucket_secs = Counter()
    app_secs = Counter()
    dom_secs = Counter()
    total_secs = idle_secs = 0
    total_ticks = switches = bursts = 0
    app_to_domains = defaultdict(Counter)

    for d in day_dirs:
        rows = read_day(d, base)
        if not rows:
            continue

        blocks, idles = build_blocks(rows, rules)
        runs = app_runs(blocks)
        tracked = sum(b["secs"] for b in blocks)
        d_idle = sum(i["secs"] for i in idles)
        d_bursts = len(churn_windows(runs))
        longest = max((r["secs"] for r in runs), default=0)

        for b in blocks:
            bucket_secs[b["bucket"]] += b["secs"]
            app_secs[b["app"]] += b["secs"]
            dom_secs[b["domain"]] += b["secs"]
            if b["url"]:
                app_to_domains[b["app"]][b["domain"]] += b["secs"]

        midnight = int(datetime.fromtimestamp(rows[0]["epoch"])
                       .replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        span = rows[-1]["epoch"] - rows[0]["epoch"] + TICK
        days.append({
            "date": d, "blocks": blocks, "midnight": midnight,
            "tracked": tracked, "idle": d_idle, "span": span,
            "switches": max(len(runs) - 1, 0), "bursts": d_bursts, "longest": longest,
            "first": rows[0]["epoch"], "last": rows[-1]["epoch"],
        })
        total_secs += tracked
        idle_secs += d_idle
        total_ticks += len(rows)
        switches += max(len(runs) - 1, 0)
        bursts += d_bursts

    if not days:
        sys.exit("no data in " + os.path.join(base, "days"))

    # ---- hero tiles
    top_bucket, top_bucket_secs = bucket_secs.most_common(1)[0]
    work = sum(bucket_secs.get(b, 0) for b in ("Client Ops", "Building"))
    hrs = total_secs / 3600
    tiles = "".join([
        f'<div class="tile"><div class="tval">{hrs:.1f}h</div><div class="tlab">Tracked</div>'
        f'<div class="tsub">{fmt_h(total_secs / len(days))} / day avg</div></div>',
        f'<div class="tile"><div class="tval">{work / total_secs * 100:.0f}%</div>'
        f'<div class="tlab">Client Ops + Building</div>'
        f'<div class="tsub">{fmt_h(work)} of {fmt_h(total_secs)}</div></div>',
        f'<div class="tile"><div class="tval">{top_bucket_secs / 3600:.1f}h</div>'
        f'<div class="tlab">Biggest bucket — {esc(top_bucket)}</div>'
        f'<div class="tsub">{top_bucket_secs / total_secs * 100:.0f}% of tracked</div></div>',
        f'<div class="tile"><div class="tval">{switches / hrs:.0f}</div>'
        f'<div class="tlab">Switches / hour</div>'
        f'<div class="tsub">{bursts} churn bursts</div></div>',
    ])

    # ---- the app-vs-domain callout: the whole reason this dashboard exists
    insight = ""
    if app_secs:
        big_app, big_app_secs = app_secs.most_common(1)[0]
        inner = app_to_domains.get(big_app)
        if inner and big_app_secs:
            top3 = inner.most_common(3)
            frag = ", ".join(f"<b>{esc(n)}</b> {fmt_hm(s)}" for n, s in top3)
            covered = sum(s for _, s in top3)
            insight = (
                '<div class="card"><h2>Why app time lies</h2>'
                f'<p class="callout"><b>{esc(big_app)}</b> is your biggest app at '
                f'<b>{fmt_hm(big_app_secs)}</b> — but that is a window, not an activity. '
                f'Inside it: {frag}. Those three alone are {covered / big_app_secs * 100:.0f}% '
                f'of {esc(big_app)}, and they are not the same kind of time. '
                'The app row tells you nothing; the domain row is the answer.</p></div>'
            )

    # ---- quality table
    q = ['<table><tr><th>Day</th><th class="n">Tracked</th><th class="n">Idle</th>'
         '<th class="n">Switches</th><th class="n">Sw/hr</th><th class="n">Churn bursts</th>'
         '<th class="n">Longest block</th></tr>']
    for d in days:
        h = d["tracked"] / 3600 or 1
        q.append(
            f'<tr><td>{d["date"]}</td><td class="n">{fmt_hm(d["tracked"])}</td>'
            f'<td class="n">{fmt_hm(d["idle"])}</td><td class="n">{d["switches"]}</td>'
            f'<td class="n">{d["switches"] / h:.0f}</td><td class="n">{d["bursts"]}</td>'
            f'<td class="n">{fmt_hm(d["longest"])}</td></tr>'
        )
    q.append("</table>")

    # ---- table view (accessibility relief for the sub-3:1 light hues)
    t = ['<table><tr><th>Bucket</th><th class="n">Time</th><th class="n">Share</th>'
         '<th>Top domains / apps in it</th></tr>']
    bucket_doms = defaultdict(Counter)
    for d in days:
        for b in d["blocks"]:
            bucket_doms[b["bucket"]][b["domain"]] += b["secs"]
    for b in order:
        s = bucket_secs.get(b, 0)
        if not s:
            continue
        tops = ", ".join(f"{esc(n)} ({fmt_hm(v)})" for n, v in bucket_doms[b].most_common(4))
        t.append(
            f'<tr><td>{esc(b)}</td><td class="n">{fmt_hm(s)}</td>'
            f'<td class="n">{s / total_secs * 100:.1f}%</td><td>{tops}</td></tr>'
        )
    t.append("</table>")

    page = PAGE.format(
        span=f'{days[0]["date"]} → {days[-1]["date"]}',
        ndays=len(days),
        total=fmt_h(total_secs),
        idle=fmt_h(idle_secs),
        ticks=total_ticks,
        tiles=tiles,
        stack=stacked_bar(bucket_secs, order, total_secs),
        legend=legend(order, bucket_secs, total_secs),
        insight=insight,
        timeline=day_timeline(days, order),
        apps=ranked_bars(app_secs.most_common(10), total_secs),
        domains=ranked_bars(dom_secs.most_common(10), total_secs),
        quality="".join(q),
        table="".join(t),
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        tick=TICK,
        cvars_light=color_vars(order, dark=False),
        cvars_dark=color_vars(order, dark=True),
    )

    with open(out_path, "w") as f:
        f.write(page)

    print(f"wrote {out_path}")
    print(f"  {len(days)} days · {fmt_h(total_secs)} tracked · {fmt_h(idle_secs)} idle · {total_ticks:,} ticks")
    for b in order:
        if bucket_secs.get(b):
            print(f"  {b:<12} {fmt_h(bucket_secs[b]):>7}  {bucket_secs[b]/total_secs*100:5.1f}%")


if __name__ == "__main__":
    main()
