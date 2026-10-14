"""ATHENA - Learning Intelligence Agent: skill gaps -> learning path.
Courses are RETRIEVED (RAG) from the learning catalog + your knowledge folder."""
import re

from .. import agent_runtime as rt
from .. import db, rag, settings, skills
from ..tools import make_tools
from .base import AgentResult, BaseAgent

FOUNDATION = ["excel", "sql", "python", "statistics", "data cleaning", "pandas", "git"]
PATTERN = re.compile(r"Learning resource for ([^:\n]+): (.+?)\. Estimated (\d+) hours")


def retrieve_course(skill: str) -> dict:
    """Find a course for this skill with RAG; fall back to the built-in catalog."""
    for hit in rag.search(f"learning resource for {skill}", k=5,
                          source=("catalog", "docs")):
        for m in PATTERN.finditer(hit["text"]):
            if m.group(1).strip().lower() == skill:
                return {"skill": skill, "course": m.group(2), "hours": int(m.group(3)),
                        "source": f"{hit['source']}:{hit['title']}"}
    item = skills.learning_item(skill)
    item["source"] = "built-in catalog"
    return item


def _order(gaps: list) -> list:
    return sorted(gaps, key=lambda s: FOUNDATION.index(s) if s in FOUNDATION else 99)


class Athena(BaseAgent):
    name = "ATHENA"
    title = "Learning Intelligence Agent"
    goal = "Close each person's skill gaps with a personal plan"
    approver_role = "Learning Team"

    def run(self, cand, job):
        found = skills.extract_skills(cand["resume_text"])
        origin = db.memory_get(cand["id"], "ORIGIN", "skills", found)
        gaps_req = _order([s for s in job["required"] if s not in origin])
        gaps_nice = _order([s for s in job["nice"] if s not in origin])
        plan = [retrieve_course(s) for s in gaps_req + gaps_nice[:2]]
        hours = sum(p["hours"] for p in plan)
        fallback = (f"{len(plan)} learning item(s), about {hours} hours. Foundations "
                    "first, required skills before nice-to-have."
                    if plan else "No skill gaps found - no learning plan needed.")
        text, used = fallback, False
        if settings.agentic():
            task = (f"Design a learning path for {job['title']}. Required gaps: {gaps_req}. "
                    f"Optional gaps: {gaps_nice}. Use get_learning_resources and policy tools. "
                    "Include every required gap exactly once, and at most two optional gaps. "
                    "Choose the order based on prerequisites and candidate evidence. "
                    'Finish with {"ordered_skills": ["skill", ...], "summary": "explain the plan"}. '
                    "Use an empty list if there are no gaps.")
            final, _ = rt.react(cand["id"], self, task, make_tools(cand, job),
                                required_tools=("get_learning_resources",))
            text = rt.require_text(cand["id"], self, final)
            ordered = final.get("ordered_skills")
            if (not isinstance(ordered, list) or
                    not all(isinstance(s, str) for s in ordered) or
                    len(ordered) != len(set(ordered)) or
                    not set(gaps_req) <= set(ordered) or
                    not set(ordered) <= set(gaps_req + gaps_nice) or
                    len(set(ordered) - set(gaps_req)) > 2):
                rt._fail(cand["id"], self, db.memory_get(cand["id"], self.name, "trace", []),
                         "Invalid learning plan: cover all required gaps once and at most two optional gaps.")
            plan = [retrieve_course(s) for s in ordered]
            hours = sum(p["hours"] for p in plan)
            used = True
        elif plan:
            task = (f"Candidate for {job['title']} has this learning plan: "
                    f"{[(p['skill'], p['course'], p['hours']) for p in plan]}. Use "
                    f"search_knowledge (source docs) to check the learning guidance, "
                    f'then finish with {{"summary": "2 encouraging, practical sentences"}}.')
            final, _ = rt.react(cand["id"], self, task, make_tools(cand, job))
            t = rt.clean_text((final or {}).get("summary"))
            if t:
                text, used = t + " " + fallback, True
        db.memory_set(cand["id"], self.name, "skill_gaps",
                      {"required": gaps_req, "nice": gaps_nice})
        db.memory_set(cand["id"], self.name, "plan", plan)
        return AgentResult(text, {"gaps_required": gaps_req, "plan": plan,
                                  "total_hours": hours}, True, self.approver_role, used)
