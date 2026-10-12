/* TALON Studio - single-page app (no libraries, works offline) */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = (p, body) => fetch("/api" + p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json());
const ICON = {
  home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z", board: "M4 4h6v16H4zM14 4h6v10h-6z", check: "M20 6L9 17l-5-5",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5V22h16", flow: "M5 3h5v5H5zM14 16h5v5h-5zM10 5.5h4a3 3 0 0 1 3 3V16",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.3l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2.2-1.3L14 3h-4l-.4 2.5A7 7 0 0 0 7.4 6.8l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .9.1 1.3l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2.2 1.3L10 21h4l.4-2.5a7 7 0 0 0 2.2-1.3l2.3 1 2-3.4-2-1.5c.1-.4.1-.9.1-1.3z",
  plus: "M12 5v14M5 12h14", x: "M18 6L6 18M6 6l12 12", file: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6"
};
const ic = (n, sz = 18) => `<svg width="${sz}" height="${sz}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${ICON[n]}"/></svg>`;
const VIEWS = { home: ["Command Center", "home"], pipeline: ["Talent Pipeline", "board"], approvals: ["Approvals", "check"], workflow: ["Agent Workflow", "flow"], knowledge: ["Knowledge Base (RAG)", "book"], settings: ["Settings & AI Engine", "gear"] };
let S = { view: "home", st: null, persona: localStorage.persona || "Recruiter", feed: [], drawer: null, tab: "overview", comments: {}, chat: [], busy: false };
const SHORT = { ORIGIN: "Source", GENESIS: "Onboard", ATHENA: "Plan", LEARNING: "Learn", NOVA: "Progress", APEX: "Design", ASSESSMENT: "Test", SENTINEL: "Integrity", TITAN: "Score", PRISM: "Ready", NORTHSTAR: "Advise", OMNIVIEW: "Report" };
const COLORS = ["#0078d4", "#6b4fd8", "#0b8a7a", "#c2570c", "#b02a6b", "#3a6ea5", "#5b7c1a"];
const color = n => COLORS[[...String(n)].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORS.length];
const initials = n => String(n).split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
const av = n => `<div class="av" style="background:${color(n)}">${esc(initials(n))}</div>`;
const ago = ts => { const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000); return s < 5 ? "now" : s < 60 ? Math.floor(s) + "s" : s < 3600 ? Math.floor(s / 60) + "m" : Math.floor(s / 3600) + "h"; };
const toast = m => { const t = document.createElement("div"); t.className = "toast"; t.textContent = m; $("#toasts").appendChild(t); setTimeout(() => t.remove(), 3500); };
const md = t => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
const ring = (v, size = 46) => { const val = v == null ? 0 : Math.min(100, v), r = 19, c = 2 * Math.PI * r, col = v == null ? "#9bb" : val >= 75 ? "#1b8a3a" : val >= 55 ? "#d99a00" : "#c0392b"; return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}" viewBox="0 0 46 46"><circle cx="23" cy="23" r="${r}" fill="none" stroke="var(--border)" stroke-width="5"/><circle cx="23" cy="23" r="${r}" fill="none" stroke="${col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${c * val / 100} ${c}"/></svg><b>${v == null ? "-" : Math.round(v)}</b></div>`; };
const levelPill = l => l ? `<span class="pill ${l === "Ready" ? "ok" : l === "Not ready" ? "bad" : "warn"}">${esc(l)}</span>` : "";
function statusChip(r) {
  if (r.running) return `<span class="pill blue"><span class="spin"></span> Agents working</span>`;
  if (r.stage === "DONE") return r.hold ? `<span class="pill warn">On HOLD</span>` : `<span class="pill ok">Completed</span>`;
  if (r.stage === "REJECTED") return `<span class="pill bad">Closed</span>`;
  const w = r.waiting; if (!w) return `<span class="pill">Ready to run</span>`;
  return w.type === "approval" ? `<span class="pill warn">Needs ${esc(w.roles.join(" + "))}</span>` : `<span class="pill ai">Waiting for candidate</span>`;
}

/* ------------------------------ data + routing ------------------------------ */
async function refresh() { S.st = await api("/state"); renderNav(); renderView(); if (S.drawer) loadDrawer(false); }
let timer = null; const soon = () => { clearTimeout(timer); timer = setTimeout(refresh, 350); };
function go(v) { S.view = v; renderNav(); renderView(); }
function renderNav() {
  const k = S.st?.kpis; $("#nav").innerHTML = Object.entries(VIEWS).map(([id, [t, i]]) => `<button class="nav ${S.view === id ? "on" : ""}" onclick="go('${id}')">${ic(i)}${t.replace(" (RAG)", "")}${id === "approvals" && k?.pending ? `<span class="badge">${k.pending}</span>` : ""}</button>`).join("");
  $("#title").textContent = VIEWS[S.view][0];
  const ai = S.st?.ai; $("#sidefoot").innerHTML = ai ? `<span class="dot ${ai.available ? "on" : ""}"></span><b>${ai.available ? "AI engine on" : "Rules mode"}</b><br>${ai.available ? esc(ai.provider + " / " + ai.model) : "No AI model connected. Everything still works."}<br><span style="opacity:.7">${ai.calls} AI calls &middot; ${ai.tokens} tokens</span>` : "";
  const sel = $("#persona"); if (S.st && !sel.options.length) { sel.innerHTML = S.st.roles.map(r => `<option ${r === S.persona ? "selected" : ""}>${r}</option>`).join(""); sel.onchange = () => { S.persona = sel.value; localStorage.persona = S.persona; renderView(); }; }
}
function renderView() {
  const f = { home: vHome, pipeline: vPipeline, approvals: vApprovals, workflow: vWorkflow, knowledge: vKnowledge, settings: vSettings }[S.view];
  if (document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && ["approvals", "settings", "knowledge"].includes(S.view)) return;
  f();
}

/* ---------------------------------- HOME ------------------------------------ */
function insight(k) {
  if (!k.candidates) return "Your pipeline is empty. Load the demo portfolio or add a candidate to see the agents work.";
  const p = [`${k.completed} of ${k.candidates} journeys completed`]; if (k.pending) p.push(`${k.pending} decision${k.pending > 1 ? "s" : ""} waiting for a person`); if (k.holds) p.push(`${k.holds} on HOLD by policy`); if (k.ready) p.push(`${k.ready} ready for deployment`);
  return p.join(" · ") + ".";
}
const EVT = { agent_started: ["ai", e => `${e.agent} is analysing`], run_ok: ["ok", e => `${e.agent} finished: ${e.detail}`], approval_requested: ["bad", e => `${e.agent} stopped for ${e.detail} approval`], approval_approved: ["ok", e => `Approved by ${e.detail}`], approval_rejected: ["bad", e => `Rejected: ${e.detail}`], escalation: ["bad", e => `Supervisor added a reviewer - ${e.detail}`], demo_simulated_input: ["sys", e => `Simulated candidate input (${e.detail})`], tool_call: ["ai", e => `${e.agent} searched: ${e.detail}`], candidate_created: ["sys", e => `Candidate added`], steps_skipped: ["sys", e => e.detail], run_error: ["bad", e => `Error: ${e.detail}`], human_input: ["sys", e => `Candidate submitted ${e.agent === "NOVA" ? "learning progress" : "the assessment"}`] };
const feedItem = e => { const m = EVT[e.event]; if (!m) return ""; const who = e.candidate_name ? `<b>${esc(e.candidate_name)}</b> - ` : ""; return `<div class="ev"><span class="tag ${m[0]}">${esc(e.agent)}</span><div>${who}${esc(m[1](e)).slice(0, 170)}</div><span class="time">${ago(e.ts)}</span></div>`; };
function vHome() {
  const s = S.st, k = s.kpis, im = s.impact, empty = !k.candidates, f = k.funnel, max = Math.max(1, ...Object.values(f));
  const lv = k.levels, tot = lv["Ready"] + lv["Conditionally ready"] + lv["Not ready"];
  const a = tot ? lv["Ready"] / tot * 100 : 0, b = tot ? (lv["Ready"] + lv["Conditionally ready"]) / tot * 100 : 0;
  const top = [...s.pool].filter(r => r.readiness != null || r.match != null).sort((x, y) => (y.readiness ?? y.match) - (x.readiness ?? x.match)).slice(0, 5);
  const pend = []; // filled async below
  $("#content").innerHTML = `
  <div class="card hero"><div><h2>${new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"}. Here is your talent pipeline.</h2><p>${esc(insight(k))}</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap">${empty ? `<button class="btn w" onclick="loadDemo()">Load demo portfolio</button>` : `<button class="btn w" onclick="go('approvals')">Open approvals${k.pending ? " (" + k.pending + ")" : ""}</button>`}<button class="btn" onclick="addCandidate()">${ic("plus", 16)} Add candidate</button><button class="btn" onclick="openChat()">Ask TALON</button></div></div></div>
  <div class="grid g5" style="margin-bottom:16px">
    <div class="card kpi"><div class="l">Candidates</div><div class="n">${k.candidates}</div><div class="s">in the pipeline</div></div>
    <div class="card kpi ${k.pending ? "warn" : ""}"><div class="l">Waiting for a human</div><div class="n">${k.pending}</div><div class="s">${Object.entries(k.pending_by_role).map(([r, n]) => r + " " + n).join(" · ") || "nothing pending"}</div></div>
    <div class="card kpi ok"><div class="l">Completed journeys</div><div class="n">${k.completed}</div><div class="s">${k.ready} ready to deploy</div></div>
    <div class="card kpi"><div class="l">Average readiness</div><div class="n">${k.avg_readiness ?? "-"}</div><div class="s">out of 100</div></div>
    <div class="card kpi ${k.holds ? "bad" : ""}"><div class="l">Policy holds</div><div class="n">${k.holds}</div><div class="s">${k.approvals_done} human decisions (demo auto-approvals excluded)</div></div></div>
  <div class="grid g2" style="margin-bottom:16px">
    <div class="card"><h3>Business impact<small>measured in this session</small></h3>
      <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
        <div class="fact" style="display:block"><span>Manual effort avoided (estimate)</span><div style="font-size:24px;font-weight:700">${im.hours_saved} h</div></div>
        <div class="fact" style="display:block"><span>Time to analyse a resume</span><div style="font-size:24px;font-weight:700">${im.shortlist_seconds ?? "-"} s</div></div>
        <div class="fact" style="display:block"><span>Documents and summaries written by agents</span><div style="font-size:24px;font-weight:700">${im.agent_outputs}</div></div>
        <div class="fact" style="display:block"><span>Human decisions logged with evidence</span><div style="font-size:24px;font-weight:700">${im.decisions}</div></div></div>
      <div style="color:var(--muted);font-size:11.5px;margin-top:8px">Effort estimate = agent outputs x typical manual minutes (resume screening ${im.assumptions.ORIGIN}, learning plan ${im.assumptions.ATHENA}, assessment design ${im.assumptions.APEX}, scoring review ${im.assumptions.TITAN}, report ${im.assumptions.OMNIVIEW}). These are assumptions, not measurements.</div></div>
    <div class="card"><h3>Gen AI at work<small>${s.ai.available ? esc(s.ai.provider + " / " + s.ai.model) : "AI model not connected"}</small></h3>
      ${s.ai.available ? "" : `<div class="callout warn" style="padding:8px 12px">Rules mode: the Gen AI features below are off. <button class="btn sm p" style="margin-left:auto" onclick="go('settings')">Connect a model</button></div>`}
      <div class="row"><span class="k" style="width:190px">AI-written agent outputs</span><div class="bar"><i style="width:${im.agent_outputs ? im.ai_written / im.agent_outputs * 100 : 0}%"></i></div><span class="v" style="width:60px">${im.ai_written}/${im.agent_outputs}</span></div>
      <div class="row"><span class="k" style="width:190px">Agent tool calls (reasoning)</span><span class="v" style="margin-left:auto">${im.tool_calls}</span></div>
      <div class="row"><span class="k" style="width:190px">Supervisor escalations to a human</span><span class="v" style="margin-left:auto">${im.escalations}</span></div>
      <div class="row"><span class="k" style="width:190px">Questions answered by Ask TALON</span><span class="v" style="margin-left:auto">${im.chats}</span></div>
      <div class="row"><span class="k" style="width:190px">AI calls / tokens</span><span class="v" style="margin-left:auto;width:auto">${s.ai.calls} / ${s.ai.tokens}</span></div></div></div>
  <div class="grid g3" style="margin-bottom:16px">
    <div class="card"><h3>Pipeline by stage<small>${k.candidates} candidates</small></h3>${Object.entries(f).map(([p, n]) => `<div class="row"><span class="k">${p}</span><div class="bar"><i style="width:${n / max * 100}%"></i></div><span class="v">${n}</span></div>`).join("")}</div>
    <div class="card"><h3>Readiness mix</h3><div style="display:flex;gap:18px;align-items:center"><div class="donut" style="background:${tot ? `conic-gradient(#1b8a3a 0 ${a}%,#d99a00 ${a}% ${b}%,#c0392b ${b}% 100%)` : "var(--border)"}"><div><span><b>${tot}</b>assessed</span></div></div><div style="font-size:13px;line-height:2"><span class="pill ok">Ready ${lv["Ready"]}</span><br><span class="pill warn">Conditionally ready ${lv["Conditionally ready"]}</span><br><span class="pill bad">Not ready ${lv["Not ready"]}</span></div></div></div></div>
  <div class="grid g2"><div class="card"><h3>Top candidates<small>by readiness</small></h3><div class="list">${top.length ? top.map(r => `<div class="it" style="cursor:pointer" onclick="openCand(${r.id})">${av(r.name)}<div><div class="t">${esc(r.name)}</div><div class="m">${esc(r.job)} · ${statusChip(r)}</div></div><div class="r">${ring(r.readiness ?? r.match, 42)}</div></div>`).join("") : `<div class="empty">No scored candidates yet</div>`}</div></div>
    <div class="card"><h3>Live agent activity<small>updates as it happens</small></h3><div class="feed" id="feed">${S.feed.slice(0, 30).map(feedItem).join("") || `<div class="empty">Agent activity will appear here</div>`}</div></div></div>`;
}
async function loadDemo() { toast("Loading demo portfolio - agents are working..."); const r = await api("/samples", {}); if (r.error) toast(r.error); }

/* -------------------------------- PIPELINE ---------------------------------- */
function vPipeline() {
  const s = S.st; $("#content").innerHTML = `<div style="display:flex;margin-bottom:14px;gap:8px"><button class="btn p" onclick="addCandidate()">${ic("plus", 16)} Add candidate</button><span style="margin-left:auto;color:var(--muted);align-self:center">Click a card to see what every agent did and why</span></div>
  ${s.pool.length ? `<div class="kan">${s.phases.map(p => { const c = s.pool.filter(r => r.phase === p); return `<div class="col"><h4>${p}<span>${c.length}</span></h4>${c.map(r => `<div class="cc" onclick="openCand(${r.id})"><div class="h">${av(r.name)}<div><div class="n">${esc(r.name)}</div><div class="j">${esc(r.job)} · ${esc(r.stage)}</div></div>${ring(r.readiness ?? r.match)}</div><div class="f">${statusChip(r)}${levelPill(r.level)}${r.flags ? `<span class="pill bad">${r.flags} flag</span>` : ""}</div></div>`).join("")}</div>`; }).join("")}</div>` : `<div class="card empty">No candidates yet.<br><br><button class="btn p" onclick="loadDemo()">Load demo portfolio</button></div>`}`;
}

/* ------------------------------- CANDIDATE ---------------------------------- */
async function openCand(id) { S.drawer = id; S.tab = "overview"; $("#veil").classList.add("on"); $("#drawer").classList.add("on"); $("#drawer").innerHTML = `<div class="empty">Loading...</div>`; loadDrawer(true); }
function closeDrawer() { S.drawer = null; $("#veil").classList.remove("on"); $("#drawer").classList.remove("on"); }
async function loadDrawer() { if (!S.drawer) return; S.cv = await api("/candidates/" + S.drawer); drawDrawer(); }
function setTab(t) { S.tab = t; drawDrawer(); }
function drawDrawer() {
  const v = S.cv; if (!v || v.error) return; const r = v.readiness || {}, w = v.status.waiting;
  const tabs = [["overview", "Overview"], ["agents", "Agent activity"], ["learn", "Learning & assessment"], ["docs", "Documents"], ["audit", "Audit"]];
  $("#drawer").innerHTML = `<div class="dh"><div class="t">${av(v.name)}<div style="flex:1"><h2>${esc(v.name)}</h2><div style="color:var(--muted)">${esc(v.job.title)} · ${esc(v.email)}</div></div>${ring(r.score ?? v.match, 54)}<button class="btn sm" onclick="closeDrawer()">${ic("x", 16)}</button></div>
    <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">${statusChip({ running: v.status.running, stage: v.stage, waiting: w, hold: (v.recommendation?.hiring || "").startsWith("HOLD") })}${levelPill(r.level)}<span class="pill">${esc(v.stage)}</span></div>
    <div class="steps">${v.steps.map(x => `<div class="stp ${x.state}" title="${esc(x.title)} - ${x.state}"><i></i>${SHORT[x.id]}</div>`).join("")}</div>
    <div class="tabs">${tabs.map(([i, t]) => `<button class="tab ${S.tab === i ? "on" : ""}" onclick="setTab('${i}')">${t}</button>`).join("")}</div></div>
    <div class="dbody">${{ overview: tOverview, agents: tAgents, learn: tLearn, docs: tDocs, audit: tAudit }[S.tab](v)}</div>`;
}
function waitBanner(v) {
  const w = v.status.waiting; if (v.stage === "DONE") return v.recommendation?.hiring?.startsWith("HOLD") ? `<div class="callout warn"><b>HOLD</b> ${esc(v.recommendation.hiring)}</div>` : `<div class="callout ok"><b>Journey complete.</b> ${esc(v.decision?.decision || "")}</div>`;
  if (v.stage === "REJECTED") return `<div class="callout bad">This journey was closed by a human reviewer.</div>`;
  if (v.status.running) return `<div class="callout blue"><span class="spin"></span> Agents are working on this candidate right now...</div>`;
  if (w?.type === "approval") return `<div class="callout warn"><b>STOP</b> ${esc(w.agent)} is waiting for <b>${esc(w.roles.join(" + "))}</b>.<button class="btn sm ok" style="margin-left:auto" onclick="go('approvals');closeDrawer()">Review</button></div>`;
  if (w?.type === "candidate") return `<div class="callout blue">Waiting for the candidate to complete: <b>${w.step === "LEARNING" ? "learning progress" : "the assessment"}</b>.<span style="margin-left:auto;display:flex;gap:6px"><button class="btn sm p" onclick="${w.step === "LEARNING" ? "learningModal()" : "assessModal()"}">Open as candidate</button><button class="btn sm" onclick="simulate()">Simulate</button></span></div>`;
  return `<div class="callout blue">Ready for the next step. <button class="btn sm p" style="margin-left:auto" onclick="runCase()">Run agents</button></div>`;
}
function tOverview(v) {
  const rec = v.recommendation, sk = v.skills, comp = v.competency || {};
  return `${waitBanner(v)}
  ${v.report ? `<div class="card" style="margin-bottom:14px"><h3>Executive summary <span class="pill ai">OMNIVIEW</span></h3>${esc(v.report.summary)}</div>` : ""}
  ${rec ? `<div class="card" style="margin-bottom:14px"><h3>Recommendation <span class="pill ai">NORTHSTAR</span><small>a human makes the final decision</small></h3><p style="margin:0 0 6px"><b>${esc(rec.hiring)}</b></p><div style="color:var(--muted)">${esc(rec.deployment)} · ${esc(rec.upskilling)}</div>${(rec.policy_evidence || []).map(p => `<div class="obs" style="margin-top:8px"><b>Policy evidence - ${esc(p.doc)}</b><br>${esc(p.text)}...</div>`).join("")}</div>` : ""}
  <div class="card" style="margin-bottom:14px"><h3>Skills vs job<small>match ${v.match ?? "-"}${v.rank ? " · rank " + v.rank + " of " + v.of : ""}</small></h3>
    <div class="chips">${sk.matched_required.map(s => `<span class="pill ok">${esc(s)}</span>`).join("")}${sk.inferred.map(s => `<span class="pill warn" title="Inferred by AI, half credit">${esc(s)} (AI)</span>`).join("")}${sk.missing.map(s => `<span class="pill bad">${esc(s)}</span>`).join("")}${sk.matched_nice.map(s => `<span class="pill blue">${esc(s)}</span>`).join("")}</div>
    <div style="color:var(--muted);font-size:12px;margin-top:8px">Green = matched, amber = inferred by AI (half credit), red = missing, blue = nice-to-have matched.</div></div>
  ${Object.keys(comp).length ? `<div class="card"><h3>Competency map <span class="pill ai">PRISM</span></h3>${Object.entries(comp).map(([k, x]) => `<div class="row"><span class="k" style="width:150px">${esc(k)}</span><div class="bar"><i style="width:${x}%"></i></div><span class="v" style="width:36px">${x}%</span></div>`).join("")}</div>` : ""}`;
}
function tAgents(v) {
  return waitBanner(v) + v.agents.map(a => {
    const st = { done: ["ok", "Done"], waiting: ["warn", "Waiting for human"], running: ["blue", "Working"], current: ["blue", "Next"], pending: ["", "Not started"], skipped: ["", "Skipped"] }[a.state];
    return `<div class="agent ${a.state === "pending" || a.state === "skipped" ? "pending" : ""}"><div class="ah"><div class="ic">${esc(a.id.slice(0, 2))}</div><div style="flex:1"><b>${esc(a.id)}</b> <span style="color:var(--muted)">${esc(a.title)}</span><div class="goal">Goal: ${esc(a.goal)}</div></div>${a.used_llm ? `<span class="pill ai">AI-written</span>` : ""}<span class="pill ${st[0]}">${st[1]}</span></div>
    ${a.summary ? `<div class="ab"><p>${esc(a.summary)}</p>
      ${a.trace.length ? `<details class="tr"><summary>Reasoning trace · ${a.trace.filter(t => t.action).length} tool call(s)${a.sources.length ? " · " + a.sources.length + " source(s)" : ""}</summary>${a.trace.map(t => t.action ? `<div class="call">${esc(t.thought || "")}\n&rarr; ${esc(t.action)}(${esc(JSON.stringify(t.args))})</div><div class="obs">${esc(t.observation)}</div>` : t.guardrail ? `<div class="callout bad" style="padding:6px 10px;margin:6px 0"><b>Guardrail</b> ${esc(t.guardrail)}</div>` : t.final ? `<div class="call">final answer: ${esc(JSON.stringify(t.final)).slice(0, 400)}</div>` : `<div class="obs">${esc(t.error || "")}</div>`).join("")}${a.sources.length ? `<div class="chips" style="margin-top:6px">${a.sources.map(s => `<span class="pill blue">${esc(s.source)}: ${esc(s.title)}</span>`).join("")}</div>` : ""}</details>` : ""}
      ${a.approvals.map(p => `<div style="margin-top:8px;font-size:12.5px"><span class="pill ${p.status === "approved" ? "ok" : p.status === "rejected" ? "bad" : "warn"}">${esc(p.role)}: ${esc(p.status)}</span> ${p.decided_by ? "by " + esc(p.decided_by) : ""} ${p.comment ? "- “" + esc(p.comment) + "”" : ""}</div>`).join("")}</div>` : ""}</div>`;
  }).join("");
}
function tLearn(v) {
  const sc = v.scores, ig = v.integrity;
  return `${waitBanner(v)}
  <div class="card" style="margin-bottom:14px"><h3>Learning plan <span class="pill ai">ATHENA</span><small>${v.plan.reduce((a, p) => a + p.hours, 0)} hours</small></h3>${v.plan.length ? `<table><tr><th>Skill</th><th>Course (retrieved from knowledge base)</th><th>Hours</th></tr>${v.plan.map(p => `<tr><td>${esc(p.skill)}</td><td>${esc(p.course)}<div style="font-size:11px;color:var(--muted)">source: ${esc(p.source || "")}</div></td><td>${p.hours}</td></tr>`).join("")}</table>` : `<div class="empty">${v.agents.find(a => a.id === "ATHENA").summary ? "No skill gaps - no plan needed" : "Not created yet"}</div>`}
    ${v.learning ? `<div class="row"><span class="k">Completion</span><div class="bar"><i style="width:${v.learning.completion_pct}%"></i></div><span class="v" style="width:44px">${v.learning.completion_pct}%</span></div>` : ""}</div>
  <div class="card"><h3>Assessment <span class="pill ai">TITAN</span></h3>${sc ? `<div class="row"><span class="k">Overall</span><div class="bar"><i style="width:${sc.total}%"></i></div><span class="v" style="width:44px">${sc.total}</span></div>${Object.entries(sc.per_skill).map(([k, x]) => `<div class="row"><span class="k">${esc(k)}</span><div class="bar"><i style="width:${x}%"></i></div><span class="v" style="width:44px">${x}%</span></div>`).join("")}${sc.coding ? `<div style="margin-top:6px;color:var(--muted)">Coding: ${sc.coding.passed}/${sc.coding.total} tests passed</div>` : ""}
    <div style="margin-top:10px">${ig && ig.violations.length ? ig.violations.map(x => `<span class="pill bad">${esc(x)}</span>`).join(" ") : `<span class="pill ok">No integrity flags</span>`}</div>` : `<div class="empty">Not assessed yet</div>`}</div>`;
}
function tDocs(v) {
  return `<div class="card"><h3>Generate documents</h3><div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn p" target="_blank" href="/api/candidates/${v.id}/dossier">${ic("file", 16)} Open candidate dossier</a><button class="btn" onclick="draft('feedback')">Feedback email</button><button class="btn" onclick="draft('invite')">Interview invite</button><button class="btn" onclick="draft('brief')">Hiring manager brief</button><button class="btn" onclick="guide()">Interview guide</button></div>
  <div style="color:var(--muted);font-size:12px;margin:8px 0">The dossier opens as a printable page - use Print &gt; Save as PDF.</div><textarea id="docout" rows="12" placeholder="Generated text appears here..."></textarea><div class="acts"><button class="btn sm" onclick="navigator.clipboard.writeText($('#docout').value);toast('Copied')">Copy</button></div></div>`;
}
const tAudit = v => `<div class="card"><h3>Audit trail<small>who did what, when</small></h3><table><tr><th>Time</th><th>Actor</th><th>Event</th><th>Detail</th></tr>${v.audit.map(a => `<tr><td style="white-space:nowrap">${esc(a.ts.slice(11))}</td><td>${esc(a.agent)}</td><td>${esc(a.event)}</td><td>${esc(a.detail)}</td></tr>`).join("")}</table></div>`;
async function runCase() { await api(`/candidates/${S.drawer}/run`, {}); soon(); }
async function simulate() { await api(`/candidates/${S.drawer}/simulate`, {}); toast("Simulated candidate input - agents continue"); soon(); }
async function draft(kind) { $("#docout").value = "Writing..."; $("#docout").value = (await api(`/candidates/${S.drawer}/draft?kind=${kind}`)).text; }
async function guide() { $("#docout").value = (await api(`/candidates/${S.drawer}/interview-guide`)).questions.map((q, i) => `${i + 1}. ${q}`).join("\n"); }

/* --------------------------------- MODALS ----------------------------------- */
const modal = html => { $("#modal").innerHTML = `<div class="modal" onclick="if(event.target===this)closeModal()"><div>${html}</div></div>`; };
const closeModal = () => $("#modal").innerHTML = "";
async function addCandidate() {
  const jobs = S.st.jobs; if (!jobs.length) { toast("Add a job first (Settings > Load demo portfolio)."); return; }
  modal(`<h3>Add a candidate</h3><div style="color:var(--muted)">Upload a resume (PDF or TXT) or paste the text. Use sample or synthetic data only.</div>
  <label>Job</label><select id="ac_job">${jobs.map(j => `<option value="${j.id}">${esc(j.title)}</option>`).join("")}</select>
  <label>Resume file</label><input type="file" id="ac_file" accept=".pdf,.txt"><label>...or paste resume text</label><textarea id="ac_text" rows="7"></textarea>
  <label style="display:flex;gap:8px;align-items:center;font-weight:500"><input type="checkbox" id="ac_auto" style="width:auto"> Autopilot (demo): auto-approve every step</label>
  <div class="acts"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn p" onclick="submitCand()">Add and start agents</button></div>`);
}
async function submitCand() {
  const f = $("#ac_file").files[0], body = { job_id: +$("#ac_job").value, resume_text: $("#ac_text").value, autopilot: $("#ac_auto").checked };
  if (f) { body.filename = f.name; body.data = await new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.readAsDataURL(f); }); }
  const r = await api("/candidates", body); if (r.error) return toast(r.error);
  closeModal(); toast("Candidate added - agents started"); go("pipeline"); soon();
}
async function learningModal() {
  const v = S.cv; modal(`<h3>Candidate: log learning progress</h3><div style="color:var(--muted)">Move each slider to the % completed.</div>${v.plan.map((p, i) => `<label>${esc(p.course)} <span id="lv${i}">0</span>%</label><input type="range" min="0" max="100" value="0" oninput="$('#lv${i}').textContent=this.value" class="lp" data-c="${esc(p.course)}">`).join("")}<div class="acts"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn p" onclick="submitLearning()">Submit</button></div>`);
}
async function submitLearning() { const progress = {}; document.querySelectorAll(".lp").forEach(i => progress[i.dataset.c] = +i.value); await api(`/candidates/${S.drawer}/learning`, { progress }); closeModal(); toast("Submitted - agents continue"); soon(); }
let assessStart = 0;
async function assessModal() {
  const a = await api(`/candidates/${S.drawer}/assessment`); assessStart = Date.now();
  modal(`<h3>Candidate: take the assessment</h3>${a.questions.map((q, i) => `<div class="q"><label>${i + 1}. ${esc(q.q)}</label>${q.options.map((o, j) => `<div class="o"><input type="radio" name="q_${esc(q.id)}" value="${j}" style="width:auto"> ${esc(o)}</div>`).join("")}</div>`).join("")}
  ${a.coding ? `<div class="q"><label>Coding task: ${esc(a.coding.prompt)}</label><textarea id="as_code" rows="8" style="font-family:ui-monospace,Consolas,monospace">${esc(a.coding.starter)}</textarea></div>` : ""}
  <label style="display:flex;gap:8px;align-items:center;font-weight:500"><input type="checkbox" id="as_help" style="width:auto"> I used outside help (honesty declaration)</label>
  <div class="acts"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn p" onclick="submitAssess(${JSON.stringify(a.questions.map(q => q.id))})">Submit assessment</button></div>`);
}
async function submitAssess(ids) {
  const answers = {}; ids.forEach(id => { const el = document.querySelector(`input[name="q_${id}"]:checked`); answers[id] = el ? +el.value : -1; });
  await api(`/candidates/${S.drawer}/assessment`, { answers, code: $("#as_code")?.value || "", seconds: (Date.now() - assessStart) / 1000, declared: $("#as_help").checked });
  closeModal(); toast("Submitted - agents continue"); soon();
}

