"""NORTHSTAR - Recommendation Agent: hiring, deployment, upskilling.
Policy is RETRIEVED (RAG) from knowledge/hiring_policy.txt and ENFORCED in code."""
from .. import agent_runtime as rt
from .. import db, rag
from ..tools import make_tools
from .base import AgentResult, BaseAgent


class Northstar(BaseAgent):
    name = "NORTHSTAR"
    title = "Recommendation Agent"
    goal = "Turn evidence into hire, deploy or upskill calls"
    approver_role = "HR"

    def run(self, cand, job):
        r = db.memory_get(cand["id"], "PRISM", "readiness", {})
        comp = db.memory_get(cand["id"], "PRISM", "competency_mapping", {})
        scores = db.memory_get(cand["id"], "TITAN", "scores", {})
        flags = db.memory_get(cand["id"], "SENTINEL", "compliance_log", {}) \
            .get("violations", [])
        level = r.get("level", "Not ready")
        hire = {"Ready": "Recommend HIRE",
                "Conditionally ready": "Recommend HIRE with an upskilling plan",
                "Not ready": "Do NOT proceed now - re-assess after upskilling"}[level]
        if flags and level != "Not ready":                  # policy rule 2, in code
            hire = "HOLD - integrity flags must be cleared by HR before any hire"
        best = max(comp, key=comp.get) if comp else "General"
        deploy = (f"Deploy to a {best}-focused team" if level != "Not ready"
                  and not flags else "No deployment yet")
        weak = [s for s, v in scores.get("per_skill", {}).items() if v < 70]
        upskill = ("Upskill in: " + ", ".join(weak)) if weak else "No upskilling needed"
        policy = [{"doc": h["title"], "text": h["text"][:200]} for h in
                  rag.search(f"hiring recommendation policy for a {level} candidate",
                             k=2, source="docs")]
        fallback = f"{hire}. {deploy}. {upskill}."

        task = (f"Explain to an HR approver this recommendation: '{hire}'. Readiness "
                f"{r}. Integrity flags: {flags}. Call search_knowledge (source docs) "
                f"to find the relevant policy, then finish with "
                f'{{"summary": "2 neutral sentences citing the policy; remind that '
                f'a human decides"}}.')
        final, _ = rt.react(cand["id"], self, task, make_tools(cand, job))
        t = rt.clean_text((final or {}).get("summary"))
        rec = {"hiring": hire, "deployment": deploy, "upskilling": upskill,
               "policy_evidence": policy, "integrity_flags": flags}
        db.memory_set(cand["id"], self.name, "recommendation", rec)
        return AgentResult((t + " " + fallback) if t else fallback, rec, True,
                           self.approver_role, bool(t))
