"""Read-only views of the data, shaped for the web interface."""
import json
import re
from datetime import datetime

from . import db, observability, orchestrator as orch, workflow
from .agents import AGENTS

ALL_PHASES = ["Sourcing", "Onboarding", "Learning", "Assessment", "Evaluation", "Decision", "Completed"]
PHASE_OF = {"ORIGIN": "Sourcing", "GENESIS": "Onboarding", "ATHENA": "Learning",
            "LEARNING": "Learning", "NOVA": "Learning", "APEX": "Assessment",
            "ASSESSMENT": "Assessment", "SENTINEL": "Assessment", "TITAN": "Assessment",
            "PRISM": "Evaluation", "NORTHSTAR": "Evaluation", "OMNIVIEW": "Decision",
            "DONE": "Completed", "REJECTED": "Completed"}
STEP_TITLE = {"LEARNING": "Candidate logs learning progress",
              "ASSESSMENT": "Candidate takes the assessment"}


def phases() -> list:
    used = {PHASE_OF[i] for i, _ in orch.PIPELINE}
    return [p for p in ALL_PHASES if p in used or p == "Completed"]


def _ready(cid: int) -> dict:
    """Readiness from PRISM (full mode) or derived by NORTHSTAR (lite mode)."""
    return db.memory_get(cid, "PRISM", "readiness") or db.memory_get(cid, "NORTHSTAR", "readiness") or {}


def _job(job_id):
    try:
        return orch.get_job(job_id)
    except Exception:
        return {"id": job_id, "title": "-", "required": [], "nice": []}


def candidate_row(c: dict) -> dict:
    cid = c["id"]
    st = workflow.status(cid)
    ready = _ready(cid)
    dec = db.memory_get(cid, "ORCHESTRATOR", "decision", {})
    flags = db.memory_get(cid, "SENTINEL", "compliance_log", {}).get("violations", [])
    rec = db.memory_get(cid, "NORTHSTAR", "recommendation", {})
    return {"id": cid, "name": c["name"], "email": c["email"], "stage": c["stage"],
            "phase": PHASE_OF.get(c["stage"], "Sourcing"), "job": _job(c["job_id"])["title"],
            "match": db.memory_get(cid, "ORIGIN", "score"),
            "readiness": ready.get("score"), "level": ready.get("level"),
            "decision": dec.get("decision"), "hold": str(rec.get("hiring", "")).startswith("HOLD"),
            "flags": len(flags), "running": st["running"], "waiting": st["waiting"]}


def pool() -> list:
    return [candidate_row(c) for c in db.q("SELECT * FROM candidates ORDER BY id")]


def kpis() -> dict:
    rows = pool()
    scores = [r["readiness"] for r in rows if r["readiness"] is not None]
    pend = db.q("SELECT role, COUNT(*) n FROM approvals WHERE status='pending' GROUP BY role")
    funnel = {p: 0 for p in phases()}
    for r in rows:
        funnel[r["phase"]] += 1
    levels = {"Ready": 0, "Conditionally ready": 0, "Not ready": 0}
    for r in rows:
        if r["level"] in levels:
            levels[r["level"]] += 1
    done = [r for r in rows if r["stage"] == "DONE"]
    return {"candidates": len(rows), "pending": sum(p["n"] for p in pend),
            "pending_by_role": {p["role"]: p["n"] for p in pend},
            "avg_readiness": round(sum(scores) / len(scores), 1) if scores else None,
            "completed": len(done), "holds": sum(1 for r in rows if r["hold"]),
            "ready": levels["Ready"], "funnel": funnel, "levels": levels,
            "audit_events": db.q1("SELECT COUNT(*) n FROM audit")["n"],
            "approvals_done": db.q1("SELECT COUNT(*) n FROM approvals WHERE status<>'pending' "
                                    "AND decided_by NOT LIKE 'DEMO%'")["n"]}


def pending(role: str = None) -> list:
    sql = ("SELECT a.*, c.name candidate_name FROM approvals a JOIN candidates c "
           "ON c.id=a.candidate_id WHERE a.status='pending'")
    args = ()
    if role:
        sql += " AND a.role=?"
        args = (role,)
    out = []
    for a in db.q(sql + " ORDER BY a.id", args):
        res = db.memory_get(a["candidate_id"], a["agent"], "result", {})
        a["data"] = res.get("data", {})
        a["agent_title"] = AGENTS[a["agent"]].title if a["agent"] in AGENTS else a["agent"]
        a["escalation"] = a["summary"].startswith("Supervisor escalation")
        out.append(a)
    return out


_SRC = re.compile(r"\[(\w+):([^\]]*?) score=([\d.\-]+)\]")


def _sources(trace: list) -> list:
    seen, out = set(), []
    for t in trace or []:
        for m in _SRC.finditer(str(t.get("observation", ""))):
            key = (m.group(1), m.group(2))
            if key not in seen:
                seen.add(key)
                out.append({"source": m.group(1), "title": m.group(2), "score": m.group(3)})
    return out


