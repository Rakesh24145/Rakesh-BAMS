"""PRISM - Readiness Intelligence Agent: strengths, skill map, readiness."""
from .. import db, skills
from .base import AgentResult, BaseAgent


class Prism(BaseAgent):
    name = "PRISM"
    title = "Readiness Intelligence Agent"
    goal = "Show who is work-ready, and where"
    approver_role = "Hiring Manager"

    def run(self, cand, job):
        fit = db.memory_get(cand["id"], "ORIGIN", "score", 0)
        learn = db.memory_get(cand["id"], "NOVA", "completion_records", {})
        scores = db.memory_get(cand["id"], "TITAN", "scores", {})
        integrity = db.memory_get(cand["id"], "SENTINEL", "compliance_log", {})
        learn_pct = learn.get("completion_pct", 100)
        total = scores.get("total", 0)
        penalty = 15 if integrity.get("violations") else 0
        readiness = round(0.3 * min(fit, 100) + 0.2 * learn_pct + 0.5 * total
                          - penalty, 1)
        level = ("Ready" if readiness >= 75 else
                 "Conditionally ready" if readiness >= 55 else "Not ready")
        per_skill = scores.get("per_skill", {})
        strengths = [s for s, v in per_skill.items() if v >= 70]
        weak = [s for s, v in per_skill.items() if v < 70]
        cmap: dict = {}
        for s, v in per_skill.items():
            cmap.setdefault(skills.CATEGORY.get(s, "General"), []).append(v)
        competency = {k: round(sum(v) / len(v)) for k, v in cmap.items()}
        db.memory_set(cand["id"], self.name, "readiness",
                      {"score": readiness, "level": level})
        db.memory_set(cand["id"], self.name, "competency_mapping", competency)
        summary = (f"Readiness {readiness}/100 - {level}. Strengths: "
                   f"{', '.join(strengths) or 'none yet'}. To improve: "
                   f"{', '.join(weak) or 'none'}.")
        return AgentResult(summary, {"readiness": readiness, "level": level,
                                     "strengths": strengths, "weak": weak,
                                     "competency": competency},
                           True, self.approver_role)
