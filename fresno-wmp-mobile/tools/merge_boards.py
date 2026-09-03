#!/usr/bin/env python3
"""Assemble the two built boards into one page, so they share one store.

    python3 tools/merge_boards.py

Why one page at all: an artifact's database belongs to that artifact. Two
published boards are two stores, so a lane assigned on the field board never
reaches the desk board — which was the whole point of sharing. One artifact,
one store, and the phone and the monitor finally agree.

THE PROBLEM WITH MERGING THESE TWO
The boards are not two views of one app. They are two applications that happen
to carry the same data: separate stylesheets sharing 50 class names, separate
DOM, and top-level scripts that both declare `state`, `render`, `save`, `TAGS`
and much else. Concatenating them breaks both, in ways that would show up as
subtly wrong colours and silently dead buttons rather than as an error.

HOW THIS AVOIDS IT
Nothing is rewritten. Each board is carried whole and inert, and exactly one is
brought to life per page load:

  - its stylesheet ships as <style media="not all">, which the browser parses
    but never applies; booting flips that one attribute to "all"
  - its markup ships inside <template>, which renders nothing and loads
    nothing; booting clones it into the mount point
  - its script ships wrapped in a function that is simply not called

So the losing board contributes no rules, no elements and no listeners. There
is no CSS scoping pass to get wrong, and no renaming — both designs are byte
for byte what they were.

Switching view reloads the page rather than tearing one board down and standing
the other up. Both register their own document-level handlers, and unpicking
that at runtime is exactly the kind of thing that half-works.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
FIELD = ROOT / "Gavin_schedule_MOBILE.live.html"
DESK = ROOT / "Gavin_schedule_DESK.live.html"
OUT = ROOT / "Gavin_schedule_BOARD.live.html"
FRAG = ROOT / "Gavin_schedule_BOARD.artifact.html"

TITLE = "Fresno WMP 2026 Schedule"


def fail(msg):
    sys.exit("merge_boards.py: " + msg)


def split(path):
    """(stylesheet, markup, script) from one built board."""
    if not path.exists():
        fail("missing %s — run patch.py for both boards first" % path.name)
    h = path.read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", h, re.S)
    if not m:
        fail("no <style> in " + path.name)
    css = m.group(1)
    scripts = re.findall(r"<script>(.*?)</script>", h, re.S)
    if len(scripts) != 1:
        fail("expected exactly one inline script in %s, found %d" % (path.name, len(scripts)))
    body = h[h.index("<body>") + len("<body>"):h.rindex("</body>")]
    markup = re.sub(r"<script>.*?</script>", "", body, flags=re.S).strip()
    for guard, what in (("</template>", "a </template>"), ("</script>", "a </script>")):
        if guard in markup:
            fail("%s contains %s in its markup, which would end the wrapper early"
                 % (path.name, what))
    if "</script>" in css:
        fail("%s stylesheet contains </script>" % path.name)
    return css, markup, scripts[0]


CHOOSER_CSS = """
/* The one piece of chrome this page owns. Deliberately plain: it sits above
   two finished designs and should not compete with either. Its colours are its
   own, not borrowed from a board, because whichever board is showing owns
   everything below it. */
#viewpick{display:flex;align-items:center;gap:0;padding:6px 10px;
  border-bottom:1px solid #cfcfcf;background:#f2f2f2;color:#1a1a1a;
  font:13px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  padding-top:calc(6px + env(safe-area-inset-top,0px))}
#viewpick b{font-weight:650;margin-right:auto;letter-spacing:-.01em}
#viewpick button{font:inherit;font-size:12.5px;padding:4px 13px;cursor:pointer;
  border:1px solid #b8b8b8;background:#fff;color:#3a3a3a}
#viewpick button:first-of-type{border-radius:5px 0 0 5px}
#viewpick button:last-of-type{border-radius:0 5px 5px 0;border-left:0}
#viewpick button[aria-pressed=true]{background:#f05b35;border-color:#f05b35;
  color:#fff;font-weight:600}
