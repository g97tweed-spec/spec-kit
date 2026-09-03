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

import theme

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
LIVE = HERE / "live.js"
SHARE = HERE / "share.js"
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
]

# Each board opens differently, so each gets its own boot block. The shape is
# the same on both: render the hardcoded snapshot first so the page is usable
# immediately, then upgrade it in place once the connector answers. A board
# that sits blank waiting on SharePoint is worse than one showing yesterday.
#
# Theme handling is not listed per board: it is derived from whatever dark
# palette each page already declares (see tools/theme.py), so a board that has
# one gets all three viewer states and a board that does not is left as the
# single-theme design it is.
PAGES = [
    {
        "name": "field board",
        # Dark mode earns its place on a phone opened before dawn.
        "theme": "auto",
        "extra_css": [],
        "marker": "<title>Fresno WMP 2026 \u2014 Field</title>",
        "needs": ["tagsOn", "defaultDay", "monthIndexFor"],
        "boot_old": """/* ===================== GO ===================== */
(async function(){
  await load();
  cur=monthIndexFor(TODAY);
  selDay=defaultDay();
  staleBanner();
  render();
})();""",
        "boot_new": """/* ===================== GO ===================== */
(async function(){
  await load();
  cur=monthIndexFor(TODAY);
  selDay=defaultDay();
  render();
  try{ await goShared(); }catch(e){ /* board still works on this device */ }
  try{
    await goLive();
    shareReapply();
    /* The live feed can move a tag to a different day, so the opening day is
       re-picked once — but only while the user is still on the day the board
       chose for them. Never yank the view out from under a deliberate tap. */
    if(selDay===TODAY||!tagsOn(selDay).length){
      cur=monthIndexFor(TODAY); selDay=defaultDay(); render();
    }
  }catch(e){
    snapshotBar("Refresh failed to start: "+(e&&e.message||e));
  }
})();""",
    },
    {
        "name": "desk calendar",
        # Light only, by request. Read indoors on a monitor, and every contrast
        # problem this board had lived in its dark palette.
        "theme": "light",
        # Only meaningful under "auto" — the dark-mode contrast repairs.
        "extra_css": ["lane-contrast.css"],
        "marker": "<title>Fresno WMP 2026 \u2014 Tag Calendar (desk)</title>",
        "needs": ["monthIndexFor"],
        "boot_old": "load().then(()=>{render();staleBanner();});",
        "boot_new": """load().then(async()=>{
  render();
  try{ await goShared(); }catch(e){ /* board still works on this device */ }
  try{
    await goLive();
    shareReapply();
    /* The desk board shows a whole month at a time, so a feed that moves a tag
       between days changes what is in the grid but not which grid to show. It
       is repainted, not repositioned — goLive() has already done that. */
  }catch(e){
    snapshotBar("Refresh failed to start: "+(e&&e.message||e));
  }
});""",
    },
]


def identify(html):
    """Which board is this? Matched on the page's own title, and on its boot
    block actually being present — a page that merely looks like one of these
    but opens some other way is not one we can splice into."""
    for page in PAGES:
        if page["marker"] in html and page["boot_old"] in html:
            return page
    known = ", ".join(p["name"] for p in PAGES)
    fail("this is not a page patch.py knows how to wire up (expected one of: %s). "
         "Either the title or the boot block has changed." % known)


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


def preflight(html, extra=()):
    """Every symbol live.js reaches for must already exist in the page, and be
    declared before the boot block where the live layer is spliced in."""
    missing = []
    for name, why in REQUIRED + [(n, "needed by this board's boot block") for n in extra]:
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
    live = LIVE.read_text(encoding="utf-8") + "\n\n" + SHARE.read_text(encoding="utf-8")
    page = identify(html)
    preflight(html, page["needs"])

    # 1. The live module goes in just before the boot block, so every helper it
    #    leans on (TAGS, AFWS, state, render, esc, PAL, AFWCOL) is defined.
    html = html.replace(page["boot_old"], live.rstrip() + "\n\n" + page["boot_new"], 1)

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
    sheets = [CSS]
    if page["theme"] == "auto":
        sheets += [HERE / n for n in page["extra_css"]]
    add = "\n".join(x.read_text(encoding="utf-8").rstrip() for x in sheets)
    html = html.replace(css_anchor, "\n" + add + "\n" + css_anchor, 1)

    # 4. Make the page's own dark palette answer all three viewer states, not
    #    just the OS default. Derived from what the page declares; a page with
    #    no dark block is left single-theme.
    style_open = html.index("<style>") + len("<style>")
    style_close = html.index("</style>", style_open)
    if page["theme"] == "light":
        css_text, n_gone = theme.force_light(html[style_open:style_close])
        themed = ("light only — %d dark block(s) removed" % n_gone) if n_gone \
            else "light only — page had no dark palette"
    else:
        css_text, n_rules = theme.apply(html[style_open:style_close])
        themed = ("%d dark rules given explicit-theme handling" % n_rules) if n_rules \
            else "single-theme page, left as is"
    html = html[:style_open] + css_text + html[style_close:]

    # 4. Offline-first: a field phone opens this with no signal often enough
    #    that the manifest and cache hints matter more than they look.
    # Only the field board carries this meta; the desk page has no mobile head.
    head_old = '<meta name="theme-color" content="#111111">'
    if head_old in html:
        html = html.replace(
            head_old, head_old + '\n<meta name="referrer" content="no-referrer">', 1)

    out.write_text(html, encoding="utf-8")
    frag.write_text(fragment(html), encoding="utf-8")
    base = len(src.read_text(encoding="utf-8"))
    print("%s [%s] -> %s (%d bytes, +%d) and %s\n   %s"
          % (src.name, page["name"], out.name, len(html), len(html) - base, frag.name, themed))


if __name__ == "__main__":
    main(sys.argv[1:])
