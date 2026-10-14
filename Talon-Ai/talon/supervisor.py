"""SUPERVISOR - watches every agent result and decides if an EXTRA human review is needed.

Agentic, but safe by design: the supervisor can only make the workflow STRICTER
(add a reviewer). It can never skip or remove an approval.
Rules give a baseline; if an AI model is connected it can add its own judgement,
which is validated before use."""
from . import agent_runtime as rt
from . import db, llm, observability, settings

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
    if settings.agentic():
        class Supervisor:
            name = "SUPERVISOR"
            title = "Human Review Supervisor"
            goal = "Identify weak evidence or inconsistencies; only add human review"

        evidence = {"stage": agent, "summary": res.summary, "data": res.data,
                    "mandatory_extra_review": found, "allowed_roles": roles}
        tools = {
            "get_review_evidence": (lambda: evidence,
                                    "get_review_evidence() - stage result, mandatory review and allowed roles")
        }
        final, _ = rt.react(
            cid, Supervisor(),
            'Assess whether an EXTRA human review is needed. Finish with {"extra_review": true or false, '
            '"role": "allowed role", "reason": "one factual sentence"}. '
            "Existing and mandatory reviews cannot be removed.", tools,
            required_tools=("get_review_evidence",))
        reason = rt.require_text(cid, Supervisor(), final, key="reason", limit=299)
        if not isinstance(final.get("extra_review"), bool) or final.get("role") not in roles:
            rt._fail(cid, Supervisor(), db.memory_get(cid, "SUPERVISOR", "trace", []),
                     "Invalid supervisor response: boolean extra_review and an allowed role are required.")
        return found or ({"role": final["role"], "reason": reason} if final["extra_review"] else None)
    if found:
        return found
    if agent in LLM_REVIEWED and llm.available() and llm.enabled_for("SUPERVISOR"):
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
