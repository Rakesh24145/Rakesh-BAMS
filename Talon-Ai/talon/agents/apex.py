"""APEX - Assessment Agent: builds the test from the job's required skills."""
from .. import db, skills
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
        with_coding = "python" in job["required"]
        assessment = {"questions": questions,
                      "coding": CODING_TASK if with_coding else None}
        db.memory_set(cand["id"], self.name, "assessment", assessment)
        comp = sorted({skills.CATEGORY.get(q["skill"], "General") for q in questions})
        db.memory_set(cand["id"], self.name, "competencies_covered", comp)
        summary = (f"Assessment ready: {len(questions)} multiple-choice question(s)"
                   f"{' + 1 coding task' if with_coding else ''}. "
                   f"Competencies: {', '.join(comp)}.")
        return AgentResult(summary, {"n_questions": len(questions),
                                     "coding": with_coding, "competencies": comp},
                           True, self.approver_role)
