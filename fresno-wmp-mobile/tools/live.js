/* =========================================================================
   LIVE DATA
   ---------
   The board below this point is a snapshot: tags, AFW windows and work
   verification were read on SNAPSHOT and hardcoded. This module makes the page
   refresh itself when it is opened.

   Where the data comes from
     The Windows pipeline (WMP_Fresno_Tracker/pipeline) reconciles the
     dependency tracker, the clearance mail and the SharePoint job files, and
     writes its result to OneDrive as data/caldata.json. That file — not the
     workbook, not the mailbox — is what this page reads. Whatever the last
     pipeline run concluded is what the board shows.

   How it reads it
     Through the viewer's own Microsoft 365 connector, via the artifact mcp
     capability. The page never holds a credential; the call runs as whoever
     opened the page, and fails closed if they have no connector.

   What it does when it cannot reach it
     Falls back, in order: the copy cached in this browser from the last
     successful open, then the hardcoded snapshot. It always says which of the
     three it is showing, and how old that is. A board that silently shows
     three-day-old clearances is worse than no board.

   What it does NOT do
     It cannot make the pipeline run. If nobody has run the sweep since Friday,
     opening this page on Monday shows Friday's data — correctly labelled as
     Friday's. The banner reports the pipeline's own clock, not the page's.
   ========================================================================= */

const LIVE = {
  server: "Microsoft 365",
  tool: "read_resource",
  drive: "b!PRd2jUqlgUaMUN0sE5o2GNcEPkwp9rFDrMOpOikwnBOuBzwAhU8EQJgZcl3V4FMT",
  root: "Everything Folder/WMP_Fresno_Tracker/data",
  /* Tried in order. The pipeline has renamed its payload before; the first
     file that parses and carries a day map wins. */
  feeds: ["caldata.json", "cal3_payload.json"],
  stamp: "_last_run.json",
  cacheKey: "fresno-wmp-live-v1",
  state: "boot"      /* boot | live | cached | snapshot */
};
function liveUri(name){ return "file:///"+LIVE.drive+"/"+LIVE.root+"/"+name; }

/* ---------- the freshness line -------------------------------------------
   Replaces the old "Snapshot is N days old" bar. Three honest states, never
   one generic "couldn't update" — each names the thing that would fix it. */
function liveBar(){
  let el=document.getElementById("liveBar");
  if(!el){
    el=document.createElement("div");
    el.id="liveBar";
    const host=document.querySelector("main");
    if(host&&host.parentNode)host.parentNode.insertBefore(el,host);
    else return null;
  }
  return el;
}
/* Tone is a class, not an inline style: the four skins are defined against the
   board's own tokens so the banner follows the phone into dark mode with
   everything else, instead of staying a bright strip at the top of a dark
   screen at 5am. */
function setBar(tone,html){
  const el=liveBar(); if(!el)return;
  el.className="lb-"+(["live","warn","bad","busy"].indexOf(tone)>=0?tone:"busy");
  el.innerHTML=html;
}
function ago(iso){
  if(!iso)return "";
  const then=new Date(iso), now=new Date();
  if(isNaN(then))return "";
  const mins=Math.round((now-then)/60000);
  if(mins<0)return "just now";
  if(mins<90)return mins+" min ago";
  const hrs=Math.round(mins/60);
  if(hrs<36)return hrs+" h ago";
  return Math.round(hrs/24)+" days ago";
}

/* ---------- transform: pipeline payload -> this board's shape -------------
   caldata.json is keyed for the desktop discrepancy calendar. Field names are
   its, not ours: n=notification, st=structure, ln=line, ss/se=scheduled
   window, sev/flags=what is wrong with it. Nothing is invented here — a field
   the payload does not carry stays empty rather than being guessed at. */
/* Priority (E/P/F) is not in caldata.json — it lives in the Master Tag Tracker,
   which this page does not read. Carried across from the snapshot per
   notification where we already know it, and left blank where we do not,
   rather than substituting a field that means something else. */
const SNAP_PRI={};
TAGS.forEach(function(x){ SNAP_PRI[x.id]=x.pri; });

