"""SUPERVISOR - watches every agent result and decides if an EXTRA human review is needed.

Agentic, but safe by design: the supervisor can only make the workflow STRICTER
(add a reviewer). It can never skip or remove an approval.
Rules give a baseline; if an AI model is connected it can add its own judgement,
which is validated before use."""
from . import llm, observability

LLM_REVIEWED = ("ORIGIN", "TITAN", "PRISM")          # keeps AI calls (and quota) low


def _rule(agent: str, res) -> dict:
    d = res.data or {}
    if agent == "ORIGIN" and 40 <= d.get("score", 0) < 60:
        return {"role": "HR", "reason": f"Borderline match score ({d['score']}). "
                "A second reviewer should confirm the shortlist decision."}
    if agent == "ORIGIN" and d.get("inferred_by_ai_half_credit"):
        return {"role": "HR", "reason": "The score includes skills inferred by the AI "
                f"({', '.join(d['inferred_by_ai_half_credit'])}). Please verify the evidence."}
    if agent == "TITAN" and 45 <= d.get("total", 100) < 60:
        return {"role": "Hiring Manager", "reason": f"Borderline assessment result "
                f"({d['total']}). Consider a follow-up interview."}
    return None


def extra_review(cid: int, agent: str, res, roles: list):
    found = _rule(agent, res)
    if found:
        return found
    if agent in LLM_REVIEWED and llm.available():
        out = llm.chat_json(
            "SUPERVISOR",
            "You are the Supervisor of a talent workflow. You may only ADD human review, "
            "never remove it. Reply with JSON only: "
            '{"extra_review": true or false, "role": "<one of %s>", "reason": "one sentence"}. '
            "Say true only for borderline, inconsistent or weakly evidenced results." % roles,
            f"Step {agent} result: {res.summary}\nData: {str(res.data)[:700]}", 120)
        if out and out.get("extra_review") is True and out.get("role") in roles \
                and isinstance(out.get("reason"), str) and 5 < len(out["reason"]) < 300:
            return {"role": out["role"], "reason": out["reason"]}
    return None
