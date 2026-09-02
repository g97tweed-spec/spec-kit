# Fresno WMP 2026 boards — live refresh

Turns the hardcoded field and desk boards into ones that show current data when
they are opened, instead of the snapshot they were built from. Both read the
same feed and share one live layer.

The boards themselves are not in this repository. It carries live PG&E operational
data — notification numbers, structure IDs, clearance windows, and named
contacts with phone numbers — and this repository is public. Only the build
tooling is here; `.gitignore` keeps the pages out.

| board | page | opens |
|---|---|---|
| field | `Gavin_schedule_MOBILE.html` | phone, day at a time |
| desk | `Gavin_schedule_DESK.html` | browser, month grid |

## What actually refreshes, and what does not

```
 Windows box                          OneDrive                   phone
 ───────────                          ────────                   ─────
 pipeline sweep  ──▶ merge.py  ──▶    data/caldata.json          (1.4 MB, desktop)
 (Outlook COM,       build.py           │
  openpyxl)          kmz.py             ├─ mobile_feed.py ─▶ data/mobile_feed.json
                     mobile_feed.py     │                        │
                                        data/_last_run.json ─────┴──read──▶ board, on open
```

The board reads `mobile_feed.json` — the pipeline's reconciled output with
everything the phone does not draw taken out — through the viewer's own
Microsoft 365 connector, every time the page is opened. Whatever the last sweep
concluded is what the board shows, and the banner across the top says when that
sweep ran.

**Opening the page cannot make the pipeline run.** The sweep needs Classic
Outlook and Desktop Commander on the Windows box; nothing in the cloud can
trigger it. If the sweep last ran Friday, opening the board on Monday shows
Friday's data — labelled as Friday's, in amber, with the number of days it is
behind. That labelling is the point: a board that silently shows three-day-old
clearances is worse than no board.

## The three states

| Banner | Means | What fixes it |
|---|---|---|
| green — up to date | live read succeeded, pipeline ran recently | nothing |
| amber — live read, N days behind | the read worked, the data is old | run the sweep |
| amber — offline copy | no connector reachable, showing this device's last good read | signal |
| red — built-in snapshot | no live read and no cache; showing 1 Sep 2026 | connector or signal |

Connector failures are reported by cause, not as one generic message: a lapsed
token says to reconnect in claude.ai Settings → Connectors, a missing connector
says to add it, an unreachable SharePoint says so.

## The trimmed feed

`tools/mobile_feed.py` is a pipeline step. Copy it to `<root>/pipeline/` and run
it after `merge.py`:

```
python3 merge.py
python3 build.py
python3 kmz.py
python3 mobile_feed.py     # writes data/mobile_feed.json
```

It projects `caldata.json` down to the fields the board renders — dropping the
per-organisation "who says what" block, the line-conflict table, the coverage
stats, the info-level flags, and the copy of each covering clearance that sits
inside every tag that rides it. On the test fixture that is 38% of the original;
on a real build, where the `sources` block is much heavier, it is nearer 15%.
The script prints the actual figure on every run.

**It is a projection, not a derivation.** Every value is copied unchanged.
Nothing is estimated, interpolated or re-derived. Two fields come close and
neither crosses the line: `f` keeps the verbatim text of flags the pipeline
already marked bad or warn, and `nr` restates the pipeline's own `NOT_READY`
flag as a boolean.

Before writing, it re-counts. If the tag count, the notification set, the day
set or the clearance count differs from `caldata.json`, it exits without
writing. A trimmed feed that has quietly lost a day's work is worse than no
trimmed feed, because the board would render the short list as though it were
the whole day. The write itself is atomic, so a board reading mid-run never
sees half a file.

The board tries `mobile_feed.json`, then `caldata.json`, then
`cal3_payload.json`, and picks its reader by shape — the trimmed feed carries a
`v` stamp — so a build made before this step existed still works.

## Data mapping

`caldata.json` is keyed for the desktop discrepancy calendar
(`pipeline/caltemplate.html` is the reference reader). The board's fields come
from it as:

| board | caldata | note |
|---|---|---|
| notification | `days[date][].n` | |
| line, structure | `.ln`, `.st` | |
| MAT, description | `.mat`, `.act` \| `.desc` | |
| flag line | worst of `.flags[]` where sev is bad or warn | the pipeline's own words |
| AFW windows | `clearances[]` | `clearance_id`, `type`, `start`/`end`, `window` |
| priority (E/P/F) | **not in caldata** | carried from the snapshot per notification, blank where unknown |

