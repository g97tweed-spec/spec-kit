#!/usr/bin/env python3
"""Tests for mobile_feed.py.

    python3 tools/test_mobile_feed.py

Two things are being checked. First that the projection keeps everything the
board draws and drops only what it does not. Second — and this is the one that
matters on an unattended run — that the verification refuses to write a feed
that has quietly lost work. A short list rendered as though it were the whole
day is the failure mode worth crashing over.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "mobile_feed.py"

passed = failed = 0


def ok(cond, label, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + label)
    else:
        failed += 1
        print("  FAIL " + label + (("  -> " + str(extra)) if extra else ""))


def caldata(n_days=3, per_day=4):
    days = {}
    n = 133600000
    for d in range(n_days):
        date = "2026-09-%02d" % (d + 1)
        rows = []
        for _ in range(per_day):
            n += 1
            rows.append({
                "n": n, "st": "016/266", "ln": "COPUS-OLD RIVER", "kv": "70",
                "mat": "921", "hq": "Bakersfield", "desc": "REPLACE DAMAGED CONDUCTOR",
                "act": "RPR CNDW", "anytime": False, "sev": "bad",
                "ss": date, "se": date, "fac": "dropped", "cs": "", "ce": "",
                "flags": [
                    {"code": "NO_CLR_ON_DATE", "sev": "bad",
                     "t": "No outage covers the planned date", "src": "sweep"},
                    {"code": "NOT_READY", "sev": "warn",
                     "t": "Readiness gate not met", "src": "tracker"},
                    {"code": "EMAIL_INFO", "sev": "info", "t": "Noted in email", "src": "x"},
                ],
                "clrs": [{"id": "AFW-1", "type": "T-line clearance", "start": date}],
            })
        days[date] = rows
    return {
        "generated": "2026-09-01", "swept": "2026-09-01T19:02:00Z",
        "tracker": "WMP Fresno Dependency Tracker 8-23-26.xlsm", "tab": "8.23.26",
        "win": ["2026-09-01", "2026-12-15"], "days": days,
        "clearances": [
            {"clearance_id": "AFW-T26-003222", "type": "T-line clearance",
             "line": "COPUS-OLD RIVER", "start": "2026-09-01", "end": "2026-09-01",
             "window": "07:00-17:00", "points": "016/266 to 017/293",
             "purpose": "Shunt splice", "structures": ["016/266"],
             "source_subject": "Clearance", "source_from": "pge",
             "source_date": "2026-08-20", "cancelled": True},
            {"clearance_id": "AFW-NO-START", "type": "NTO"},   # no start: not a window
        ],
        "still_open": [{"item": "LZ02", "detail": "BLM approval outstanding", "who": "Stantec"}],
        # everything below is desktop-calendar furniture the phone never draws
        "sources": {"2026-09-01": {"133600001": {"s": {"pge": {"org": "pge", "says": "x" * 200,
                                                               "state": "ok"}}, "x": ["disagree"]}}},
        "orgsummary": {"orgs": ["pge"], "labels": {"pge": "PG&E"}},
        "lineissues": [{"line": "COPUS-OLD RIVER", "n_outside": 9}],
        "coverage": {"total_rows": 1232},
    }


def run(cal):
    """Run the real script against a throwaway tree; return (rc, out, feed|None)."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "data").mkdir()
    (tmp / "pipeline").mkdir()
    (tmp / "data" / "caldata.json").write_text(json.dumps(cal), encoding="utf-8")
    shutil.copy(SCRIPT, tmp / "pipeline" / SCRIPT.name)
    r = subprocess.run([sys.executable, "pipeline/" + SCRIPT.name],
                       cwd=tmp, capture_output=True, text=True)
    out = tmp / "data" / "mobile_feed.json"
    feed = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    shutil.rmtree(tmp, ignore_errors=True)
    return r.returncode, (r.stdout + r.stderr).strip(), feed


