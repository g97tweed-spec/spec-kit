/* Shared board state, under a stub store.
 *
 *   node tools/test_share.js [built-page.html]
 *
 * The stub is a real one: two pages share one store, writes merge per key the
 * way update() does, and subscribers are notified. That lets the tests assert
 * the thing that actually matters — that a lane assigned on one board appears
 * on the other, and that two people editing different tags do not overwrite
 * each other.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require(process.env.JSDOM ||
  "/tmp/claude-0/-home-user-spec-kit/3b825c4a-09ec-5d15-97cc-c9efe5430fe7/scratchpad/node_modules/jsdom");

const FILE = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(__dirname, "..", "Gavin_schedule_MOBILE.live.html");
const HTML = fs.readFileSync(FILE, "utf8");
console.log("share: " + path.basename(FILE));

let pass = 0, fail = 0;
function ok(cond, label, extra) {
  if (cond) { pass++; console.log("  ok   " + label); }
  else { fail++; console.log("  FAIL " + label + (extra ? "  -> " + extra : "")); }
}

/* ---- the stub store -----------------------------------------------------
   Mirrors the contract the board is written against: set() replaces, update()
   merges nested objects one level down and REJECTS invalid_argument when the
   document is absent, onSnapshot fires on every change. */
function makeStore() {
  const docs = new Map();
  const subs = new Map();
  const notify = p => (subs.get(p) || []).forEach(fn => fn(snapshot(p)));
  const snapshot = p => ({
    id: p.split("/").pop(),
    exists: docs.has(p),
    data: () => (docs.has(p) ? JSON.parse(JSON.stringify(docs.get(p))) : undefined),
  });
  function merge(target, patch) {
    Object.keys(patch).forEach(k => {
      const v = patch[k];
      if (v && typeof v === "object" && !Array.isArray(v)) {
        target[k] = merge(target[k] && typeof target[k] === "object" ? target[k] : {}, v);
      } else target[k] = v;
    });
    return target;
  }
  const writes = [];
  return {
    docs, writes,
    api: {
      doc(p) {
        return {
          id: p.split("/").pop(), path: p,
          async get() { return snapshot(p); },
          async set(data) { writes.push(["set", p]); docs.set(p, JSON.parse(JSON.stringify(data))); notify(p); },
          async update(data) {
            writes.push(["update", p]);
            if (!docs.has(p)) { const e = new Error("no such document"); e.code = "invalid_argument"; throw e; }
            docs.set(p, merge(docs.get(p), JSON.parse(JSON.stringify(data))));
            notify(p);
          },
          onSnapshot(next) {
            if (!subs.has(p)) subs.set(p, []);
            subs.get(p).push(next);
            setTimeout(() => next(snapshot(p)), 0);
            return () => {};
          },
        };
      },
    },
  };
}

function open(store, storage, mcpNull) {
  const vc = new VirtualConsole();
  const errors = [];
  vc.on("jsdomError", e => errors.push(String((e && e.message) || e)));
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously", pretendToBeVisual: true,
    url: "https://example.invalid/board", virtualConsole: vc,
    beforeParse(w) {
      const mem = storage;
      Object.defineProperty(w, "localStorage", {
        value: {
          getItem: k => (k in mem ? mem[k] : null),
          setItem: (k, v) => { mem[k] = String(v); },
          removeItem: k => { delete mem[k]; }, clear: () => {},
        }, configurable: true,
      });
      w.claude = {
        use: async n => (n === "db" ? (store ? store.api : null) : (mcpNull ? null : null)),
      };
      w.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {},
        addEventListener() {}, removeEventListener() {} });
      w.scrollTo = () => {};
      w.Element.prototype.scrollIntoView = function () {};
      w.HTMLElement.prototype.scrollIntoView = function () {};
    },
  });
  return { dom, errors };
}
const ev = (dom, expr) => { try { return dom.window.eval(expr); } catch (e) { return undefined; } };
const settle = (ms = 300) => new Promise(r => setTimeout(r, ms));

