"""NOVA - Learning Progress Agent: progress, engagement, analytics."""
from .. import agent_runtime as rt
from .. import db
from .base import AgentResult, BaseAgent


class Nova(BaseAgent):
    name = "NOVA"
    title = "Learning Progress Agent"
    goal = "Keep learners engaged and completing"
    approver_role = "Manager"

    def run(self, cand, job):
        plan = db.memory_get(cand["id"], "ATHENA", "plan", [])
        progress = db.memory_get(cand["id"], self.name, "progress", {})
        if plan:
            pcts = [progress.get(p["course"], 0) for p in plan]
            completion = round(sum(pcts) / len(pcts), 1)
            done_hours = round(sum(p["hours"] * progress.get(p["course"], 0) / 100
                                   for p in plan), 1)
        else:
            completion, done_hours = 100.0, 0.0
        engagement = ("high" if completion >= 80 else
                      "medium" if completion >= 50 else "low")
        at_risk = completion < 60
        db.memory_set(cand["id"], self.name, "completion_records",
                      {"completion_pct": completion, "hours_done": done_hours})
        summary = (f"Learning completion {completion}% ({done_hours} h done), "
                   f"engagement {engagement}." + (" AT RISK - manager review." if at_risk else ""))
        return rt.review_result(self, cand, job, AgentResult(summary, {"completion_pct": completion,
                                     "engagement": engagement, "at_risk": at_risk,
                                     "hours_done": done_hours},
                           at_risk, self.approver_role))
