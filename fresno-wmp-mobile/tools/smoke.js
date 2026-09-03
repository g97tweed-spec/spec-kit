/* Smoke test for the live board.
 *
 * Loads the built page under jsdom with a stubbed Microsoft 365 connector and
 * asserts the four states the field will actually hit: a good live read, a
 * connector that is not there, an expired token, and a second open with no
 * signal but a warm cache. It also asserts the two things a refresh must never
 * do — drop a crew lane assignment, or give two overlapping clearances the same
 * colour.
 *
 *   node build/smoke.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require(process.env.JSDOM ||
  "/tmp/claude-0/-home-user-spec-kit/3b825c4a-09ec-5d15-97cc-c9efe5430fe7/scratchpad/node_modules/jsdom");

/* Runs against either board: node tools/smoke.js [built-page.html]
   The live layer is identical on both, so the same six states are asserted on
   whichever page is handed in. */
const FILE = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(__dirname, "..", "Gavin_schedule_MOBILE.live.html");
const HTML = fs.readFileSync(FILE, "utf8");
console.log("smoke: " + path.basename(FILE));

let pass = 0, fail = 0;
function ok(cond, label, extra) {
  if (cond) { pass++; console.log("  ok   " + label); }
  else { fail++; console.log("  FAIL " + label + (extra ? "  -> " + extra : "")); }
}

/* A payload shaped exactly like caldata.json, per caltemplate.html's reader:
   days{date:[tag]}, clearances[], still_open[], generated/swept/tracker/tab. */
function payload(day) {
  return {
    job: "16507610870", contractor: "PAR", tracker: "WMP Fresno Dependency Tracker 9-14-26.xlsm",
    tab: "9.14.26", generated: day, swept: day + "T14:02:00Z", win: [day, day],
    days: {
      [day]: [
        { n: 133636998, st: "021/401", ln: "COPUS-OLD RIVER", kv: "70", mat: "921",
          hq: "Bakersfield", desc: "JIT INST SHNT", act: "JIT INST SHNT", anytime: false,
          sev: "bad", ss: day, se: day,
          flags: [{ code: "NO_CLR_ON_DATE", sev: "bad", t: "No outage covers the planned date", src: "sweep" }],
          clrs: [] },
        { n: 131176541, st: "016/266", ln: "COPUS-OLD RIVER", kv: "70", mat: "ICW",
          hq: "Bakersfield", desc: "RPR CNDW", act: "RPR CNDW", anytime: true,
          sev: "ok", ss: day, se: day, flags: [], clrs: [] }
      ]
    },
    clearances: [
      { clearance_id: "AFW-T26-009001", type: "T-line clearance", line: "COPUS-OLD RIVER",
        start: day, end: day, window: "07:00-17:00", points: "016/266 to 017/293",
        purpose: "Shunt splice", structures: ["016/266"], source_subject: "Clearance",
        source_from: "pge", source_date: day },
      { clearance_id: "AFW-26-0099002", type: "Distribution NTO", line: "COPUS-OLD RIVER",
        start: day, end: day, window: "08:00-16:00", structures: [],
        source_subject: "NTO", source_from: "pge", source_date: day }
    ],
    still_open: [{ item: "LZ02 right of way", detail: "BLM approval outstanding", who: "Stantec" }]
  };
}

function makeDom(claudeStub, storage) {
  const vc = new VirtualConsole();
  const errors = [];
  vc.on("jsdomError", e => errors.push(String(e && e.message || e)));
  vc.on("error", (...a) => errors.push(a.join(" ")));

  const dom = new JSDOM(HTML, {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    url: "https://example.invalid/board",
    virtualConsole: vc,
    beforeParse(w) {
      // localStorage that persists across the two opens in the cache test
      const mem = storage;
      Object.defineProperty(w, "localStorage", {
        value: {
          getItem: k => (k in mem ? mem[k] : null),
          setItem: (k, v) => { mem[k] = String(v); },
          removeItem: k => { delete mem[k]; },
          clear: () => { for (const k in mem) delete mem[k]; }
        }, configurable: true
      });
      w.claude = claudeStub;
      w.matchMedia = w.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {},
        addEventListener() {}, removeEventListener() {} }));
      w.scrollTo = () => {};
      // jsdom implements no layout, so these are absent rather than no-ops
      w.Element.prototype.scrollIntoView = function () {};
      w.HTMLElement.prototype.scrollIntoView = function () {};
    }
  });
  return { dom, errors };
}

