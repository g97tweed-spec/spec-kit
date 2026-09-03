/* =========================================================================
   SHARED BOARD STATE
   ------------------
   Crew lanes, day notes and resources are the foreman's, not the pipeline's.
   Until now they lived in this browser's localStorage, which meant they never
   left the device they were typed on — not to a colleague, not even from the
   phone to the desk. Assigning tomorrow's Copus work to Thomas was a note to
   self that looked like a plan.

   These now live in the artifact's shared store, so everyone who opens the
   board sees the same assignments, and anyone who can open it can change them.

   WHAT IS SHARED, AND WHAT IS NOT
     Shared:  who is on each tag, which day it sits on, day and month notes,
              resources, vendor and field notes — the things that are a
              decision about the work.
     Local:   which sections are collapsed, which job packages are expanded —
              view state. Sharing those would mean one person's scrolling
              rearranging someone else's screen.

   HOW CONCURRENT EDITS BEHAVE
     Both documents are keyed maps, written with update(), whose nested merge
     applies one key without touching the rest. Two people moving two different
     tags merge cleanly. Two people moving the SAME tag within the same moment
     is last-writer-wins, which for one tag and two foremen is the right answer
     anyway — the board shows what the second person decided, to both of them.

   WHEN THE STORE IS NOT THERE
     Opened as a file from OneDrive there is no store, and none of this runs:
     the board keeps its own state on the device exactly as before. Everything
     here is an upgrade on top of a board that already works without it.
   ========================================================================= */

const SHARE = {
  /* Two documents rather than one per tag: an artifact's store holds 5,000
     documents in total, and a per-tag scheme would spend a quarter of that on
     one board. Both stay far inside the 256 KiB body cap — ~1,200 assignments
     is about 50 KB. */
  placeDoc: "board/place",
  notesDoc: "board/notes",
  /* Slices of `state` that are a decision about the work, and therefore
     everyone's. Anything not listed stays on the device. */
  keys: ["res", "notes", "dnotes", "vend", "fnotes", "vadd"],
  db: null,
  ready: false,
  applying: false,   /* true while writing a remote change in, to not echo it back */
  pushed: null,      /* last state we sent, to diff against */
  subs: []
};

function shareClone(o){ try{ return JSON.parse(JSON.stringify(o)); }catch(e){ return {}; } }

/* What we would send right now, so a later save() can be diffed against it. */
function shareSnapshot(){
  const out = {place:{}};
  Object.keys(state.place).forEach(function(k){
    const p = state.place[k];
    out.place[k] = {d: p.d || "", lane: p.lane || "unassigned"};
  });
  SHARE.keys.forEach(function(k){ out[k] = shareClone(state[k] || {}); });
  return out;
}

/* Only what changed, as a nested patch update() can merge. */
function sharePatch(now, before){
  const patch = {};
  const place = {};
  Object.keys(now.place).forEach(function(k){
    const a = now.place[k], b = before && before.place && before.place[k];
    if(!b || b.lane !== a.lane || b.d !== a.d) place[k] = a;
  });
  if(Object.keys(place).length) patch.place = place;

  const rest = {};
  SHARE.keys.forEach(function(k){
    const a = now[k] || {}, b = (before && before[k]) || {};
    const sub = {};
    Object.keys(a).forEach(function(id){
      if(JSON.stringify(a[id]) !== JSON.stringify(b[id])) sub[id] = a[id];
    });
    if(Object.keys(sub).length) rest[k] = sub;
  });
  return {place: patch.place || null, rest: Object.keys(rest).length ? rest : null};
}

/* update() merges but requires the document to exist; set() creates but
   replaces wholesale. Try the merge, create only on the miss. */
async function shareWrite(path, body){
  const ref = SHARE.db.doc(path);
  try{
    await ref.update(body);
  }catch(e){
    if(e && e.code === "invalid_argument"){
      try{ await ref.set(body); }catch(e2){ shareTrouble(e2); }
    }else{
      shareTrouble(e);
    }
  }
}

/* The field board has a toast; the desk calendar has no transient message
   surface at all. So the warning gets its own line under the freshness banner:
   present on both boards, and persistent, which suits it better than a toast
   anyway — "your assignments are not reaching anyone" should stay on screen. */
function shareNotice(msg){
  let el = document.getElementById("shareBar");
  if(!el){
    el = document.createElement("div");
    el.id = "shareBar";
    el.className = "lb-warn";
    const after = document.getElementById("liveBar");
    const host = document.querySelector("main") || document.querySelector(".page");
    if(after && after.parentNode) after.parentNode.insertBefore(el, after.nextSibling);
    else if(host && host.parentNode) host.parentNode.insertBefore(el, host);
    else return;
  }
  el.textContent = msg;
}

