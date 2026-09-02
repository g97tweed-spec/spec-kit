"""Make a board's dark palette answer all three viewer states.

Both boards ship their dark colours behind `@media (prefers-color-scheme: dark)`
and nothing else. That covers a viewer on the OS default, which is what these
pages were built for — opened from Files, there is nothing but the OS to ask.

Published to claude.ai there is a third state. The viewer stamps
`data-theme="dark"` or `data-theme="light"` on the root element when someone
picks a theme explicitly, and stamps nothing on "system". So the page as
written has two faults:

  - someone who picks DARK gets the light palette, because nothing responds to
    the stamp
  - someone who picks LIGHT on a dark-mode OS gets the DARK palette, because
    the media query fires regardless of their choice

The second is the one worth being careful about, and the reason this rewrites
the page's existing block rather than only adding to it. An added
`:root:not([data-theme="light"])` rule does not stop the original `:root` rule
inside the media query from applying — it is still there, still matching. The
guard has to go on the original.

So: the page's own dark block is guarded in place, and a second copy is emitted
for the explicit-dark stamp. Every colour is the page's own — nothing here
invents a value or decides what dark should look like. A page with no dark
block at all is left alone; single-theme by design is a legitimate answer and
not something to synthesise a palette for.
"""

import re

MEDIA = "@media (prefers-color-scheme: dark)"

# The banner is the one thing on these pages that the boards themselves do not
# style, so its dark skins are declared here rather than derived. Values match
# the light ones in live.css, darkened the same way the boards darken theirs.
BANNER_DARK = [
    ("#liveBar.lb-live", "--lbBg:#14301e;--lbFg:#a8e0bd;--lbBd:#235c39"),
    ("#liveBar.lb-warn", "--lbBg:#33280f;--lbFg:#f0d49a;--lbBd:#5c4718"),
    ("#liveBar.lb-bad", "--lbBg:#331717;--lbFg:#f0b5b5;--lbBd:#5c2626"),
    ("#liveBar.lb-busy", "--lbBg:#1b222c;--lbFg:#b8c6d8;--lbBd:#2f3b4a"),
]

GUARD_SYSTEM = ':root:not([data-theme="light"])'
GUARD_DARK = ':root[data-theme="dark"]'


def _block_span(css, start):
    """Character span of the {...} beginning at or after `start`."""
    open_at = css.index("{", start)
    depth = 0
    i = open_at
    while True:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return open_at, i
        i += 1


def _rules(body):
    """Top-level (selector_span, selector, declarations) inside a media body.
    Comments are stripped from selectors but left in the body untouched."""
    out = []
    i = 0
    while True:
        brace = body.find("{", i)
        if brace < 0:
            return out
        raw = body[i:brace]
        sel = re.sub(r"/\*.*?\*/", "", raw, flags=re.S).strip()
        open_at, close_at = _block_span(body, i)
        if sel:
            sel_start = i + (len(raw) - len(raw.lstrip()))
            out.append(((sel_start, brace), sel, body[open_at + 1:close_at]))
        i = close_at + 1


def _guard(selector, guard):
    """`:root` becomes the guard itself; anything else is scoped under it, so
    `img.drw, .zwrap img` guards both halves and not just the first."""
    parts = []
    for one in selector.split(","):
        one = one.strip()
        if not one:
            continue
        parts.append(guard if one == ":root" else guard + " " + one)
    return ", ".join(parts)


def force_light(css):
    """Strip the dark palette: the page renders light for everyone.

    Every problem this board had in dark mode — the assigned tag chip, the note
    chip, the lane hint, the work description — was a colour chosen against a
    light ground still being used against a dark one. Removing the dark palette
    removes the class, rather than correcting its members one at a time.

    The page keeps its colour tokens; only the block that redefines them for
    dark goes. It already paints its own #fff ground, so it holds on a dark
    host. The viewer's theme toggle also writes an inline `color-scheme` on the
    root element, which would tint form controls and scrollbars even with every
    dark rule gone — hence the one !important, which is deliberate: the page is
    declaring a single theme, not competing over one.
    """
    out = []
    prev = 0
    removed = 0
    idx = 0
    while True:
        at = css.find(MEDIA, idx)
        if at < 0:
            break
        open_at, close_at = _block_span(css, at)
        out.append(css[prev:at])
        prev = close_at + 1
        idx = close_at + 1
        removed += 1
    out.append(css[prev:])
    body = "".join(out)
    if removed:
        body += ("\n/* Single-theme by choice: the dark palette was removed at build time"
                 "\n   by tools/theme.py force_light. See the README. */"
                 "\n:root{color-scheme:light !important}\n")
    return body, removed


def apply(css):
    """Return the stylesheet with all three viewer states handled.

    Every `prefers-color-scheme: dark` block is processed, not just the first —
    the build appends its own (see lane-contrast.css), and a block left
    unguarded is exactly the bug this module exists to prevent.

    Returns the stylesheet unchanged when the page declares no dark palette at
    all — that is a single-theme design, and giving it a dark ground it never
    reads would leave half the page light and half dark.
    """
    spans = []
    idx = 0
    while True:
        at = css.find(MEDIA, idx)
        if at < 0:
            break
        open_at, close_at = _block_span(css, at)
        spans.append((open_at, close_at))
        idx = close_at + 1
    if not spans:
        return css, 0

    out = []
    prev = 0
    total = 0
    first = True
    for open_at, close_at in spans:
        body = css[open_at + 1:close_at]
        rules = _rules(body)
        if not rules:
            continue
        total += len(rules)

        # 1. Guard the page's own block in place, back to front so the earlier
        #    spans stay valid.
        guarded = body
        for (s0, s1), sel, _ in reversed(rules):
            guarded = guarded[:s0] + _guard(sel, GUARD_SYSTEM) + guarded[s1:]

        # 2. Emit the same declarations again for an explicit dark choice.
        copy = ["/* Same palette again for a viewer who picked dark explicitly."
                "\n   Generated from the block above by tools/theme.py — edit that"
                "\n   block, not this one. */"]
        for _, sel, decls in rules:
            copy.append("%s{%s}" % (_guard(sel, GUARD_DARK), decls.strip()))

        # 3. The banner, once, alongside the first block that carries anything.
        banner_sys = banner_dark = ""
        if first:
            banner_sys = "\n" + "\n".join(
                "%s{%s}" % (_guard(s, GUARD_SYSTEM), d) for s, d in BANNER_DARK)
            banner_dark = "\n" + "\n".join(
                "%s{%s}" % (_guard(s, GUARD_DARK), d) for s, d in BANNER_DARK)
            first = False

        out.append(css[prev:open_at + 1])
        out.append(guarded)
        out.append(banner_sys + "\n")
        out.append(css[close_at:close_at + 1])
        out.append("\n\n" + "\n".join(copy) + banner_dark + "\n")
        prev = close_at + 1

    out.append(css[prev:])
    return "".join(out), total
