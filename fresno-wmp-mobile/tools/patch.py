#!/usr/bin/env python3
"""Turn the hardcoded Fresno WMP mobile board into one that refreshes on open.

The snapshot file is the input and is never edited in place. Re-run this after
the pipeline regenerates the snapshot and the live layer re-applies cleanly.

    python3 build/patch.py                 # snapshot -> Gavin_schedule_MOBILE.live.html

The three edits, all anchored on text that must exist. A missing anchor is a
hard failure: silently producing a page that looks live but is not is the one
outcome worth crashing over.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "Gavin_schedule_MOBILE.snapshot.html"
OUT = ROOT / "Gavin_schedule_MOBILE.live.html"        # standalone, for OneDrive
FRAG = ROOT / "Gavin_schedule_MOBILE.artifact.html"   # fragment, for publishing
LIVE = HERE / "live.js"
CSS = HERE / "live.css"

# The boot block, replaced wholesale. The original awaited load() and rendered
# the snapshot; the live one renders the snapshot first and then upgrades it,
# so the page is usable on a phone before SharePoint has answered.
BOOT_OLD = """/* ===================== GO ===================== */
(async function(){
  await load();
  cur=monthIndexFor(TODAY);
  selDay=defaultDay();
  staleBanner();
  render();
})();"""

BOOT_NEW = """/* ===================== GO ===================== */
(async function(){
  await load();
  cur=monthIndexFor(TODAY);
  selDay=defaultDay();
  render();
  try{
    await goLive();
    /* The live feed can move a tag to a different day, so the opening day is
       re-picked once — but only while the user is still on the day the board
       chose for them. Never yank the view out from under a deliberate tap. */
    if(selDay===TODAY||!tagsOn(selDay).length){
      cur=monthIndexFor(TODAY); selDay=defaultDay(); render();
    }
  }catch(e){
    snapshotBar("Refresh failed to start: "+(e&&e.message||e));
  }
})();"""


def fragment(html):
    """The publish wrapper supplies doctype, head and body, so the artifact form
    is the same page with its own document shell removed. The title and style
    move to the top of the file, where the wrapper looks for them. The
    apple-mobile-web-app meta tags are dropped with the head — they only ever
    applied to the file opened directly from Files, which is the other output.
    """
    start = html.index("<title>")
    body_open = html.index("<body>") + len("<body>")
    body_close = html.rindex("</body>")
    head = html[start:html.index("</head>")]
    return head.rstrip() + "\n\n" + html[body_open:body_close].strip() + "\n"


def fail(msg):
    sys.exit("patch.py: " + msg)


def main():
    if not SRC.exists():
        fail("missing snapshot at " + str(SRC))
    html = SRC.read_text(encoding="utf-8")
    live = LIVE.read_text(encoding="utf-8")

    # 1. The live module goes in just before the boot block, so every helper it
    #    leans on (TAGS, AFWS, state, render, esc, PAL, AFWCOL) is defined.
    if BOOT_OLD not in html:
        fail("boot block not found — the snapshot's GO section has changed")
    html = html.replace(BOOT_OLD, live.rstrip() + "\n\n" + BOOT_NEW, 1)

    # 2. staleBanner is dead: the live layer owns the banner now. Left defined
    #    but unwired, so an older call site cannot resurrect the wrong message.
    n_stale = len(re.findall(r"\bstaleBanner\(\)", html))
    if n_stale != 1:
        fail("expected exactly one staleBanner() call site, found %d" % n_stale)

    # 3. The banner skins and the missing [data-theme] blocks. The board only
    #    handled prefers-color-scheme, which renders the wrong palette for a
    #    viewer who has explicitly picked a theme.
    css_anchor = "</style>"
    if css_anchor not in html:
        fail("no </style> to append the live stylesheet to")
    html = html.replace(css_anchor, "\n" + CSS.read_text(encoding="utf-8").rstrip()
                        + "\n" + css_anchor, 1)

    # 4. Offline-first: a field phone opens this with no signal often enough
    #    that the manifest and cache hints matter more than they look.
    head_old = '<meta name="theme-color" content="#111111">'
    if head_old not in html:
        fail("head anchor not found")
    html = html.replace(
        head_old,
        head_old + '\n<meta name="referrer" content="no-referrer">',
        1,
    )

    OUT.write_text(html, encoding="utf-8")
    FRAG.write_text(fragment(html), encoding="utf-8")
    base = len(SRC.read_text(encoding="utf-8"))
    print("wrote %s (%d bytes, +%d over snapshot)" % (OUT.name, len(html), len(html) - base))
    print("wrote %s (%d bytes)" % (FRAG.name, len(FRAG.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
