"""ATLAS (monitoring / audit) and LEDGER (token + cost tracking)."""
from datetime import datetime

from . import config, db

AGENT_NAMES = ["ORIGIN", "GENESIS", "ATHENA", "NOVA", "APEX",
               "SENTINEL", "TITAN", "PRISM", "NORTHSTAR", "OMNIVIEW"]


# ------------------------------- ATLAS -------------------------------------
def log(candidate_id, agent: str, event: str, detail="") -> None:
    db.run(
        "INSERT INTO audit(ts,candidate_id,agent,event,detail) VALUES (?,?,?,?,?)",
        (db.now(), candidate_id, agent, event, str(detail)[:500]),
    )


def agent_health() -> list:
    rows = []
    for name in AGENT_NAMES:
        ok = db.q1("SELECT COUNT(*) n, MAX(ts) last FROM audit "
                   "WHERE agent=? AND event='run_ok'", (name,))
        err = db.q1("SELECT COUNT(*) n FROM audit "
                    "WHERE agent=? AND event='run_error'", (name,))
        status = "no runs yet"
        if ok["n"] or err["n"]:
            status = "healthy" if err["n"] == 0 else "has errors"
        rows.append({"agent": name, "status": status, "successful_runs": ok["n"],
                     "errors": err["n"], "last_run": ok["last"] or "-"})
    return rows


def sla_status() -> list:
    rows = []
    for a in db.q("SELECT * FROM approvals WHERE status='pending'"):
        age = (datetime.now() - datetime.fromisoformat(a["created"])).total_seconds()
        hours = round(age / 3600, 2)
        rows.append({"approval_id": a["id"], "candidate_id": a["candidate_id"],
                     "agent": a["agent"], "waiting_for": a["role"],
                     "hours_waiting": hours,
                     "sla": "BREACH" if hours > config.SLA_HOURS_FOR_APPROVAL else "ok"})
    return rows


def recent_audit(limit: int = 100) -> list:
    return db.q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))


# ------------------------------- LEDGER ------------------------------------
def log_llm(agent, model, prompt_tokens, completion_tokens, latency_ms) -> None:
    cost = (prompt_tokens + completion_tokens) / 1000 * config.EST_CLOUD_COST_PER_1K_TOKENS
    db.run(
        "INSERT INTO ledger(ts,agent,model,prompt_tokens,completion_tokens,"
        "est_cost,latency_ms) VALUES (?,?,?,?,?,?,?)",
        (db.now(), agent, model, prompt_tokens, completion_tokens, cost, latency_ms),
    )


def ledger_summary() -> dict:
    tot = db.q1("SELECT COUNT(*) calls, COALESCE(SUM(prompt_tokens),0) p, "
                "COALESCE(SUM(completion_tokens),0) c, COALESCE(SUM(est_cost),0) cost "
                "FROM ledger")
    by_agent = db.q("SELECT agent, COUNT(*) calls, SUM(prompt_tokens+completion_tokens) "
                    "tokens FROM ledger GROUP BY agent ORDER BY tokens DESC")
    return {"calls": tot["calls"], "prompt_tokens": tot["p"],
            "completion_tokens": tot["c"], "est_cloud_cost_usd": round(tot["cost"], 4),
            "actual_cost_usd": 0.0, "by_agent": by_agent}