const settle = () => new Promise(r => setTimeout(r, 250));

function bar(dom) {
  const el = dom.window.document.getElementById("liveBar");
  return el ? el.textContent.replace(/\s+/g, " ").trim() : "";
}
/* Top-level `const` in a classic script lands in the global lexical scope,
   not on `window`, so the board's own bindings are read back through eval in
   the page's realm rather than off the window object. */
function ev(dom, expr) {
  try { return dom.window.eval(expr); } catch (e) { return undefined; }
}
function counts(dom) {
  return { tags: ev(dom, "TAGS.length"), afws: ev(dom, "AFWS.length") };
}

async function run() {
  /* The board opens on the device's today, so the fixture has to use the same
     day the board will compute — a hardcoded date passes until midnight and
     then starts failing for a reason that has nothing to do with the code. */
  const n = new Date();
  const DAY = n.getFullYear() + "-" + String(n.getMonth() + 1).padStart(2, "0")
            + "-" + String(n.getDate()).padStart(2, "0");

  /* ---- 1. live read succeeds ------------------------------------------- */
  console.log("\n1. connector answers with a fresh payload");
  {
    const calls = [];
    const stub = { use: async n => n !== "mcp" ? null : {
      callTool: async (server, tool, input) => {
        calls.push({ server, tool, uri: input.uri });
        const name = input.uri.split("/").pop();
        if (name === "_last_run.json")
          return { payload: { last_build: DAY, last_swept: DAY + "T14:02:00Z",
                              tracker_file: "WMP Fresno Dependency Tracker 9-14-26.xlsm",
                              tracker_tab: "9.14.26" } };
        if (name === "caldata.json") return { payload: payload(DAY) };
        throw { code: "tool_error", message: "no such file" };
      }
    }};
    const { dom, errors } = makeDom(stub, {});
    await settle();
    const c = counts(dom);
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(c.tags === 2, "TAGS replaced by the feed (2)", "got " + c.tags);
    ok(c.afws === 2, "AFWS replaced by the feed (2)", "got " + c.afws);
    ok(/Up to date/.test(bar(dom)), "banner reports up to date", bar(dom).slice(0, 90));
    ok(/9\.14\.26/.test(bar(dom)), "banner names the tracker tab it read");
    ok(calls.some(x => x.server === "Microsoft 365" && x.tool === "read_resource"),
       "called Microsoft 365 read_resource");
    ok(calls.every(x => /^file:\/\/\/b!/.test(x.uri)), "used file:/// drive URIs");

    // overlapping clearances must not share a colour
    const a = ev(dom, 'AFWCOL["AFW-T26-009001"]'), b = ev(dom, 'AFWCOL["AFW-26-0099002"]');
    ok(a && b && a[2] !== b[2], "overlapping clearances get different colours",
       JSON.stringify([a, b]));

    // the tag the feed flags must reach the rendered day
    const body = dom.window.document.body.textContent;
    ok(/021\/401/.test(body), "feed tag rendered on the board");

    // Desk calendar only: its "clear the board" button restores a frozen copy
    // of the opening lanes. Left on snapshot values it would wipe every tag the
    // feed brought and resurrect ones it dropped.
    if (ev(dom, 'typeof baseline') === "object") {
      const bKeys = ev(dom, "Object.keys(baseline).sort().join(',')");
      const pKeys = ev(dom, "Object.keys(state.place).sort().join(',')");
      ok(bKeys === pKeys, "reset baseline is rebuilt to match the feed", bKeys);
      ok(bKeys === "131176541,133636998", "and holds the feed's tags, not the snapshot's", bKeys);
    }
  }

  /* ---- 2. no connector -------------------------------------------------- */
  console.log("\n2. viewer has no Microsoft 365 connector");
  {
    const stub = { use: async () => null };
    const { dom, errors } = makeDom(stub, {});
    await settle();
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(/built-in snapshot/i.test(bar(dom)), "falls back to the snapshot, and says so", bar(dom).slice(0, 90));
    ok(counts(dom).tags > 100, "snapshot tags still on the board", String(counts(dom).tags));
  }

  /* ---- 3. token lapsed -------------------------------------------------- */
  console.log("\n3. connector token has expired");
  {
    const stub = { use: async n => n !== "mcp" ? null : {
      callTool: async () => { throw { code: "needs_reauth", message: "token expired" }; }
    }};
    const { dom, errors } = makeDom(stub, {});
    await settle();
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(/reconnect/i.test(bar(dom)), "banner names the actual fix (reconnect)", bar(dom).slice(0, 120));
    ok(!/something went wrong/i.test(bar(dom)), "no generic catch-all message");
  }

  /* ---- 4. warm cache, then no signal ------------------------------------ */
  console.log("\n4. second open in the field with no signal");
  {
    const mem = {};
    const good = { use: async n => n !== "mcp" ? null : {
      callTool: async (s, t, i) => {
        const name = i.uri.split("/").pop();
        if (name === "_last_run.json") return { payload: { last_build: DAY } };
        if (name === "caldata.json") return { payload: payload(DAY) };
        throw { code: "tool_error", message: "nope" };
      }
    }};
    const first = makeDom(good, mem);
    await settle();
    ok(Object.keys(mem).some(k => k.indexOf("fresno-wmp-live") === 0),
       "successful read is cached on the device", Object.keys(mem).join(","));

    // assign a crew lane, as a foreman would, then reopen offline
    const notif = ev(first.dom, "TAGS[0].id");
    ev(first.dom, 'state.place["' + notif + '"].lane = "Thomas"');
    mem["fresno-wmp-monthcal-v2"] = ev(first.dom, "JSON.stringify(state)");

    const dead = { use: async n => n !== "mcp" ? null : {
      callTool: async () => { throw { code: "server_unavailable", message: "unreachable", retryable: true }; }
    }};
    const second = makeDom(dead, mem);
    await settle();
    ok(second.errors.length === 0, "no page errors", second.errors[0]);
    ok(counts(second.dom).tags === 2, "board renders from the cached feed, not the snapshot",
       String(counts(second.dom).tags));
    ok(/offline copy/i.test(bar(second.dom)), "banner says it is the offline copy", bar(second.dom).slice(0, 100));
    ok(ev(second.dom, 'state.place["' + notif + '"] && state.place["' + notif + '"].lane') === "Thomas",
       "crew lane assignment survived the refresh",
       ev(second.dom, 'JSON.stringify(state.place["' + notif + '"])'));
  }

  /* ---- 5. the trimmed feed ---------------------------------------------- */
  console.log("\n5. pipeline emits the trimmed feed");
  {
    /* Shape mirrors pipeline/mobile_feed.py: short keys, empty fields omitted,
       `v` stamped so the board picks the reader by shape rather than filename. */
    const trimmed = {
      v: 1, src: "caldata.json", generated: DAY, swept: DAY + "T14:02:00Z",
      tracker: "WMP Fresno Dependency Tracker 9-14-26.xlsm", tab: "9.14.26",
      win: [DAY, DAY],
      days: { [DAY]: [
        { n: "133636998", st: "021/401", ln: "COPUS-OLD RIVER", mat: "921", w: "JIT INST SHNT",
          kv: "70", hq: "Bakersfield", sev: "bad", ss: DAY, se: DAY,
          f: ["No outage covers the planned date", "Readiness gate not met"], nr: 1 },
        { n: "131176541", st: "016/266", ln: "COPUS-OLD RIVER", mat: "ICW", w: "RPR CNDW",
          kv: "70", hq: "Bakersfield", sev: "ok", at: 1 }
      ]},
      clr: [
        { id: "AFW-T26-009001", ty: "T-line clearance", ln: "COPUS-OLD RIVER", d0: DAY, d1: DAY,
          win: "07:00-17:00", pts: "016/266 to 017/293", why: "Shunt splice", st: ["016/266"],
          src: "Clearance — pge — " + DAY },
        { id: "AFW-26-0099002", ty: "Distribution NTO", ln: "COPUS-OLD RIVER", d0: DAY, d1: DAY,
          win: "08:00-16:00", x: 1 }
      ],
      open: [{ item: "LZ02 right of way", detail: "BLM approval outstanding", who: "Stantec" }],
      n_tags: 2, n_clr: 2
    };
    const asked = [], askedUris = [];
    const stub = { use: async n => n !== "mcp" ? null : {
      callTool: async (s, t, i) => {
        const name = i.uri.split("/").pop();
        asked.push(name); askedUris.push(i.uri);
        if (name === "_last_run.json") return { payload: { last_build: DAY } };
        if (name === "mobile_feed.json") return { payload: trimmed };
        throw { code: "tool_error", message: "should not have been asked for " + name };
      }
    }};
    const { dom, errors } = makeDom(stub, {});
    await settle();
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(asked.indexOf("mobile_feed.json") >= 0, "asks for the trimmed feed", asked.join(","));
    ok(asked.indexOf("caldata.json") < 0,
       "and does not also pull the 1.4 MB payload once the trim answers", asked.join(","));
    // the shared copy is tried before the personal one, so a colleague with
    // access to the project folder gets live data rather than the snapshot
    const first = askedUris.filter(u => u.indexOf("_last_run") < 0)[0] || "";
    ok(/Fresno WMP 2026/.test(first) && /Programs/.test(first),
       "reads the team folder on PARDivision7 first", first);
    ok(counts(dom).tags === 2 && counts(dom).afws === 2, "board reads the trimmed shape",
       JSON.stringify(counts(dom)));
    ok(/Up to date/.test(bar(dom)) && /9\.14\.26/.test(bar(dom)),
       "banner reads the same off either format", bar(dom).slice(0, 80));
    ok(ev(dom, 'TAGS[0].flag') === "No outage covers the planned date",
       "flag line is the pipeline's own words", ev(dom, 'TAGS[0].flag'));
    ok(ev(dom, 'NOTREADY.has("133636998")') === true,
       "readiness set is rebuilt from the feed, not left on snapshot values");
    ok(ev(dom, 'NOTREADY.has("133366379")') === false,
       "and a snapshot tag the feed no longer flags is cleared");
    ok(ev(dom, 'TAGS[0].pri') === "", "priority stays blank when nothing knows it",
       ev(dom, 'TAGS[0].pri'));
    ok(ev(dom, 'AFWS[1].cancelled') === true, "cancelled clearance stays cancelled");
    ok(/021\/401/.test(dom.window.document.body.textContent), "trimmed tag rendered on the board");
  }

  /* ---- 6. trimmed feed missing, caldata still there ---------------------- */
  console.log("\n6. build made before the trim step existed");
  {
    const stub = { use: async n => n !== "mcp" ? null : {
      callTool: async (s, t, i) => {
        const name = i.uri.split("/").pop();
        if (name === "_last_run.json") return { payload: { last_build: DAY } };
        if (name === "caldata.json") return { payload: payload(DAY) };
        throw { code: "tool_error", message: "no such file" };
      }
    }};
    const { dom, errors } = makeDom(stub, {});
    await settle();
    ok(errors.length === 0, "no page errors", errors[0]);
    ok(counts(dom).tags === 2, "falls through to caldata.json and still goes live",
       String(counts(dom).tags));
    ok(/Up to date/.test(bar(dom)), "banner still reports up to date", bar(dom).slice(0, 60));
  }

  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
}

run().catch(e => { console.error(e); process.exit(1); });
