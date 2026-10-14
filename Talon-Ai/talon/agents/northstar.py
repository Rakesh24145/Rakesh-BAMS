"""NORTHSTAR - Recommendation Agent: hiring, deployment, upskilling.
Policy is RETRIEVED (RAG) from knowledge/hiring_policy.txt and ENFORCED in code."""
from .. import agent_runtime as rt
from .. import db, rag, skills
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
        origin = db.memory_get(cand["id"], "ORIGIN", "result", {}).get("data", {})
        if not r:        # LITE mode (no PRISM agent): derive readiness from match + learning effort
            hours = db.memory_get(cand["id"], "ATHENA", "result", {}).get("data", {}).get("total_hours", 0)
            score = round(0.6 * min(origin.get("score", 0), 100) + 0.4 * max(0, 100 - 2 * hours), 1)
            r = {"score": score, "level": ("Ready" if score >= 75 else
                                           "Conditionally ready" if score >= 55 else "Not ready")}
            db.memory_set(cand["id"], self.name, "readiness", r)
            cats: dict = {}
            for sk in origin.get("matched_required", []) + origin.get("matched_nice", []):
                cats.setdefault(skills.CATEGORY.get(sk, "General"), []).append(100)
            comp = {k: round(sum(v) / len(v)) for k, v in cats.items()}
        level = r.get("level", "Not ready")
        hire = {"Ready": "Recommend HIRE",
                "Conditionally ready": "Recommend HIRE with an upskilling plan",
                "Not ready": "Do NOT proceed now - re-assess after upskilling"}[level]
        if flags and level != "Not ready":                  # policy rule 2, in code
            hire = "HOLD - integrity flags must be cleared by HR before any hire"
        if level != "Not ready" and origin and not origin.get("years") and not flags:   # policy rule 6
            hire = "HOLD - experience is not stated in the resume; a recruiter must confirm it before any hire"
            flags = ["Years of experience not stated"]
        best = max(comp, key=comp.get) if comp else "General"
        deploy = (f"Deploy to a {best}-focused team" if level != "Not ready"
                  and not flags else "No deployment yet")
        weak = [s for s, v in scores.get("per_skill", {}).items() if v < 70] or origin.get("missing_required", [])
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
        final, _ = rt.react(cand["id"], self, task, make_tools(cand, job),
                            required_tools=("search_knowledge",))
        t = rt.require_text(cand["id"], self, final)
        rec = {"hiring": hire, "deployment": deploy, "upskilling": upskill,
               "policy_evidence": policy, "integrity_flags": flags}
        db.memory_set(cand["id"], self.name, "recommendation", rec)
        return AgentResult((t + " " + fallback) if t else fallback, rec, True,
                           self.approver_role, bool(t))
