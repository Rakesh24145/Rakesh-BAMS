"""APEX - Assessment Agent: builds the test from the job's required skills."""
import json

from .. import agent_runtime as rt
from .. import db, settings, skills
from ..tools import make_tools
from .base import AgentResult, BaseAgent

# One small coding task. TITAN runs the candidate's code against these tests.
CODING_TASK = {
    "function": "is_palindrome",
    "prompt": ("Write a Python function is_palindrome(s) that returns True if the "
               "text reads the same forwards and backwards, ignoring case, spaces "
               "and punctuation."),
    "starter": "def is_palindrome(s):\n    # your code here\n    pass\n",
    "tests": [["Racecar", True], ["hello", False],
              ["A man, a plan, a canal: Panama", True], ["", True]],
    "solution": ("def is_palindrome(s):\n"
                 "    t = [ch.lower() for ch in s if ch.isalnum()]\n"
                 "    return t == t[::-1]\n"),
}


class Apex(BaseAgent):
    name = "APEX"
    title = "Assessment Agent"
    goal = "Test the right competencies fairly"
    approver_role = "Assessment Owner"

    def run(self, cand, job):
        questions = []
        for skill in job["required"]:
            for item in skills.BANK.get(skill, [])[:2]:
                questions.append({**item, "skill": skill})
        questions = questions[:10]
        if not questions:
            questions = [{**g, "skill": "general"} for g in skills.GENERIC]
        text = None
        if settings.agentic():
            tools = make_tools(cand, job)
            tools["get_question_bank"] = (
                lambda: json.dumps([{k: v for k, v in q.items() if k != "answer"}
                                    for q in questions]),
                "get_question_bank() - approved question IDs, skills, prompts and options")
            final, _ = rt.react(cand["id"], self,
                                "Design this candidate's assessment. Retrieve get_question_bank and "
                                "choose up to 10 distinct question IDs, covering every skill in the bank "
                                "at least once. Use candidate evidence to choose the order and depth. "
                                'Finish with {"question_ids": ["id", ...], "summary": "explain your design"}. '
                                "Do not invent questions or answer keys.", tools,
                                required_tools=("get_question_bank",))
            text = rt.require_text(cand["id"], self, final)
            ids = final.get("question_ids")
            bank = {q["id"]: q for q in questions}
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 10 or
                    not all(isinstance(i, str) and i in bank for i in ids) or
                    len(ids) != len(set(ids)) or
                    {bank[i]["skill"] for i in ids} != {q["skill"] for q in questions}):
                rt._fail(cand["id"], self, db.memory_get(cand["id"], self.name, "trace", []),
                         "Invalid assessment: use distinct approved IDs and cover every bank skill.")
            questions = [bank[i] for i in ids]
        with_coding = "python" in job["required"]
        assessment = {"questions": questions,
                      "coding": CODING_TASK if with_coding else None}
        db.memory_set(cand["id"], self.name, "assessment", assessment)
        comp = sorted({skills.CATEGORY.get(q["skill"], "General") for q in questions})
        db.memory_set(cand["id"], self.name, "competencies_covered", comp)
        summary = (f"Assessment ready: {len(questions)} multiple-choice question(s)"
                   f"{' + 1 coding task' if with_coding else ''}. "
                   f"Competencies: {', '.join(comp)}.")
        return AgentResult((text + " " + summary) if text else summary, {"n_questions": len(questions),
                                     "coding": with_coding, "competencies": comp},
                           True, self.approver_role, bool(text))
