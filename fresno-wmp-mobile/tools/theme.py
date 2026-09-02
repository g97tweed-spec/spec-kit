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


def apply(css):
    """Return the stylesheet with all three viewer states handled.

    Returns it unchanged when the page declares no dark palette — that is a
    single-theme design, and giving it a dark ground it never reads would leave
    half the page light and half dark.
    """
    at = css.find(MEDIA)
    if at < 0:
        return css, 0

    open_at, close_at = _block_span(css, at)
    body = css[open_at + 1:close_at]
    rules = _rules(body)
    if not rules:
        return css, 0

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

    # 3. The banner, in both states.
    banner_sys = "\n".join("%s{%s}" % (_guard(s, GUARD_SYSTEM), d) for s, d in BANNER_DARK)
    banner_dark = "\n".join("%s{%s}" % (_guard(s, GUARD_DARK), d) for s, d in BANNER_DARK)

    out = (css[:open_at + 1]
           + guarded
           + "\n" + banner_sys + "\n"
           + css[close_at:close_at + 1]
           + "\n\n" + "\n".join(copy)
           + "\n" + banner_dark + "\n"
           + css[close_at + 1:])
    return out, len(rules)