/* -------------------------------- APPROVALS --------------------------------- */
const FACTS = {
  ORIGIN: d => [["Match score", d.score], ["Rank", d.rank + " of " + d.of], ["Matched", (d.matched_required || []).join(", ") || "none"], ["Missing", (d.missing_required || []).join(", ") || "none"], ["AI-inferred", (d.inferred_by_ai_half_credit || []).join(", ") || "none"]],
  GENESIS: d => [["Status", d.status], ["Issues", (d.issues || []).join("; ") || "none"]],
  ATHENA: d => [["Courses", (d.plan || []).length], ["Total hours", d.total_hours], ["Gaps", (d.gaps_required || []).join(", ") || "none"]],
  NOVA: d => [["Completion", d.completion_pct + "%"], ["Engagement", d.engagement], ["At risk", d.at_risk ? "yes" : "no"]],
  APEX: d => [["Questions", d.n_questions], ["Coding task", d.coding ? "yes" : "no"], ["Competencies", (d.competencies || []).join(", ")]],
  SENTINEL: d => [["Avg seconds / question", d.avg_seconds], ["Flags", (d.violations || []).join("; ") || "none"]],
  TITAN: d => [["Overall", d.total], ["Objective", d.objective + "%"], ["Coding", d.coding ? d.coding.passed + "/" + d.coding.total + " tests" : "n/a"]],
  PRISM: d => [["Readiness", d.readiness], ["Level", d.level], ["Strengths", (d.strengths || []).join(", ") || "none"], ["To improve", (d.weak || []).join(", ") || "none"]],
  NORTHSTAR: d => [["Hiring", d.hiring], ["Deployment", d.deployment], ["Upskilling", d.upskilling]],
  OMNIVIEW: d => [["Readiness", (d.readiness || {}).score], ["Recommendation", (d.recommendation || {}).hiring]]
};
const facts = a => { try { return (FACTS[a.agent] ? FACTS[a.agent](a.data || {}) : []).map(([k, v]) => `<span class="fact"><span>${esc(k)}</span><b>${esc(v)}</b></span>`).join(""); } catch (e) { return ""; } };
async function vApprovals() {
  const all = await api("/approvals"), roles = S.st.roles, by = {}; all.forEach(a => by[a.role] = (by[a.role] || 0) + 1);
  const mine = all.filter(a => a.role === S.persona);
  $("#content").innerHTML = `<div class="card" style="margin-bottom:16px"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><b>Acting as</b>${roles.map(r => `<button class="btn sm ${r === S.persona ? "p" : ""}" onclick="S.persona='${r}';localStorage.persona='${r}';$('#persona').value='${r}';vApprovals()">${r}${by[r] ? ` <span class="pill warn">${by[r]}</span>` : ""}</button>`).join("")}</div></div>
  ${mine.length ? mine.map(a => `<div class="card" style="margin-bottom:14px"><div style="display:flex;gap:12px;align-items:center">${av(a.candidate_name)}<div style="flex:1"><b>${esc(a.candidate_name)}</b> <span style="color:var(--muted)">· ${esc(a.agent)} ${esc(a.agent_title)}</span><div>${a.escalation ? `<span class="pill ai">Supervisor escalation</span>` : `<span class="pill warn">STOP: needs ${esc(a.role)}</span>`}</div></div><button class="btn sm" onclick="openCand(${a.candidate_id})">View case</button></div>
    <p style="margin:12px 0">${esc(a.summary)}</p><div class="facts">${facts(a)}</div>
    <input type="text" placeholder="Comment (optional, saved in the audit trail)" value="${esc(S.comments[a.id] || "")}" oninput="S.comments[${a.id}]=this.value" id="cm${a.id}"><div class="acts"><button class="btn bad" onclick="decide(${a.id},false)">Reject</button><button class="btn ok" onclick="decide(${a.id},true)">Approve and continue</button></div></div>`).join("") : `<div class="card empty">Nothing is waiting for <b>${esc(S.persona)}</b>.${all.length ? `<br>${all.length} item(s) are waiting for other roles - switch role above.` : ""}</div>`}`;
}
async function decide(id, approve) { await api(`/approvals/${id}/decide`, { approve, comment: S.comments[id] || "", by: S.persona }); delete S.comments[id]; toast(approve ? "Approved. Agents are continuing..." : "Rejected. Journey closed."); await refresh(); }