let shareBroken = false;
function shareTrouble(e){
  /* The board still works — it keeps writing to this device. But it also
     toasts "Saved on this device" after every change, and on its own that
     reads like success. Once sharing is known broken, that message is
     rewritten for the rest of the session, so a foreman is never left
     believing an assignment reached the crew when it stopped at the phone. */
  if(shareBroken) return;
  shareBroken = true;
  const code = (e && e.code) || "unknown";
  shareNotice(code === "revoked" || code === "permission_denied"
    ? "Saved on this device only — you have view access to this board, not edit."
    : "Saved on this device only — the shared board is unreachable, so changes "
      + "made here are not reaching anyone else.");
}

/* Push whatever has changed since the last push. Called after the board's own
   save(), which is already debounced. */
async function sharePush(){
  if(!SHARE.ready || SHARE.applying) return;
  const now = shareSnapshot();
  const d = sharePatch(now, SHARE.pushed);
  SHARE.pushed = now;
  if(d.place) await shareWrite(SHARE.placeDoc, {place: d.place});
  if(d.rest)  await shareWrite(SHARE.notesDoc, d.rest);
}

/* Apply a remote document to the board. */
function shareApplyPlace(data){
  if(!data || !data.place) return false;
  let touched = false;
  Object.keys(data.place).forEach(function(id){
    const p = data.place[id];
    if(!p || !state.place[id]) return;      /* a tag this build does not carry */
    if(state.place[id].lane !== p.lane || (p.d && state.place[id].d !== p.d)){
      state.place[id] = {d: p.d || state.place[id].d, lane: p.lane || "unassigned"};
      touched = true;
    }
  });
  return touched;
}
function shareApplyNotes(data){
  if(!data) return false;
  let touched = false;
  SHARE.keys.forEach(function(k){
    const incoming = data[k];
    if(!incoming) return;
    state[k] = state[k] || {};
    Object.keys(incoming).forEach(function(id){
      if(JSON.stringify(state[k][id]) !== JSON.stringify(incoming[id])){
        state[k][id] = incoming[id];
        touched = true;
      }
    });
  });
  return touched;
}

/* The board's lanes are rebuilt from PRESET whenever a feed lands, so the
   shared assignments have to go back on top afterwards. goLive() calls this. */
let shareLastPlace = null;
function shareReapply(){
  if(!SHARE.ready) return;
  const touched = shareLastPlace && shareApplyPlace(shareLastPlace);
  /* The feed rebuilt state.place, so what we believe we last pushed is stale.
     Re-baseline, or the next save would push the whole board back up as if the
     foreman had just reassigned every tag. */
  SHARE.pushed = shareSnapshot();
  if(touched) render();
}

async function goShared(){
  const db = await claude.use("db");
  if(!db) return;                      /* opened as a file, or not granted */
  SHARE.db = db;

  /* Seed from what is already stored before subscribing, so the first paint
     carries other people's assignments rather than flashing this device's. */
  try{
    const [p, n] = await Promise.all([
      db.doc(SHARE.placeDoc).get(),
      db.doc(SHARE.notesDoc).get()
    ]);
    let touched = false;
    if(p.exists){ shareLastPlace = p.data(); touched = shareApplyPlace(shareLastPlace) || touched; }
    if(n.exists){ touched = shareApplyNotes(n.data()) || touched; }
    if(touched) render();
  }catch(e){ shareTrouble(e); return; }

  SHARE.ready = true;
  SHARE.pushed = shareSnapshot();

  /* Live: someone else's change lands here without a reload. */
  SHARE.subs.push(db.doc(SHARE.placeDoc).onSnapshot(function(snap){
    if(!snap.exists) return;
    SHARE.applying = true;
    shareLastPlace = snap.data();
    const touched = shareApplyPlace(shareLastPlace);
    SHARE.pushed = shareSnapshot();
    SHARE.applying = false;
    if(touched) render();
  }, shareTrouble));

  SHARE.subs.push(db.doc(SHARE.notesDoc).onSnapshot(function(snap){
    if(!snap.exists) return;
    SHARE.applying = true;
    const touched = shareApplyNotes(snap.data());
    SHARE.pushed = shareSnapshot();
    SHARE.applying = false;
    if(touched) render();
  }, shareTrouble));

  /* Everything the board already does to persist a change ends in save().
     Wrapping it here means no call site had to learn about sharing. */
  const localSave = save;
  save = function(){
    localSave.apply(null, arguments);
    sharePush();
  };

  /* The board's own confirmation, corrected while sharing is down. Its toast
     fires after a debounce, so it would otherwise land on top of the warning
     and read as though the change had gone through to everyone. */
  if(typeof toast === "function"){
    const baseToast = toast;
    toast = function(m){
      if(shareBroken && m === "Saved on this device"){
        m = "Saved on this device only — not shared";
      }
      return baseToast(m);
    };
  }
}
