# Twice-daily freshness check — create this from the claude.ai Routines UI

The board tells the truth about its own age every time it is opened, so this
routine is the proactive half: it pushes a notification when the pipeline has
gone stale while nobody is looking at the board.

It has to be created from the claude.ai Routines UI (or any session that holds
the connector). A routine created from a Claude Code session cannot be granted
the Microsoft 365 connector, so it would fire with no SharePoint access and
report nothing useful. The existing "Fresno WMP KML — daily 6am refresh" routine
is the working example of the same pattern.

**Schedule:** `0 12,21 * * 1-5` — 05:00 and 14:00 Pacific, weekdays.
**Notifications:** push on, email off.
**New session on each firing.**

---

Check whether the Fresno WMP field board is showing current data, and say so in a few lines. Run silent when everything is fine.

The board is a published artifact that reads the pipeline's output from OneDrive every time Gavin opens it. It shows whatever the last pipeline sweep wrote. Opening it cannot make the sweep run — that needs Classic Outlook and Desktop Commander on Gavin's Windows box. So the thing that can silently go wrong is the sweep not having run, while the board keeps showing old work as though it were today's.

Load the Microsoft 365 tools with ToolSearch (select:mcp__Microsoft_365__read_resource,mcp__Microsoft_365__sharepoint_search), then:

1. Read the pipeline's own stamp:
   file:///b!PRd2jUqlgUaMUN0sE5o2GNcEPkwp9rFDrMOpOikwnBOuBzwAhU8EQJgZcl3V4FMT/Everything Folder/WMP_Fresno_Tracker/data/_last_run.json
   Take last_build, last_swept, tracker_file and tracker_tab.

2. sharepoint_search for "Fresno WMP 2026 Master Tag Tracker" and for "WMP Fresno Dependency Tracker". Note the newest lastModifiedDateTime on each.

3. Compare. Report only what is actionable:
   - Sweep is 2+ days old, or the workbook has been re-saved since last_swept: say the board is behind, by how long, and that the sweep needs running on the Windows box. Name the workbook timestamp against the sweep timestamp so the gap is concrete.
   - A dependency tracker file newer than the one in tracker_file: name both, since extract.py picks the newest .xlsm and a new one changes what the board shows.
   - Everything current: reply in one line that the board is current as of <last_build>, and stop. Do not pad it.

Do not try to run the pipeline, do not edit any file in the tracker folder, and do not rebuild the board. This is a read-only check. If a read fails, say which one failed and what the error was rather than guessing at freshness.

Dates are UTC in these files; Gavin works Pacific. Do not restate a UTC timestamp as if it were his local time.
