"""OMNIVIEW - Executive Intelligence Agent: reports and portfolio dashboard."""
from .. import agent_runtime as rt
from .. import db
from ..tools import make_tools
from .base import AgentResult, BaseAgent


def portfolio() -> dict:
    """Numbers for the executive dashboard (all candidates)."""
    cands = db.q("SELECT id, stage FROM candidates")
    funnel: dict = {}
    for c in cands:
        funnel[c["stage"]] = funnel.get(c["stage"], 0) + 1
    scores = [db.memory_get(c["id"], "PRISM", "readiness", {}).get("score")
              for c in cands]
    scores = [s for s in scores if s is not None]
    pending = db.q1("SELECT COUNT(*) n FROM approvals WHERE status='pending'")["n"]
    return {"candidates": len(cands), "funnel": funnel, "pending_approvals": pending,
            "avg_readiness": round(sum(scores) / len(scores), 1) if scores else None,
            "completed": funnel.get("DONE", 0)}


class Omniview(BaseAgent):
    name = "OMNIVIEW"
    title = "Executive Intelligence Agent"
    goal = "Give leaders one trusted view of talent"
    approver_role = "Executive"

    def run(self, cand, job):
        mem = db.memory_all(cand["id"])
        rec = mem.get("NORTHSTAR", {}).get("recommendation", {})
        ready = mem.get("PRISM", {}).get("readiness") or mem.get("NORTHSTAR", {}).get("readiness", {})
        report = {
            "candidate": cand["name"], "role": job["title"],
            "match_score": mem.get("ORIGIN", {}).get("score"),
            "learning": mem.get("NOVA", {}).get("completion_records"),
            "assessment": mem.get("TITAN", {}).get("scores"),
            "integrity": mem.get("SENTINEL", {}).get("compliance_log"),
            "readiness": ready, "recommendation": rec,
        }
        fallback = (f"{cand['name']} for {job['title']}: readiness "
                    f"{ready.get('score', '-')} ({ready.get('level', '-')}). "
                    f"{rec.get('hiring', '')}.")
        task = (f"Write an executive summary of this candidate report: {report}. "
                f'Finish with {{"summary": "3 short factual sentences"}}.')
        final, _ = rt.react(cand["id"], self, task, make_tools(cand, job))
        t = rt.require_text(cand["id"], self, final, limit=900)
        text, used = (t, True) if t else (fallback, False)
        db.memory_set(cand["id"], self.name, "executive_report",
                      {"summary": text, **report})
        return AgentResult(text, report, True, self.approver_role, used)
