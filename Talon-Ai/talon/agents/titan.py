"""TITAN - Evaluation Agent: objective scoring, coding evaluation, AI review."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .. import agent_runtime as rt
from .. import config, db
from ..tools import make_tools
from .apex import CODING_TASK
from .base import AgentResult, BaseAgent


def run_code_tests(code: str) -> dict:
    """Run candidate code in a separate Python process with a time limit.
    NOTE: prototype only - this is NOT a secure sandbox."""
    fn = CODING_TASK["function"]
    harness = (code + "\n\nimport json\n_t = " + repr(CODING_TASK["tests"]) +
               "\n_r = []\nfor _a, _e in _t:\n    try:\n"
               f"        _r.append(bool({fn}(_a) == _e))\n"
               "    except Exception:\n        _r.append(False)\nprint(json.dumps(_r))\n")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidate.py"
        path.write_text(harness, encoding="utf-8")
        try:
            out = subprocess.run([sys.executable, "-I", str(path)], capture_output=True,
                                 text=True, timeout=config.CODING_TIMEOUT_SECONDS)
            results = json.loads(out.stdout.strip().splitlines()[-1])
        except Exception as exc:          # timeout, syntax error, no output...
            return {"passed": 0, "total": len(CODING_TASK["tests"]),
                    "score": 0.0, "error": type(exc).__name__}
    return {"passed": sum(results), "total": len(results),
            "score": round(100 * sum(results) / len(results), 1), "error": ""}


class Titan(BaseAgent):
    name = "TITAN"
    title = "Evaluation Agent"
    goal = "Score objectively and consistently"
    approver_role = "Interviewer"

    def run(self, cand, job):
        assessment = db.memory_get(cand["id"], "APEX", "assessment", {})
        sub = db.memory_get(cand["id"], "APEX", "submission", {})
        qs = assessment.get("questions", [])
        per_skill: dict = {}
        correct = 0
        for q in qs:
            ok = sub.get("answers", {}).get(q["id"]) == q["answer"]
            correct += ok
            s = per_skill.setdefault(q["skill"], [0, 0])
            s[0] += ok
            s[1] += 1
        objective = round(100 * correct / len(qs), 1) if qs else 0.0
        coding = None
        if assessment.get("coding"):
            coding = run_code_tests(sub.get("code", ""))
        total = objective if coding is None else round(0.7 * objective +
                                                       0.3 * coding["score"], 1)
        skill_scores = {k: round(100 * v[0] / v[1]) for k, v in per_skill.items()}
        db.memory_set(cand["id"], self.name, "scores",
                      {"objective": objective, "coding": coding, "total": total,
                       "per_skill": skill_scores})
        fallback = (f"Objective {objective}% ({correct}/{len(qs)})"
                    + (f", coding {coding['passed']}/{coding['total']} tests"
                       if coding else "") + f". Overall {total}/100.")
        task = (f"Review this assessment result neutrally. Per-skill scores: "
                f"{skill_scores}. Coding: {coding}. Overall: {total}. Use "
                f"search_knowledge (source docs) for the proficiency levels. Finish "
                f'with {{"summary": "2 neutral sentences, no hiring advice"}}.')
        final, _ = rt.react(cand["id"], self, task, make_tools(cand, job))
        llm_text = rt.require_text(cand["id"], self, final)
        text, used = (llm_text + " " + fallback, True) if llm_text else (fallback, False)
        db.memory_set(cand["id"], self.name, "evaluation_result", text)
        return AgentResult(text, {"objective": objective, "coding": coding,
                                  "total": total, "per_skill": skill_scores},
                           True, self.approver_role, used)
