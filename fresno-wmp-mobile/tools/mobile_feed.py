#!/usr/bin/env python3
"""Write data/mobile_feed.json — the trimmed feed the phone board reads.

Runs on the Windows box as the last step of a build, after merge.py:

    cd <root>/pipeline
    python3 merge.py
    python3 build.py
    python3 kmz.py
    python3 mobile_feed.py     <-- this

caldata.json is ~1.4 MB because it carries everything the desktop discrepancy
calendar draws: the per-organisation "who says what" block, the line-conflict
table, the coverage stats, the full flag list with sources, and a copy of each
covering clearance inside every tag that rides it. The phone board draws none of
that. It crosses a connector on every cold open, so this projects it down to the
fields the board actually renders.

THIS IS A PROJECTION, NOT A DERIVATION. Every value is copied from caldata.json
unchanged. Nothing is estimated, interpolated, re-derived or filled in. Two
places come close and neither crosses the line:

  - `f` keeps the flag TEXT of flags the pipeline already marked bad or warn,
    verbatim. Flags marked info or ok are dropped because the board has nowhere
    to show them — not because a judgement was made about them.
  - `nr` is 1 when the tag carries a flag whose code is NOT_READY. That is the
    pipeline's own conclusion, restated as a boolean; it is not a fresh reading
    of the readiness columns.

If caldata.json ever stops carrying a field, the board loses it. It is never
guessed at from somewhere else.
"""

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent / "data"
SRC = DATA / "caldata.json"
OUT = DATA / "mobile_feed.json"

FEED_VERSION = 1


def die(msg):
    sys.exit("mobile_feed.py: " + msg)


def tag(x):
    """One tag, short-keyed. Empty fields are omitted rather than written as
    empty strings — across ~1,200 tags that is most of the saving."""
    out = {"n": str(x.get("n", "")), "st": x.get("st", ""), "ln": x.get("ln", "")}
    for short, long in (("mat", "mat"), ("kv", "kv"), ("hq", "hq"),
                        ("sev", "sev"), ("ss", "ss"), ("se", "se")):
        v = x.get(long)
        if v:
            out[short] = v
    # The board shows one work description. caldata carries a short activity
    # code and a longer description; the code is what a foreman reads.
    w = (x.get("act") or x.get("desc") or "").strip()
    if w:
        out["w"] = w
    if x.get("anytime"):
        out["at"] = 1

    flags = x.get("flags") or []
    texts = [f.get("t", "") for f in flags if f.get("sev") in ("bad", "warn") and f.get("t")]
    if texts:
        out["f"] = texts
    if any(f.get("code") == "NOT_READY" for f in flags):
        out["nr"] = 1
    return out


def clearance(c):
    out = {"id": c.get("clearance_id", "")}
    for short, long in (("ty", "type"), ("ln", "line"), ("d0", "start"), ("d1", "end"),
                        ("win", "window"), ("pts", "points"), ("why", "purpose"),
                        ("note", "note")):
        v = c.get(long)
        if v:
            out[short] = v
    st = c.get("structures") or []
    if st:
        out["st"] = st
    if c.get("cancelled"):
        out["x"] = 1
    src = " — ".join(str(v) for v in (c.get("source_subject"), c.get("source_from"),
                                      c.get("source_date")) if v)
    if src:
        out["src"] = src
    return out


def main():
    if not SRC.exists():
        die("no caldata.json at %s — run merge.py first" % SRC)
    try:
        D = json.loads(SRC.read_text(encoding="utf-8"))
    except ValueError as e:
        die("caldata.json will not parse: %s" % e)

    days_in = D.get("days") or {}
    if not days_in:
        die("caldata.json carries no days — refusing to write an empty feed")

    days = {}
    n_tags = 0
    for date in sorted(days_in):
        rows = [tag(x) for x in days_in[date]]
        if rows:
            days[date] = rows
            n_tags += len(rows)

    if not n_tags:
        die("every day in caldata.json is empty — refusing to write a feed with no work "
            "on it, which the board would have to treat as a real answer")

    clrs = [clearance(c) for c in (D.get("clearances") or []) if c.get("start")]

    feed = {
        "v": FEED_VERSION,
        "src": SRC.name,
        "generated": D.get("generated", ""),
        "swept": D.get("swept", ""),
        "tracker": D.get("tracker", ""),
        "tab": D.get("tab", ""),
        "win": D.get("win") or None,
        "days": days,
        "clr": clrs,
        "open": [
            {k: o.get(k, "") for k in ("item", "detail", "who")}
            for o in (D.get("still_open") or [])
        ],
        "n_tags": n_tags,
        "n_clr": len(clrs),
    }

    # --- verification, before anything is written -------------------------
    # Nothing lost, nothing added. A trimmed feed that quietly drops a day's
    # work is worse than no trimmed feed, because the board would show the
    # short list as though it were the whole day.
    src_tags = sum(len(v) for v in days_in.values())
    if n_tags != src_tags:
        die("tag count changed: caldata %d, feed %d" % (src_tags, n_tags))
    src_notifs = {str(x.get("n")) for v in days_in.values() for x in v}
    out_notifs = {t["n"] for v in days.values() for t in v}
    if src_notifs != out_notifs:
        missing = sorted(src_notifs - out_notifs)[:5]
        extra = sorted(out_notifs - src_notifs)[:5]
        die("notification set changed — missing %s, extra %s" % (missing, extra))
    src_days = {d for d, v in days_in.items() if v}
    if src_days != set(days):
        die("day set changed: %d in caldata, %d in feed" % (len(src_days), len(days)))
    src_clr = len([c for c in (D.get("clearances") or []) if c.get("start")])
    if len(clrs) != src_clr:
        die("clearance count changed: caldata %d, feed %d" % (src_clr, len(clrs)))

    body = json.dumps(feed, ensure_ascii=False, separators=(",", ":"))

    # Atomic: the board may be reading the old file while this runs, and a
    # half-written feed parses as nothing at all.
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, OUT)

    before = SRC.stat().st_size
    after = OUT.stat().st_size
    print("mobile_feed.json: %d tags on %d days, %d clearances — %.0f KB from %.0f KB (%.0f%%)"
          % (n_tags, len(days), len(clrs), after / 1024, before / 1024, 100 * after / before))


if __name__ == "__main__":
    main()