def case_view(cid: int) -> dict:
    c = orch.get_candidate(cid)
    job = _job(c["job_id"])
    st = workflow.status(cid)
    stage = c["stage"]
    ids = orch.STEP_IDS
    plan = db.memory_get(cid, "ATHENA", "plan", [])
    waiting_agent = (st["waiting"] or {}).get("agent")
    steps, agents = [], []
    for i, sid in enumerate(ids):
        typ = orch.STEP_TYPE[sid]
        res = db.memory_get(cid, sid, "result")
        if stage == "DONE" or (stage in ids and i < ids.index(stage)):
            state = "done" if (res or typ == "human") else "skipped"
            if sid in ("LEARNING", "NOVA") and not plan:
                state = "skipped"
        elif sid == stage:
            state = ("error" if (st["waiting"] or {}).get("type") == "error"
                     else "waiting" if st["waiting"] else ("running" if st["running"] else "current"))
        else:
            state = "pending"
        title = AGENTS[sid].title if sid in AGENTS else STEP_TITLE[sid]
        steps.append({"id": sid, "title": title, "type": typ, "state": state})
        if typ == "agent":
            trace = db.memory_get(cid, sid, "trace", [])
            error = db.memory_get(cid, sid, "execution_error")
            ap = db.q("SELECT id, role, status, comment, decided_by, decided, summary "
                      "FROM approvals WHERE candidate_id=? AND agent=? ORDER BY id", (cid, sid))
            agents.append({"id": sid, "title": title, "goal": AGENTS[sid].goal,
                           "state": state, "summary": error["message"] if error else (res or {}).get("summary", ""),
                           "used_llm": (res or {}).get("used_llm", False),
                           "data": (res or {}).get("data", {}), "trace": trace,
                           "sources": _sources(trace), "approvals": ap})
    origin = db.memory_get(cid, "ORIGIN", "result", {}).get("data", {})
    return {
        "id": cid, "name": c["name"], "email": c["email"], "job": job, "stage": stage,
        "phase": PHASE_OF.get(stage, "Sourcing"), "status": st, "steps": steps, "agents": agents,
        "skills": {"found": origin.get("skills_found", []),
                   "matched_required": origin.get("matched_required", []),
                   "matched_nice": origin.get("matched_nice", []),
                   "missing": origin.get("missing_required", []),
                   "inferred": origin.get("inferred_by_ai_half_credit", [])},
        "match": origin.get("score"), "rank": origin.get("rank"), "of": origin.get("of"),
        "plan": plan, "learning": db.memory_get(cid, "NOVA", "completion_records"),
        "scores": db.memory_get(cid, "TITAN", "scores"),
        "integrity": db.memory_get(cid, "SENTINEL", "compliance_log"),
        "readiness": _ready(cid) or None,
        "competency": db.memory_get(cid, "PRISM", "competency_mapping", {}) or db.memory_get(cid, "NORTHSTAR", "competency", {}),
        "recommendation": db.memory_get(cid, "NORTHSTAR", "recommendation"),
        "decision": db.memory_get(cid, "ORCHESTRATOR", "decision"),
        "report": db.memory_get(cid, "OMNIVIEW", "executive_report"),
        "approvals": db.q("SELECT * FROM approvals WHERE candidate_id=? ORDER BY id", (cid,)),
        "audit": db.q("SELECT * FROM audit WHERE candidate_id=? ORDER BY id DESC LIMIT 80", (cid,)),
        "resume_text": c["resume_text"], "waiting_agent": waiting_agent}


def activity(since_id: int = 0, limit: int = 40) -> list:
    rows = db.q("SELECT a.*, c.name candidate_name FROM audit a LEFT JOIN candidates c "
                "ON c.id=a.candidate_id WHERE a.id>? ORDER BY a.id DESC LIMIT ?",
                (since_id, limit))
    return list(reversed(rows))


def health() -> dict:
    return {"agents": observability.agent_health(), "sla": observability.sla_status(),
            "ledger": observability.ledger_summary()}


# Minutes a person would typically spend per task (ASSUMPTIONS - change to match your team)
MANUAL_MINUTES = {"ORIGIN": 25, "ATHENA": 30, "APEX": 45, "TITAN": 20, "OMNIVIEW": 30}


def impact() -> dict:
    """Numbers measured from this session, for the benefits story."""
    secs = []
    for c in db.q("SELECT id, created FROM candidates"):
        r = db.q1("SELECT ts FROM audit WHERE candidate_id=? AND agent='ORIGIN' AND "
                  "event='run_ok' ORDER BY id LIMIT 1", (c["id"],))
        if r:
            secs.append((datetime.fromisoformat(r["ts"]) - datetime.fromisoformat(c["created"])).total_seconds())
    results = db.q("SELECT agent, value FROM memory WHERE key='result'")
    by_agent: dict = {}
    ai_written = 0
    for r in results:
        by_agent[r["agent"]] = by_agent.get(r["agent"], 0) + 1
        try:
            ai_written += 1 if json.loads(r["value"]).get("used_llm") else 0
        except Exception:
            pass
    minutes = sum(MANUAL_MINUTES.get(a, 0) * n for a, n in by_agent.items())
    count = lambda ev: db.q1("SELECT COUNT(*) n FROM audit WHERE event=?", (ev,))["n"]   # noqa: E731
    dec = db.q1("SELECT COUNT(*) n, SUM(CASE WHEN comment IS NOT NULL AND comment<>'' THEN 1 ELSE 0 END) c "
                "FROM approvals WHERE status<>'pending' AND decided_by NOT LIKE 'DEMO%'")
    return {"hours_saved": round(minutes / 60, 1), "shortlist_seconds": round(sum(secs) / len(secs), 1) if secs else None,
            "agent_outputs": len(results), "ai_written": ai_written, "tool_calls": count("tool_call"),
            "escalations": count("escalation"), "chats": count("chat"),
            "decisions": dec["n"], "decisions_commented": dec["c"] or 0,
            "assumptions": MANUAL_MINUTES}
