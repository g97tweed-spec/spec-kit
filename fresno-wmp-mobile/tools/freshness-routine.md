# Twice-daily freshness check

The boards tell the truth about their own age every time they are opened, so
this routine is the proactive half: it pushes a notification when the pipeline
has gone stale while nobody is looking.

**Live as `trig_019Rsd5HyjBDxYz4oZFsNnQn`**, created 2026-09-02.

- **Schedule** `0 12,21 * * 1-5` — 05:00 and 14:00 Pacific, weekdays
- **Notifications** push on, email off
- **New session on each firing**

**Confirmed working.** Creating this from a Claude Code session logs a warning
that the routine "stores no MCP connectors" and will fire without them. In this
environment that warning is wrong: a manual test fire on 2026-09-02 reported the
Microsoft 365 tools were available to it and completed in 37 seconds. So the
routine does not need recreating from the claude.ai Routines UI, and neither do
others like it — the two pre-existing Fresno routines were made the same way and
have been reading SharePoint and Outlook successfully for weeks.

Worth knowing rather than re-deriving: the way to settle it is to fire the
routine manually and read the run, because a session cannot read another
session's transcript. Ask the run itself to state whether the tools loaded.

The prompt as it stands:

---

Check whether Gavin's Fresno WMP boards are showing current data, and say so in a few lines. Run silent when everything is fine.

The two boards (field and desk) are published artifacts that read the pipeline's output from OneDrive every time they are opened. They show whatever the last pipeline sweep wrote. Opening them cannot make the sweep run — that needs Classic Outlook and Desktop Commander on Gavin's Windows box. So the thing that can silently go wrong is the sweep not having run, while the boards keep showing old work as though it were today's.

Load the Microsoft 365 tools with ToolSearch (select:mcp__Microsoft_365__read_resource,mcp__Microsoft_365__sharepoint_search), then:

1. Read the pipeline's own stamp:
   file:///b!PRd2jUqlgUaMUN0sE5o2GNcEPkwp9rFDrMOpOikwnBOuBzwAhU8EQJgZcl3V4FMT/Everything Folder/WMP_Fresno_Tracker/data/_last_run.json
   Take last_build, last_swept, tracker_file and tracker_tab.

2. Check the trimmed feed the boards actually read exists and is no older than the build:
   file:///b!PRd2jUqlgUaMUN0sE5o2GNcEPkwp9rFDrMOpOikwnBOuBzwAhU8EQJgZcl3V4FMT/Everything Folder/WMP_Fresno_Tracker/data/mobile_feed.json
   Read only its opening characters — it is a few hundred KB, so do not pull the whole thing into context if you can avoid it; its "generated" and "n_tags" fields are near the start. If the file does not exist, that means pipeline/mobile_feed.py has not been added to the build yet: say so, note the boards are falling back to the full caldata.json, and carry on.

3. sharepoint_search for "Fresno WMP 2026 Master Tag Tracker" and for "WMP Fresno Dependency Tracker". Note the newest lastModifiedDateTime on each.

4. Compare. Report only what is actionable:
   - Sweep is 2+ days old, or the workbook has been re-saved since last_swept: say the boards are behind, by how long, and that the sweep needs running on the Windows box. Name the workbook timestamp against the sweep timestamp so the gap is concrete.
   - A dependency tracker file newer than the one in tracker_file: name both, since extract.py picks the newest .xlsm and a new one changes what the boards show.
   - mobile_feed.json older than last_build, or missing: say so — the boards would be showing data older than the pipeline's own latest run.
   - Everything current: reply in one line that the boards are current as of <last_build>, and stop. Do not pad it.

Do not try to run the pipeline, do not edit any file in the tracker folder, and do not rebuild the boards. This is a read-only check. If a read fails, say which one failed and what the error was rather than guessing at freshness.

Dates are UTC in these files; Gavin works Pacific. Do not restate a UTC timestamp as if it were his local time.
