/* The merged board.
 *
 *   node tools/test_merged.js
 *
 * Two things to prove. First that carrying both boards inert and waking one
 * did not break either — the losing board must contribute no rules, no
 * elements and no listeners. Second the reason for merging at all: an
 * assignment made in the field view has to reach the desk view, which it never
 * could while they were two artifacts with two stores.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require(process.env.JSDOM ||
  "/tmp/claude-0/-home-user-spec-kit/3b825c4a-09ec-5d15-97cc-c9efe5430fe7/scratchpad/node_modules/jsdom");

const HTML = fs.readFileSync(path.join(__dirname, "..", "Gavin_schedule_BOARD.live.html"), "utf8");
let pass = 0, fail = 0;
function ok(c, label, extra) {
  if (c) { pass++; console.log("  ok   " + label); }
  else { fail++; console.log("  FAIL " + label + (extra ? "  -> " + extra : "")); }
}

/* One store, shared by every page in this run — which is the point. */
function makeStore() {
  const docs = new Map(), subs = new Map();
  const snap = p => ({ id: p.split("/").pop(), exists: docs.has(p),
    data: () => (docs.has(p) ? JSON.parse(JSON.stringify(docs.get(p))) : undefined) });
  const notify = p => (subs.get(p) || []).forEach(fn => fn(snap(p)));
  const merge = (t, patch) => {
    Object.keys(patch).forEach(k => {
      const v = patch[k];
      t[k] = (v && typeof v === "object" && !Array.isArray(v))
        ? merge(t[k] && typeof t[k] === "object" ? t[k] : {}, v) : v;
    });
    return t;
  };
  return { docs, api: { doc(p) { return {
    id: p.split("/").pop(), path: p,
    async get() { return snap(p); },
    async set(d) { docs.set(p, JSON.parse(JSON.stringify(d))); notify(p); },
    async update(d) {
      if (!docs.has(p)) { const e = new Error("absent"); e.code = "invalid_argument"; throw e; }
      docs.set(p, merge(docs.get(p), JSON.parse(JSON.stringify(d)))); notify(p);
    },
    onSnapshot(next) {
      if (!subs.has(p)) subs.set(p, []);
      subs.get(p).push(next);
      setTimeout(() => next(snap(p)), 0);
      return () => {};
    } }; } } };
}

function open(view, store, storage) {
  const vc = new VirtualConsole(); const errors = [], navs = [];
  vc.on("jsdomError", e => {
    const m = String((e && e.message) || e);
    /* jsdom implements no navigation, so a reload surfaces here rather than
       happening. That is the signal the page tried to reload — location itself
       cannot be stubbed, it is non-configurable. */
    (/Not implemented:\s*navigation/i.test(m) ? navs : errors).push(m);
  });
  const mem = storage || {};
  if (view) mem["fresno-board-view"] = view;
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously", pretendToBeVisual: true,
    url: "https://example.invalid/b?__probe", virtualConsole: vc,
    beforeParse(w) {
      Object.defineProperty(w, "localStorage", { value: {
        getItem: k => (k in mem ? mem[k] : null),
        setItem: (k, v) => { mem[k] = String(v); },
        removeItem: k => { delete mem[k]; }, clear: () => {} }, configurable: true });
      w.claude = { use: async n => (n === "db" && store ? store.api : null) };
      w.matchMedia = q => ({ matches: /max-width/.test(q) && mem.__narrow === "1",
        addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
      w.scrollTo = () => {};
      w.Element.prototype.scrollIntoView = function () {};
      w.HTMLElement.prototype.scrollIntoView = function () {};
    },
  });
  return { dom, errors, navs, mem };
}
const ev = (d, x) => { try { return d.window.eval(x); } catch (e) { return undefined; } };
const settle = (ms = 350) => new Promise(r => setTimeout(r, ms));
const css = (d, id) => d.window.document.getElementById(id).media;
/* The boards share ten ids (scrim, tabs, zoom, zimg ...). Mounting both would
   make getElementById return whichever came first, silently wiring half of one
   board's controls to the other's elements. */