/* --------------------------------- WORKFLOW --------------------------------- */
async function vWorkflow() {
  const g = await api("/graph");
  $("#content").innerHTML = `<div class="sup"><div class="mark" style="background:linear-gradient(135deg,#6b4fd8,#0078d4)">${ic("flow", 20)}</div><div><b>Supervisor</b><div style="color:var(--muted)">Routes every candidate to the next agent and can add an extra human reviewer when a result looks borderline or weakly evidenced. It can only make the process stricter, never skip an approval.</div></div></div>
  <div class="wf">${g.nodes.map((n, i) => `<div class="node ${n.type === "human" ? "human" : ""} ${n.count ? "hot" : ""}"><span class="c ${n.count ? "" : "z"}">${n.count}</span><small>Step ${i + 1}</small><b>${esc(n.id)}</b><div style="color:var(--muted);font-size:12.5px">${esc(n.title)}</div><div style="font-size:12px;margin-top:6px">${esc(n.goal)}</div>${n.type === "agent" ? `<div class="gate"><span class="pill warn">STOP gate</span></div>` : `<div class="gate"><span class="pill ai">Candidate acts</span></div>`}</div>`).join("")}</div>
  <div class="card" style="margin-top:16px"><b>${g.done}</b> journeys completed. The number on each card is how many candidates are at that step right now. Dashed cards are steps where the candidate acts.</div>`;
}