function fromFeed(D){
  const tags=[], afws=[], seen={};

  Object.keys(D.days||{}).forEach(function(date){
    (D.days[date]||[]).forEach(function(x){
      const id=String(x.n);
      if(seen[id])return;          /* a notif can appear twice; first date wins */
      seen[id]=1;
      /* The board's flag line is the worst thing the pipeline found, in its
         own words. Its severity ordering is bad > warn > info > ok. */
      const fl=(x.flags||[]).filter(function(f){return f.sev==="bad"||f.sev==="warn";});
      tags.push({
        id:id, notif:id,
        line:String(x.ln||""),
        st:String(x.st||""),
        w:String(x.act||x.desc||"").trim(),
        mat:String(x.mat||""),
        pri:SNAP_PRI[id]||"",
        d:date,
        flag:fl.length?fl[0].t:"",
        sev:x.sev||"",
        anytime:!!x.anytime,
        kv:x.kv||"", hq:x.hq||"",
        ss:x.ss||"", se:x.se||"",
        flags:x.flags||[],
        clrs:x.clrs||[]
      });
    });
  });

  (D.clearances||[]).forEach(function(c){
    if(!c||!c.start)return;
    afws.push({
      no:String(c.clearance_id||""),
      kind:String(c.type||"Type not stated"),
      ckt:String(c.line||""),
      d0:String(c.start||""), t0:"",
      d1:String(c.end||c.start||""), t1:"",
      window:c.window||"",
      scope:(c.structures||[]).join(", "),
      note:c.note||"",
      purpose:c.purpose||"",
      cancelled:!!c.cancelled,
      src:[c.source_subject,c.source_from,c.source_date].filter(Boolean).join(" — ")
    });
  });

  return {
    tags:tags, afws:afws,
    open:D.still_open||[],
    generated:D.generated||"", swept:D.swept||"",
    tracker:D.tracker||"", tab:D.tab||"",
    win:D.win||null
  };
}

/* Swap the feed into the board's own arrays. They are const bindings used all
   through the file, so the contents are replaced in place rather than the
   bindings reassigned. Crew lane assignments are keyed by notification and
   survive the swap — a refresh must never silently re-lane a crew's day. */
function applyFeed(F){
  if(!F||!F.tags||!F.tags.length)return false;

  /* load() only restores lanes for tags the snapshot already knew, so a lane a
     foreman put on a tag that arrived with the feed would be dropped on the
     next open. Read the saved map directly and merge both ways: what was
     stored, then anything assigned since this page loaded. */
  const lanes={};
  try{
    const raw=localStorage.getItem(KEY);
    if(raw){
      const s=JSON.parse(raw);
      if(s&&s.place)Object.keys(s.place).forEach(function(k){
        const l=s.place[k]&&s.place[k].lane;
        if(l&&l!=="unassigned")lanes[k]=l;
      });
    }
  }catch(e){}
  Object.keys(state.place).forEach(function(k){
    const l=state.place[k].lane;
    if(l&&l!=="unassigned")lanes[k]=l;
  });

  TAGS.length=0;  F.tags.forEach(function(t){ TAGS.push(t); });
  AFWS.length=0;  F.afws.forEach(function(a){ AFWS.push(a); });

  state.place={};
  TAGS.forEach(function(x){
    state.place[x.id]={ d:x.d, lane:lanes[x.id]||PRESET[x.id]||"unassigned" };
  });

  recolorAFW();
  return true;
}

/* Re-run the snapshot's own colour assignment over the new set: overlapping
   windows must not land on the same colour, or two live clearances read as one
   on the day strip. Same algorithm as the boot-time pass, not an index. */
function recolorAFW(){
  Object.keys(AFWCOL).forEach(function(k){ delete AFWCOL[k]; });
  const list=AFWS.filter(function(a){ return !a.unknown&&!a.status; });
  const overlap=function(a,b){ return a.d0<=b.d1&&b.d0<=a.d1; };
  list.forEach(function(a){
    if(AFWCOL[a.no])return;
    const used=new Set();
    list.forEach(function(b){
      if(b.no!==a.no&&AFWCOL[b.no]&&overlap(a,b))used.add(AFWCOL[b.no][2]);
    });
    let i=0; while(used.has(i))i++;
    const p=PAL[i%PAL.length];
    AFWCOL[a.no]=[p[0],p[1],i];
  });
}

/* ---------- the read ------------------------------------------------------ */
function readJSON(mcp,name){
  return mcp.callTool(LIVE.server,LIVE.tool,{uri:liveUri(name)}).then(function(r){
    let p=r&&r.payload;
    if(typeof p==="string"){ try{ p=JSON.parse(p); }catch(e){ p=null; } }
    return {data:p, at:(r&&r.cache&&r.cache.storedAt)||Date.now()};
  });
}

/* Each mcp error code has a different fix; the banner names it rather than
   collapsing everything into "couldn't refresh". */