print("\n1. the projection")
rc, out, feed = run(caldata())
ok(rc == 0, "runs clean", out)
ok(feed is not None, "writes a feed")
if feed:
    ok(feed["v"] == 1, "stamps a version, so the board can tell the formats apart")
    ok(feed["n_tags"] == 12 and len(feed["days"]) == 3, "every tag on every day survives",
       (feed["n_tags"], len(feed["days"])))
    t = feed["days"]["2026-09-01"][0]
    ok(t["w"] == "RPR CNDW", "keeps the activity code a foreman reads, not the long description")
    ok(t.get("f") == ["No outage covers the planned date", "Readiness gate not met"],
       "keeps bad and warn flag text verbatim, in order", t.get("f"))
    ok("Noted in email" not in json.dumps(t), "drops info flags the board cannot show")
    ok(t.get("nr") == 1, "restates the pipeline's own NOT_READY as a boolean")
    ok("fac" not in t and "cs" not in t and "clrs" not in t,
       "drops fields the board never draws", list(t))
    ok("sources" not in feed and "lineissues" not in feed and "coverage" not in feed,
       "drops the desktop-calendar blocks entirely")
    ok(len(feed["clr"]) == 1, "a clearance with no start date is not a window", len(feed["clr"]))
    c = feed["clr"][0]
    ok(c["x"] == 1 and c["id"] == "AFW-T26-003222", "cancelled stays marked cancelled")
    ok(c["src"] == "Clearance — pge — 2026-08-20", "source line is joined, not invented", c["src"])
    ok(feed["open"][0]["who"] == "Stantec", "still-open items carry who owes the answer")
    ok(feed["tab"] == "8.23.26" and feed["tracker"].endswith(".xlsm"),
       "carries the tracker identity the banner reports")

print("\n2. it refuses to write a feed that lost work")
# A day whose rows vanish must not pass. Simulated by handing the script a
# caldata whose day list disagrees with itself is not possible from outside, so
# instead check the guards that CAN be tripped from the input side.
rc, out, feed = run({"generated": "x", "days": {}})
ok(rc != 0 and feed is None, "empty day map is refused, not written as an empty board", out)
ok("empty feed" in out, "and says why", out)

rc, out, feed = run({"days": {"2026-09-01": []}})
ok(rc != 0, "a day map with no rows at all is refused too", out)

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "data").mkdir(); (tmp / "pipeline").mkdir()
(tmp / "data" / "caldata.json").write_text("{not json", encoding="utf-8")
shutil.copy(SCRIPT, tmp / "pipeline" / SCRIPT.name)
r = subprocess.run([sys.executable, "pipeline/" + SCRIPT.name], cwd=tmp,
                   capture_output=True, text=True)
ok(r.returncode != 0 and "will not parse" in (r.stdout + r.stderr),
   "unparseable caldata is refused with the parse error", (r.stdout + r.stderr).strip())
ok(not (tmp / "data" / "mobile_feed.json").exists(),
   "and no partial feed is left behind for the board to read")
shutil.rmtree(tmp, ignore_errors=True)

rc, out, feed = run({"days": None})
ok(rc != 0, "a missing day map is refused", out)

print("\n3. it does not hold the board hostage to size")
big = caldata(n_days=60, per_day=20)
rc, out, feed = run(big)
ok(rc == 0 and feed and feed["n_tags"] == 1200, "1,200 tags project cleanly", out)
lean = len(json.dumps(feed, separators=(",", ":")))
fat = len(json.dumps(big))
# No fixed ratio is asserted: how much comes off depends on how heavy the
# `sources` block is in that particular build, which this fixture only
# approximates. The claim under test is that the trim is substantial, not that
# it hits a number. The real figure is printed by the script on each run.
ok(lean < fat * 0.6, "feed is well under caldata",
   "%d KB from %d KB (%.0f%%)" % (lean / 1024, fat / 1024, 100 * lean / fat))
print("     %d KB from %d KB (%.0f%%) on this fixture" % (lean / 1024, fat / 1024, 100 * lean / fat))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
