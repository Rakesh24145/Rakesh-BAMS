"""SENTINEL - Integrity Agent: monitoring records, compliance, violations."""
import re

from .. import agent_runtime as rt
from .. import config, db
from .base import AgentResult, BaseAgent


def _norm(code: str) -> str:
    return re.sub(r"\s+", "", code or "")


class Sentinel(BaseAgent):
    name = "SENTINEL"
    title = "Integrity Agent"
    goal = "Keep assessments honest and compliant"
    approver_role = "HR"

    def run(self, cand, job):
        sub = db.memory_get(cand["id"], "APEX", "submission", {})
        violations = []
        n = max(sub.get("n_questions", 0), 1)
        avg = sub.get("seconds_total", 0) / n
        if avg < config.MIN_SECONDS_PER_QUESTION:
            violations.append(f"Answered too fast (avg {avg:.1f}s per question)")
        answers = list((sub.get("answers") or {}).values())
        if len(answers) >= 5 and len(set(answers)) == 1:
            violations.append("Identical answer option chosen for every question")
        if sub.get("declared_external_help"):
            violations.append("Candidate declared use of external help")
        code = _norm(sub.get("code"))
        if len(code) > 40:
            for other in db.q("SELECT candidate_id cid, value v FROM memory WHERE "
                              "agent='APEX' AND key='submission' AND candidate_id<>?",
                              (cand["id"],)):
                import json
                if _norm(json.loads(other["v"]).get("code")) == code:
                    violations.append(f"Code identical to candidate #{other['cid']}")
        db.memory_set(cand["id"], self.name, "compliance_log",
                      {"avg_seconds_per_question": round(avg, 1),
                       "violations": violations})
        summary = ("No integrity violations detected." if not violations
                   else "Possible violations: " + "; ".join(violations))
        return rt.review_result(self, cand, job, AgentResult(summary, {"violations": violations,
                                     "avg_seconds": round(avg, 1)},
                           bool(violations), self.approver_role))