function reason(err){
  const c=err&&err.code;
  if(c==="needs_reauth")        return "Microsoft 365 needs reconnecting — claude.ai Settings → Connectors.";
  if(c==="server_not_connected")return "No Microsoft 365 connector on this account — add it in claude.ai Settings → Connectors.";
  if(c==="selection_required")  return "More than one Microsoft 365 connector; none chosen yet.";
  if(c==="not_granted"||c==="capability_disabled")
                                return "This view cannot reach connectors.";
  if(c==="blocked_by_policy"||c==="approval_required")
                                return "Org policy blocks the connector call.";
  if(c==="server_unavailable")  return "SharePoint did not answer.";
  if(c==="tool_error")          return "SharePoint refused the read: "+((err&&err.message)||"no reason given");
  return (err&&err.message)||"Refresh failed.";
}

function cacheWrite(F){
  try{ localStorage.setItem(LIVE.cacheKey,JSON.stringify({at:Date.now(),F:F})); }catch(e){}
}
function cacheRead(){
  try{
    const raw=localStorage.getItem(LIVE.cacheKey);
    if(!raw)return null;
    const o=JSON.parse(raw);
    return (o&&o.F&&o.F.tags&&o.F.tags.length)?o:null;
  }catch(e){ return null; }
}

/* The snapshot banner, kept for the case where nothing live is reachable and
   nothing is cached. It is the old staleBanner text, told against the
   pipeline's clock rather than pretending the board is current. */
function snapshotBar(extra){
  const n=daysBetween(SNAPSHOT,TODAY);
  setBar(n>2?"bad":"warn",
    "<b>Showing the built-in snapshot"+(n>0?", "+n+" day"+(n===1?"":"s")+" old":"")+".</b> "+
    "Tags, clearances and verification were read on 1 Sep 2026 and have not refreshed. "+
    "Live and window-closed states are worked out against today’s date, "+TODAY+". "+
    (extra?"<br>"+esc(extra):""));
}

async function goLive(){
  /* Render immediately from the snapshot, then upgrade. The field opens this
     on a phone; it must never sit on a blank screen waiting for SharePoint. */
  const cached=cacheRead();
  if(cached&&applyFeed(cached.F)){
    LIVE.state="cached";
    render();
    setBar("busy","Checking for newer data… showing the copy saved on this device ("+ago(new Date(cached.at).toISOString())+").");
  }else{
    snapshotBar();
  }

  const mcp=await claude.use("mcp");
  if(!mcp){
    if(LIVE.state==="cached"){
      setBar("warn","<b>Offline copy.</b> Saved on this device "+ago(new Date(cached.at).toISOString())+
        ". This page cannot reach SharePoint from here, so nothing newer could be checked.");
    }else{
      snapshotBar("No connector available in this view.");
    }
    return;
  }

  /* Stamp first: 5 KB, and on its own it already answers the only question
     that matters — when did the pipeline last run. */
  let stamp=null;
  try{ stamp=(await readJSON(mcp,LIVE.stamp)).data; }catch(e){ /* fall through */ }

  let feed=null, err=null;
  for(let i=0;i<LIVE.feeds.length&&!feed;i++){
    try{
      const got=await readJSON(mcp,LIVE.feeds[i]);
      if(got.data&&got.data.days&&Object.keys(got.data.days).length){
        feed=fromFeed(got.data);
        feed._file=LIVE.feeds[i];
        feed._at=got.at;
      }
    }catch(e){ err=e; }
  }

  if(feed&&applyFeed(feed)){
    LIVE.state="live";
    cacheWrite(feed);
    render();
    const built=feed.generated||(stamp&&stamp.last_build)||"";
    const swept=feed.swept||(stamp&&stamp.last_swept)||"";
    const behind=built?daysBetween(built.slice(0,10),TODAY):0;
    setBar(behind>=3?"warn":"live",
      "<b>"+(behind>=3?"Live read, but the pipeline is "+behind+" days behind.":"Up to date.")+"</b> "+
      "Pipeline last built "+esc(built||"unknown")+
      (swept?", mail swept to "+esc(String(swept).replace("T"," ").replace("Z"," UTC")):"")+". "+
      (stamp&&stamp.tracker_file?"Tracker "+esc(stamp.tracker_file)+" tab "+esc(stamp.tracker_tab||"?")+". ":"")+
      TAGS.length+" tags, "+AFWS.length+" outage documents."+
      (behind>=3?"<br>Nothing newer exists to read — the sweep has to be run on the Windows box before this page can show anything fresher.":""));
    return;
  }

  /* Live read failed. Say which fallback is on screen and why. */
  const why=reason(err||{});
  if(LIVE.state==="cached"){
    setBar("warn","<b>Offline copy.</b> Saved on this device "+ago(new Date(cached.at).toISOString())+
      ". "+esc(why));
  }else{
    snapshotBar(why);
  }
}
