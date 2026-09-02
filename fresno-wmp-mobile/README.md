# Fresno WMP 2026 field board — live refresh

Turns the hardcoded mobile board into one that shows current data when it is
opened, instead of the snapshot it was built from.

The board itself is not in this repository. It carries live PG&E operational
data — notification numbers, structure IDs, clearance windows, and named
contacts with phone numbers — and this repository is public. Only the build
tooling is here; `.gitignore` keeps the pages out.

## What actually refreshes, and what does not

```
 Windows box                     OneDrive                    phone
 ───────────                     ────────                    ─────
 pipeline sweep    ──writes──▶   data/caldata.json  ──read──▶  board, on open
 (Outlook COM,                   data/_last_run.json
  openpyxl, merge.py)
```

The board reads `caldata.json` — the pipeline's reconciled output — through the
viewer's own Microsoft 365 connector, every time the page is opened. Whatever
the last sweep concluded is what the board shows, and the banner across the top
says when that sweep ran.

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
python3 tools/patch.py     # snapshot -> .live.html (standalone) + .artifact.html (fragment)
node tools/smoke.js        # 20 checks across the four states
```

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

`smoke.js` drives the built page under jsdom with a stubbed connector and
asserts the four states, plus the two things a refresh must never do: drop a
crew lane, or give two overlapping clearance windows the same colour.

## Known limits

- The board reads one file. If the pipeline renames its payload, `LIVE.feeds`
  in `tools/live.js` lists the candidates tried in order.
- `caldata.json` is ~1.4 MB. It crosses the connector on every cold open;
  the result is cached per device, and the page renders the snapshot first so
  it is never blank while waiting.
- Work verification, the job-package scans and the landing-zone detail are
  still snapshot data. They are not in `caldata.json`.
