"""GENESIS - Onboarding Agent: registration + (simulated) identity validation."""
import re

from .. import agent_runtime as rt
from .. import db
from .base import AgentResult, BaseAgent


class Genesis(BaseAgent):
    name = "GENESIS"
    title = "Onboarding Agent"
    goal = "Onboard verified candidates smoothly"
    approver_role = "HR"

    def run(self, cand, job):
        issues = []
        if not (cand["name"] or "").strip():
            issues.append("Name is missing")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cand["email"] or ""):
            issues.append("Email format looks invalid")
        if len(cand["resume_text"] or "") < 200:
            issues.append("Resume is very short (under 200 characters)")
        dup = db.q("SELECT id FROM candidates WHERE lower(email)=lower(?) AND id<>?",
                   (cand["email"], cand["id"]))
        if dup:
            issues.append(f"Same email used by candidate #{dup[0]['id']}")

        status = "verified" if not issues else "needs_review"
        db.memory_set(cand["id"], self.name, "verification_status", status)
        db.memory_set(cand["id"], self.name, "profile", {
            "name": cand["name"], "email": cand["email"], "job": job["title"]})
        summary = ("Profile verified (simulated checks: name, email format, resume "
                   "length, duplicates).") if not issues else \
            "Needs human review: " + "; ".join(issues)
        return rt.review_result(self, cand, job,
                                AgentResult(summary, {"status": status, "issues": issues},
                                            bool(issues), self.approver_role))