Priority lives in the Master Tag Tracker, which this page does not read. It is
left blank rather than filled from a field that means something else.

Crew lane assignments are the foreman's, not the pipeline's, and are keyed by
notification so a refresh never re-lanes anyone's day — including for tags that
arrived with the feed and were never in the snapshot.

## Build

```bash
python3 tools/patch.py Gavin_schedule_MOBILE.snapshot.html
python3 tools/patch.py Gavin_schedule_DESK.snapshot.html
node tools/smoke.js Gavin_schedule_MOBILE.live.html   # 34 checks, six states
node tools/smoke.js Gavin_schedule_DESK.live.html     # 36 — adds the reset baseline
python3 tools/test_mobile_feed.py                     # 23 on the trimmer and its guards
python3 tools/test_theme.py                           # 18 on the theme rewrite
```

`patch.py` identifies which board it was handed from the page's own title and
boot block, and refuses anything else. Before splicing it checks the page
declares every symbol the live layer drives it through; a page missing any is
named, not patched and hoped for. The two boards differ in three places and the
patcher handles each:

| | field board | desk calendar |
|---|---|---|
| boots | `(async ...)()` with a day strip to reposition | `load().then(...)`, month grid stays put |
| banner mounts before | `<main>` | `.page` |
| dark palette | 1 rule, `--ink`/`--bg` | 3 rules, 88 `--kNN` colour tokens |

The desk board also keeps a frozen copy of the opening crew lanes for its "clear
the board" button. A refresh rebuilds it; left alone it would wipe every tag the
feed brought and resurrect ones it dropped.

## Themes

Both boards ship their dark colours behind `@media (prefers-color-scheme: dark)`
and nothing else. That is right for a file opened from Files, where the OS is
the only thing to ask. Published to claude.ai there is a third state: the viewer
stamps `data-theme` on the root element for an explicit choice and stamps
nothing for "system".

`tools/theme.py` rewrites the page so all three resolve. It guards the page's
own dark block **in place** and emits a second copy for the explicit-dark stamp.
Guarding in place is the part that matters: adding a
`:root:not([data-theme="light"])` rule alongside does not stop the original
`:root` rule inside the media query from matching, so someone who picks light on
a dark-mode OS still gets the dark palette. That was shipped broken on the field
board before this existed.

Every colour is the page's own — nothing here invents a value or decides what
dark should look like. A page with no dark block is returned untouched; single
-theme by design is an answer, not a gap.

`patch.py` takes `Gavin_schedule_MOBILE.snapshot.html` as input and never edits
it. Every edit is anchored on text that must exist; a missing anchor is a hard
failure, because quietly producing a page that looks live but is not is the one
outcome worth crashing over. Re-run it after the board is regenerated.

Two outputs, because they are opened two different ways:

- **`.artifact.html`** — document shell removed, for publishing to claude.ai.
  This is the one that refreshes: only a published artifact can reach the
  connector.
- **`.live.html`** — standalone, for OneDrive. Opened straight from Files it has
  no connector, so it shows the snapshot and says so. It is the offline backup,
  not the live copy.

`smoke.js` takes either built page and drives it under jsdom with a stubbed
connector, asserting the same six states on both, plus the things a refresh must
never do: drop a crew lane, give two overlapping clearance windows the same
colour, or leave the desk board's reset baseline on snapshot values.

## Known limits

- The board reads one file. If the pipeline renames its payload, `LIVE.feeds`
  in `tools/live.js` lists the candidates tried in order.
- The feed crosses the connector on every cold open. The result is cached per
  device, and the page renders the snapshot first so it is never blank while
  waiting. If `mobile_feed.py` is not in the build, the board falls back to the
  full 1.4 MB `caldata.json`.
- Work verification, the job-package scans and the landing-zone detail are
  still snapshot data. They are not in `caldata.json`.

## Scheduled freshness check

The board reports its own age on every open, which covers the case where
someone is looking at it. `tools/freshness-routine.md` is the other half — a
twice-daily push when the pipeline has gone stale while nobody is. It has to be
created from the claude.ai Routines UI: a routine created from a Claude Code
session cannot be granted the Microsoft 365 connector, so it would fire blind.