/* -------------------------------- KNOWLEDGE --------------------------------- */
async function vKnowledge() {
  const kb = await api("/kb"); $("#content").innerHTML = `<div class="card" style="margin-bottom:16px"><h3>What the agents can look up (RAG)<small>embedder: ${esc(kb.embedder)}</small></h3><div class="chips">${Object.entries(kb.by_source).map(([k, n]) => `<span class="pill blue">${esc(k)}: ${n} chunks</span>`).join("")}</div><div style="margin:10px 0;color:var(--muted)">Files in the knowledge folder: ${kb.files.map(f => `<span class="pill">${esc(f)}</span>`).join(" ")}</div><div style="display:flex;gap:8px"><button class="btn" onclick="kbUpload()">Upload a document (.txt / .md)</button><button class="btn" onclick="kbReindex()">Re-index</button></div></div>
  <div class="card"><h3>Try a search</h3><div style="display:flex;gap:8px"><input id="kq" placeholder="e.g. what happens when an integrity flag is raised?" onkeydown="if(event.key==='Enter')kbSearch()"><select id="ks" style="width:150px"><option>all</option><option>docs</option><option>skills</option><option>catalog</option><option>jobs</option><option>resume</option></select><button class="btn p" onclick="kbSearch()">Search</button></div><div id="kres" style="margin-top:12px"></div></div>`;
}
async function kbSearch() { const q = $("#kq").value, res = await api("/kb/search", { q, source: $("#ks").value }); const words = q.toLowerCase().split(/\W+/).filter(w => w.length > 3);
  $("#kres").innerHTML = res.map(h => { let t = esc(h.text); words.forEach(w => t = t.replace(new RegExp("(" + w + ")", "gi"), '<span class="hl">$1</span>')); return `<div class="card" style="margin-bottom:10px;background:var(--surface2)"><div style="display:flex;gap:8px;margin-bottom:6px"><span class="pill blue">${esc(h.source)}</span><b>${esc(h.title)}</b><span style="margin-left:auto;color:var(--muted)">similarity ${h.score}</span></div>${t}</div>`; }).join("") || `<div class="empty">No results</div>`; }
