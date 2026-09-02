#!/usr/bin/env python3
"""Tests for theme.py — the three viewer states.

    python3 tools/test_theme.py

The case worth the test is the middle one: a viewer who explicitly picks LIGHT
while their OS is in dark mode. Adding a guarded rule does not fix that on its
own, because the page's original unguarded rule inside the media query is still
there and still matching. This asserts the original is guarded in place.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import theme  # noqa: E402

passed = failed = 0


def ok(cond, label, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   " + label)
    else:
        failed += 1
        print("  FAIL " + label + (("  -> " + str(extra)) if extra else ""))


SAMPLE = """:root{ --bg:#fff; --ink:#111; }
@media (prefers-color-scheme: dark){
:root{
  --bg:#141414; --ink:#f2f2f2;
}
/* scans stay on white */
img.drw, .zwrap img{background:#fff;filter:brightness(.90)}
}
.card{background:var(--bg)}
"""

print("\n1. a page that declares a dark palette")
out, n = theme.apply(SAMPLE)
ok(n == 2, "both rules in the media block are handled", n)

media_body = out[out.index("@media"):out.index(".card{")]
ok(":root:not([data-theme=\"light\"]){" in media_body,
   "the page's own :root rule is guarded IN PLACE, not merely shadowed")
ok(not re.search(r"\{\s*:root\s*\{", media_body),
   "no bare :root rule is left inside the media query — this is the "
   "explicit-light-on-dark-OS bug", media_body[:120])
ok(':root:not([data-theme="light"]) img.drw' in media_body
   and ':root:not([data-theme="light"]) .zwrap img' in media_body,
   "a multi-part selector is guarded on every part, not just the first")

ok(':root[data-theme="dark"]{' in out, "an explicit dark choice gets the palette")
ok(':root[data-theme="dark"] img.drw' in out, "and the component rules with it")
ok(out.count("--bg:#141414") == 2, "dark value appears once per state, not more",
   out.count("--bg:#141414"))
ok("--bg:#fff" in out and out.index("--bg:#fff") < out.index("@media"),
   "the light palette is untouched and still first")
ok(".card{background:var(--bg)}" in out, "rules after the media block are untouched")
ok("#liveBar.lb-live" in out, "the banner gets dark skins in both states")
ok(out.count("--lbBg:#14301e") == 2, "banner skin once per state",
   out.count("--lbBg:#14301e"))

print("\n1b. a page with more than one dark block")
TWO = SAMPLE + """
@media (prefers-color-scheme: dark){
  .flane .tag{background:rgba(0,0,0,.45)}
}
"""
out2b, n2b = theme.apply(TWO)
ok(n2b == 3, "rules across both blocks are counted", n2b)
ok(out2b.count(':root:not([data-theme="light"]) .flane .tag') == 1,
   "the appended block is guarded too — an unguarded second block is the same bug")
ok(':root[data-theme="dark"] .flane .tag' in out2b,
   "and answers an explicit dark choice")
ok(out2b.count("--lbBg:#14301e") == 2,
   "banner skins are emitted once, not once per block", out2b.count("--lbBg:#14301e"))

print("\n2. a page with no dark palette")
single = ":root{ --bg:#fff }\nbody{background:var(--bg)}\n"
out2, n2 = theme.apply(single)
ok(out2 == single and n2 == 0,
   "left exactly as written — single-theme by design is an answer, not a gap")

print("\n3. the real boards")
root = pathlib.Path(__file__).resolve().parent.parent
for name in ("Gavin_schedule_MOBILE.live.html", "Gavin_schedule_DESK.live.html"):
    f = root / name
    if not f.exists():
        print("  --   %s not built, skipped" % name)
        continue
    html = f.read_text(encoding="utf-8")
    css = html[html.index("<style>"):html.index("</style>")]
    media = css[css.index("@media (prefers-color-scheme: dark)"):]
    media = media[:media.index("\n}\n") + 3] if "\n}\n" in media else media
    ok(not re.search(r"\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{", css),
       "%s: no unguarded :root inside the dark media query" % name)
    ok(':root[data-theme="dark"]' in css,
       "%s: explicit dark choice is answered" % name)
    # every token the dark block sets must also be set in the explicit block
    dark_tokens = set(re.findall(r"(--[a-zA-Z0-9]+)\s*:", media))
    explicit = css[css.index(':root[data-theme="dark"]'):]
    missing = sorted(t for t in dark_tokens if t + ":" not in explicit.replace(" ", ""))
    ok(not missing, "%s: every dark token is carried into the explicit block" % name,
       missing[:8])

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