async function run() {
  console.log("\n1. an assignment reaches the store");
  const store = makeStore();
  const a = open(store, {});
  await settle();
  ok(a.errors.length === 0, "no page errors", a.errors[0]);
  const tag = ev(a.dom, "TAGS[0].id");
  ev(a.dom, `state.place["${tag}"].lane = "Thomas"; save();`);
  await settle(500);
  const doc = store.docs.get("board/place");
  ok(!!doc && doc.place && doc.place[tag] && doc.place[tag].lane === "Thomas",
     "the lane is written to the shared document", JSON.stringify(doc && doc.place && doc.place[tag]));
  ok(store.writes.some(w => w[0] === "set"),
     "the first write creates the document, since update() cannot", JSON.stringify(store.writes[0]));

  console.log("\n2. a second person opening the board sees it");
  const b = open(store, {});          // different device: empty localStorage
  await settle();
  ok(b.errors.length === 0, "no page errors", b.errors[0]);
  ok(ev(b.dom, `state.place["${tag}"].lane`) === "Thomas",
     "the other board opens with the assignment already on it",
     ev(b.dom, `state.place["${tag}"].lane`));

  console.log("\n3. a change on one board lands on the other, live");
  const tag2 = ev(b.dom, "TAGS[1].id");
  ev(b.dom, `state.place["${tag2}"].lane = "Jose"; save();`);
  await settle(500);
  ok(ev(a.dom, `state.place["${tag2}"].lane`) === "Jose",
     "the first board receives it without a reload", ev(a.dom, `state.place["${tag2}"].lane`));
  ok(ev(a.dom, `state.place["${tag}"].lane`) === "Thomas",
     "and its own earlier assignment is untouched");

  console.log("\n4. two people, two different tags, no clobbering");
  const t3 = ev(a.dom, "TAGS[2].id"), t4 = ev(a.dom, "TAGS[3].id");
  ev(a.dom, `state.place["${t3}"].lane = "Alex"; save();`);
  ev(b.dom, `state.place["${t4}"].lane = "Thomas"; save();`);
  await settle(700);
  const p = store.docs.get("board/place").place;
  ok(p[t3] && p[t3].lane === "Alex" && p[t4] && p[t4].lane === "Thomas",
     "both survive — update() merges per key rather than replacing the map",
     JSON.stringify([p[t3], p[t4]]));
  ok(p[tag].lane === "Thomas" && p[tag2].lane === "Jose",
     "and the earlier two are still there");

  console.log("\n5. notes are shared, view state is not");
  ev(a.dom, `state.dnotes["2026-09-08"] = "call Hernandez before rolling"; ` +
            `state.closed["something"] = 1; save();`);
  await settle(500);
  const notes = store.docs.get("board/notes");
  ok(notes && notes.dnotes && notes.dnotes["2026-09-08"] === "call Hernandez before rolling",
     "the day note is shared");
  ok(!notes.closed, "collapsed sections are NOT — that is this person's screen, not a decision",
     JSON.stringify(Object.keys(notes || {})));

  console.log("\n6. no store at all");
  const c = open(null, {});
  await settle();
  ok(c.errors.length === 0, "no page errors", c.errors[0]);
  const t5 = ev(c.dom, "TAGS[0].id");
  ev(c.dom, `state.place["${t5}"].lane = "Alex"; save();`);
  await settle(300);
  ok(ev(c.dom, `state.place["${t5}"].lane`) === "Alex",
     "the board still works, keeping state on the device as it always did");

  console.log("\n7. a viewer who cannot write");
  const ro = makeStore();
  ro.api.doc = (p => {
    const base = makeStore().api.doc(p);
    return Object.assign({}, base, {
      async get() { return { id: p, exists: false, data: () => undefined }; },
      async set() { const e = new Error("read only"); e.code = "permission_denied"; throw e; },
      async update() { const e = new Error("read only"); e.code = "permission_denied"; throw e; },
      onSnapshot() { return () => {}; },
    });
  });
  const d = open(ro, {});
  await settle();
  const t6 = ev(d.dom, "TAGS[0].id");
  ev(d.dom, `state.place["${t6}"].lane = "Jose"; save();`);
  await settle(500);
  ok(d.errors.length === 0, "no page errors", d.errors[0]);
  ok(ev(d.dom, `state.place["${t6}"].lane`) === "Jose",
     "their own change still shows on their screen");
  const notice = d.dom.window.document.getElementById("shareBar");
  ok(notice && /device only/i.test(notice.textContent),
     "and they are told, on a line that stays put, that it went no further",
     notice && notice.textContent);
  ok(notice && /view access/i.test(notice.textContent),
     "naming the actual reason — view access, not a mystery failure",
     notice && notice.textContent);

  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
}
run().catch(e => { console.error(e); process.exit(1); });