async function kbReindex() { toast("Re-indexing..."); await api("/kb/reindex", {}); vKnowledge(); }
function kbUpload() { const i = document.createElement("input"); i.type = "file"; i.accept = ".txt,.md"; i.onchange = async () => { const f = i.files[0]; const data = await new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.readAsDataURL(f); }); await api("/kb/upload", { filename: f.name, data }); toast("Document indexed"); vKnowledge(); }; i.click(); }

/* -------------------------------- SETTINGS ---------------------------------- */
async function vSettings() {
  const { settings: st, ai } = await api("/settings"), p = st.provider;
  const E = [["none", "Rules mode", "No AI model. Everything works with rules, retrieval and templates."], ["ollama", "Ollama (local)", "Free, private, runs on your laptop."], ["github", "GitHub Models", "Free tier with your GitHub token (Copilot account)."], ["openai", "OpenAI-compatible API", "Groq, OpenRouter, Together, Azure OpenAI..."]];
  $("#content").innerHTML = `<div class="card" style="margin-bottom:16px"><h3>AI engine<small>${ai.available ? "connected: " + esc(ai.provider + " / " + ai.model) : "not connected"}</small></h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">${E.map(([id, t, d]) => `<div class="eng ${p === id ? "on" : ""}" onclick="pickEngine('${id}')"><b>${t}</b><small>${d}</small></div>`).join("")}</div>
  <div id="fields">${p === "ollama" ? `<label>Ollama URL</label><input id="s_ollama_url" value="${esc(st.ollama_url)}"><label>Chat model (ollama pull ${esc(st.ollama_model)})</label><input id="s_ollama_model" value="${esc(st.ollama_model)}"><label>Embedding model (ollama pull ${esc(st.embed_model)})</label><input id="s_embed_model" value="${esc(st.embed_model)}">` : ""}
  ${p === "github" ? `<div class="callout blue" style="margin-top:12px">Create a <b>fine-grained personal access token</b> in GitHub with the <b>Models: Read</b> permission. A Copilot subscription alone is not an API key. The free tier is rate-limited, so the demo uses few AI calls.</div><label>GitHub token</label><input type="password" id="s_github_token" placeholder="${st.github_token ? "saved (hidden)" : "github_pat_..."}"><label>Model</label><div style="display:flex;gap:8px"><input id="s_github_model" value="${esc(st.github_model)}" list="gm"><datalist id="gm"></datalist><button class="btn" onclick="listModels()">List models</button></div>` : ""}
  ${p === "openai" ? `<label>Base URL</label><input id="s_openai_base" value="${esc(st.openai_base)}"><label>API key</label><input type="password" id="s_openai_key" placeholder="${st.openai_key ? "saved (hidden)" : "paste key"}"><label>Model</label><input id="s_openai_model" value="${esc(st.openai_model)}">` : ""}</div>
  <label>Demo pace: seconds of visible "thinking" per agent in Rules mode</label><input id="s_demo_pace" value="${st.demo_pace}" style="width:120px">
  <div class="acts"><span id="testres" style="margin-right:auto;align-self:center;color:var(--muted)">${esc(ai.last_error)}</span><button class="btn" onclick="testAI()">Test connection</button><button class="btn p" onclick="saveSettings()">Save</button></div></div>
  <div class="card"><h3>Data</h3><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" onclick="loadDemo()">Load demo portfolio</button><button class="btn bad" onclick="resetAll()">Reset all data</button></div><p style="color:var(--muted)">Everything is stored in the data folder on this computer. Use sample or synthetic data only.</p></div>`;
  S.pickedEngine = p;
}
function pickEngine(id) { S.pickedEngine = id; api("/settings", { provider: id }).then(vSettings); }
async function saveSettings() { const b = { provider: S.pickedEngine }; document.querySelectorAll("[id^=s_]").forEach(i => { const k = i.id.slice(2); b[k] = k === "demo_pace" ? parseFloat(i.value) || 0.8 : i.value; }); await api("/settings", b); toast("Saved"); refresh(); vSettings(); }
async function testAI() { await saveSettings(); $("#testres")?.replaceChildren("Testing..."); const r = await api("/settings/test", {}); toast(r.message); vSettings().then(() => { const e = $("#testres"); if (e) e.textContent = r.message; }); }
async function listModels() { const r = await api("/settings/github-models"); $("#gm").innerHTML = r.models.map(m => `<option>${esc(m)}</option>`).join(""); toast(r.models.length ? r.models.length + " models found" : (r.error || "No models returned - check the token")); }
async function resetAll() { if (!confirm("Delete ALL candidates and data?")) return; await api("/reset", {}); S.feed = []; toast("Reset"); refresh(); }