#viewpick button:focus-visible{outline:2px solid #1a1a1a;outline-offset:1px}
@media (prefers-color-scheme: dark){
  #viewpick:not([data-fixed=light]){background:#1c1c1c;color:#f0f0f0;border-bottom-color:#3a3a3a}
  #viewpick:not([data-fixed=light]) button{background:#262626;border-color:#454545;color:#d8d8d8}
  #viewpick:not([data-fixed=light]) button[aria-pressed=true]{background:#f05b35;border-color:#f05b35;color:#fff}
}
"""

# A board's internals are function-scoped once merged, so the tests have no way
# in short of driving the whole UI. This opens one, and only when the page is
# asked for with ?__probe — absent that query it defines nothing at all, so a
# board opened normally carries no extra surface.
PROBE = """
try{
  if(String(location.search||"").indexOf("__probe") >= 0){
    window.__boardProbe = {
      firstTag: function(){ return TAGS[0].id; },
      laneOf:   function(id){ return state.place[id] && state.place[id].lane; },
      assign:   function(id, lane){ state.place[id].lane = lane; save(); }
    };
  }
}catch(e){}
"""

BOOT = """
/* ---------- which board, and bringing it to life ----------------------- */
(function(){
  "use strict";
  var KEY = "fresno-board-view";
  function stored(){ try{ return localStorage.getItem(KEY); }catch(e){ return null; } }
  function remember(v){ try{ localStorage.setItem(KEY, v); }catch(e){} }

  /* A phone gets the field board, a monitor the desk calendar — but only until
     someone chooses, after which their choice holds on that device. */
  var choice = stored();
  if(choice !== "field" && choice !== "desk"){
    var narrow = false;
    try{ narrow = window.matchMedia("(max-width: 820px)").matches; }catch(e){}
    choice = narrow ? "field" : "desk";
  }

  var pick = document.getElementById("viewpick");
  pick.querySelectorAll("button").forEach(function(b){
    b.setAttribute("aria-pressed", String(b.dataset.view === choice));
    b.addEventListener("click", function(){
      if(b.dataset.view === choice) return;
      remember(b.dataset.view);
      /* Reload rather than swap in place: both boards register their own
         document-level handlers, and unpicking one at runtime half-works. */
      location.reload();
    });
  });
  /* The desk board is light only, so the chooser above it stays light too
     rather than sitting as a dark strip on a white page. */
  if(choice === "desk") pick.setAttribute("data-fixed", "light");

  document.getElementById("css-" + choice).media = "all";
  document.getElementById("mount")
    .appendChild(document.getElementById("mk-" + choice).content.cloneNode(true));

  /* Now, and only now, does that board's code run — against its own markup,
     with its own stylesheet live and the other board contributing nothing. */
  (choice === "field" ? bootField : bootDesk)();
})();
"""


def main():
    f_css, f_markup, f_js = split(FIELD)
    d_css, d_markup, d_js = split(DESK)

    page = []
    page.append("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">")
    page.append('<meta name="viewport" content="width=device-width, initial-scale=1, '
                'viewport-fit=cover, maximum-scale=5">')
    page.append('<meta name="apple-mobile-web-app-capable" content="yes">')
    page.append('<meta name="apple-mobile-web-app-title" content="Fresno WMP">')
    page.append('<meta name="referrer" content="no-referrer">')
    page.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
    page.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    page.append('<link href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed'
                ':wght@400;500;600;700&display=swap" rel="stylesheet">')
    page.append("<title>%s</title>" % TITLE)
    page.append("<style>%s</style>" % CHOOSER_CSS)
    # Parsed but never applied until one is chosen.
    page.append('<style media="not all" id="css-field">%s</style>' % f_css)
    page.append('<style media="not all" id="css-desk">%s</style>' % d_css)
    page.append("</head>\n<body>")
    page.append('<div id="viewpick"><b>Fresno WMP 2026</b>'
                '<button type="button" data-view="field">Field</button>'
                '<button type="button" data-view="desk">Desk</button></div>')
    page.append('<div id="mount"></div>')
    page.append('<template id="mk-field">\n%s\n</template>' % f_markup)
    page.append('<template id="mk-desk">\n%s\n</template>' % d_markup)
    page.append("<script>")
    page.append("function bootField(){\n%s\n%s\n}" % (f_js, PROBE))
    page.append("function bootDesk(){\n%s\n%s\n}" % (d_js, PROBE))
    page.append(BOOT)
    page.append("</script>\n</body>\n</html>")

    html = "\n".join(page)
    OUT.write_text(html, encoding="utf-8")

    start = html.index("<title>")
    body_open = html.index("<body>") + len("<body>")
    body_close = html.rindex("</body>")
    frag = html[start:html.index("</head>")].rstrip() + "\n\n" + \
        html[body_open:body_close].strip() + "\n"
    FRAG.write_text(frag, encoding="utf-8")

    print("%s (%d bytes) and %s (%d bytes)"
          % (OUT.name, len(html), FRAG.name, len(frag)))
    print("   field %d KB css / %d KB js   desk %d KB css / %d KB js"
          % (len(f_css) / 1024, len(f_js) / 1024, len(d_css) / 1024, len(d_js) / 1024))


if __name__ == "__main__":
    main()
