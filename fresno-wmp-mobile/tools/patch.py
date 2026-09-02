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
LIVE = HERE / "live.js"
CSS = HERE / "live.css"

DEFAULT_SRC = ROOT / "Gavin_schedule_MOBILE.snapshot.html"

# Symbols the live layer calls into. Both boards were cut from the same
# codebase, but "both boards look the same inside" is an assumption, and the
# cost of it being wrong is a page that loads and then silently fails to
# refresh. Checked up front, by name, with the failure naming what is missing.
REQUIRED = [
    ("TAGS", "the tag array the feed replaces"),
    ("AFWS", "the clearance array the feed replaces"),
    ("PAL", "the palette the clearance colours come from"),
    ("AFWCOL", "the clearance colour map"),
    ("NOTREADY", "the readiness set the tag sheet draws from"),
    ("PRESET", "the default crew lanes"),
    ("state", "the saved board state"),
    ("KEY", "the localStorage key the saved state lives under"),
    ("SNAPSHOT", "the date the hardcoded data was read"),
    ("TODAY", "the device clock"),
    ("render", "the repaint entry point"),
    ("esc", "the HTML escaper"),
    ("daysBetween", "the date arithmetic the banner reports with"),
    ("tagsOn", "the per-day tag lookup"),
    ("defaultDay", "the opening day chooser"),
    ("monthIndexFor", "the opening month chooser"),
]

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


def preflight(html):
    """Every symbol live.js reaches for must already exist in the page, and be
    declared before the boot block where the live layer is spliced in."""
    missing = []
    for name, why in REQUIRED:
        # a declaration, not a mention: `const TAGS=`, `let state=`,
        # `function render(`, `var x =` — whitespace tolerated
        decl = re.search(r"\b(?:const|let|var)\s+%s\b\s*=" % re.escape(name), html) \
            or re.search(r"\bfunction\s+%s\s*\(" % re.escape(name), html)
        if not decl:
            missing.append("  %-14s %s" % (name, why))
    if missing:
        fail("this page does not declare everything the live layer needs:\n"
             + "\n".join(missing)
             + "\n\nThe live layer drives the board through these. Port it by hand "
               "rather than letting patch.py splice into a page it does not fit.")


def main(argv):
    src = pathlib.Path(argv[0]).resolve() if argv else DEFAULT_SRC
    if not src.exists():
        fail("no such file: " + str(src))
    # Gavin_schedule_DESK.snapshot.html -> Gavin_schedule_DESK.{live,artifact}.html
    stem = src.name
    for suffix in (".snapshot.html", ".html"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    out = src.parent / (stem + ".live.html")
    frag = src.parent / (stem + ".artifact.html")

    html = src.read_text(encoding="utf-8")
    live = LIVE.read_text(encoding="utf-8")
    preflight(html)

    # 1. The live module goes in just before the boot block, so every helper it
    #    leans on (TAGS, AFWS, state, render, esc, PAL, AFWCOL) is defined.
    if BOOT_OLD not in html:
        fail("boot block not found — this page does not open the way the mobile "
             "board does, so the live layer has nowhere to hook in")
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

    out.write_text(html, encoding="utf-8")
    frag.write_text(fragment(html), encoding="utf-8")
    base = len(src.read_text(encoding="utf-8"))
    print("%s -> %s (%d bytes, +%d) and %s"
          % (src.name, out.name, len(html), len(html) - base, frag.name))


if __name__ == "__main__":
    main(sys.argv[1:])