/* --------------------------------- CHAT ------------------------------------- */
const SUG = ["Who is ready for hire?", "What is waiting for approval?", "Which candidates have risks or holds?", "Summarize Aisha", "Compare Priya and Sofia", "What does our policy say about integrity flags?"];
function openChat() { $("#chat").classList.add("on"); $("#veil").classList.add("on"); if (!S.chat.length) S.chat.push({ r: "a", t: "Hi, I am TALON. I answer from the live talent data and your policy documents, and I show which tools I used.", s: [] }); drawChat(); $("#chatin").focus(); }
function closeChat() { $("#chat").classList.remove("on"); if (!S.drawer) $("#veil").classList.remove("on"); }
function drawChat() { $("#msgs").innerHTML = S.chat.map(m => `<div class="m ${m.r}">${m.r === "a" ? md(m.t) : esc(m.t)}${m.s?.length ? `<small>Tools: ${esc(m.s.join(", "))} · ${m.llm ? "answered by AI model" : "answered by built-in rules"}</small>` : ""}</div>`).join("") + (S.busy ? `<div class="m a"><span class="spin"></span> thinking...</div>` : ""); $("#msgs").scrollTop = 1e9; $("#sug").innerHTML = S.chat.length < 3 ? SUG.map(s => `<button onclick="ask('${s}')">${s}</button>`).join("") : ""; $("#chatmode").textContent = S.st?.ai?.available ? "AI model + data tools" : "Built-in rules + data tools"; }
async function ask(q) { q = (q || $("#chatin").value).trim(); if (!q) return; $("#chatin").value = ""; S.chat.push({ r: "u", t: q }); S.busy = true; drawChat(); const r = await api("/chat", { message: q }); S.busy = false; S.chat.push({ r: "a", t: r.answer, s: r.steps, llm: r.used_llm }); drawChat(); }

/* --------------------------------- boot ------------------------------------- */
$("#veil").onclick = () => { closeDrawer(); closeChat(); };
$("#askbtn").onclick = openChat; $("#chatx").onclick = closeChat; $("#chatgo").onclick = () => ask(); $("#chatin").onkeydown = e => { if (e.key === "Enter") ask(); };
$("#theme").onclick = () => { const d = document.documentElement.dataset.theme === "dark"; document.documentElement.dataset.theme = d ? "" : "dark"; localStorage.theme = d ? "" : "dark"; };
if (localStorage.theme) document.documentElement.dataset.theme = localStorage.theme;
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeDrawer(); closeChat(); closeModal(); } if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openChat(); } });
(async function () {
  await refresh(); const es = new EventSource("/api/events");
  es.onmessage = m => { const e = JSON.parse(m.data); S.feed.unshift(e); S.feed = S.feed.slice(0, 80); const f = $("#feed"); if (f && S.view === "home") f.innerHTML = S.feed.slice(0, 30).map(feedItem).join(""); soon(); };
  api("/activity?since=0").then(rows => { S.feed = rows.reverse(); if (S.view === "home") renderView(); });
})();