function dupeIds(dom) {
  const seen = new Set(), dupes = [];
  dom.window.document.querySelectorAll("[id]").forEach(el => {
    if (seen.has(el.id)) dupes.push(el.id); else seen.add(el.id);
  });
  return dupes;
}

async function run() {
  console.log("\n1. the field view wakes, and only the field view");
  {
    const { dom, errors } = open("field", null, {});
    await settle();
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(css(dom, "css-field") === "all", "its stylesheet is live", css(dom, "css-field"));
    ok(css(dom, "css-desk") === "not all",
       "the desk stylesheet stays inert — 50 shared class names never collide",
       css(dom, "css-desk"));
    const body = dom.window.document.getElementById("mount").innerHTML;
    ok(/id="strip"/.test(body), "field markup is mounted");
    ok(!/id="bReset"/.test(body), "desk markup is not");
    ok(dupeIds(dom).length === 0,
       "no duplicated element ids — the two boards share ten, and only one "
       + "board's markup is ever in the document", dupeIds(dom).join(","));
    ok(ev(dom, "typeof TAGS") === "undefined",
       "board globals stay inside their function — nothing leaks to the page");
  }

  console.log("\n2. the desk view wakes, and only the desk view");
  {
    const { dom, errors } = open("desk", null, {});
    await settle();
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(css(dom, "css-desk") === "all" && css(dom, "css-field") === "not all",
       "the other stylesheet stays inert");
    const body = dom.window.document.getElementById("mount").innerHTML;
    ok(/id="bReset"/.test(body), "desk markup is mounted");
    ok(!/id="strip"/.test(body), "field markup is not");
    ok(dupeIds(dom).length === 0, "no duplicated element ids here either",
       dupeIds(dom).join(","));
  }

  console.log("\n3. what a device gets before anyone chooses");
  {
    const wide = open(null, null, {});
    await settle();
    ok(css(wide.dom, "css-desk") === "all", "a monitor opens on the desk calendar");
    const phone = open(null, null, { __narrow: "1" });
    await settle();
    ok(css(phone.dom, "css-field") === "all", "a phone opens on the field board");
  }

  console.log("\n4. choosing a view");
  {
    const { dom, mem, navs } = open("desk", null, {});
    await settle();
    const btn = [...dom.window.document.querySelectorAll("#viewpick button")]
      .find(b => b.dataset.view === "field");
    ok(btn.getAttribute("aria-pressed") === "false", "the inactive view is not pressed");
    btn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    ok(mem["fresno-board-view"] === "field", "the choice is remembered on this device");
    ok(navs.length === 1, "and the page reloads into it rather than swapping in place",
       JSON.stringify(navs));
  }

  console.log("\n5. THE POINT: an assignment crosses between the two views");
  {
    const store = makeStore();
    const f = open("field", store, {});
    await settle();
    const notif = ev(f.dom, "window.__boardProbe && window.__boardProbe.firstTag()");
    ok(!!notif, "test hook reachable", String(notif));
    ev(f.dom, `window.__boardProbe.assign(${JSON.stringify(notif)}, "Thomas")`);
    await settle(500);
    const doc = store.docs.get("board/place");
    ok(doc && doc.place && doc.place[notif] && doc.place[notif].lane === "Thomas",
       "the field view wrote it to the shared store",
       JSON.stringify(doc && doc.place && doc.place[notif]));

    const d = open("desk", store, {});               // same store, other view
    await settle(500);
    const seen = ev(d.dom, `window.__boardProbe.laneOf(${JSON.stringify(notif)})`);
    ok(seen === "Thomas",
       "and the DESK view opens with it — the thing two artifacts could never do",
       String(seen));
  }

  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
}
run().catch(e => { console.error(e); process.exit(1); });
