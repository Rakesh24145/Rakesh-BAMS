"""ASK TALON - a conversational agent over the whole talent pool.
With an AI model it plans, calls data tools and answers (agentic RAG).
Without one it answers common leadership questions from the same tools."""
import json
import re

from . import agent_runtime as rt
from . import db, llm, rag, reports, settings, views


class _Agent:
    name, title = "ASK_TALON", "Talent Copilot"
    goal = "Answer leaders' questions about the talent pool using only tool results"


def _find(text: str):
    rows = views.pool()
    low = (text or "").lower()
    m = re.search(r"#(\d+)", low)
    if m:
        return next((r for r in rows if r["id"] == int(m.group(1))), None)
    for r in rows:
        parts = [p for p in r["name"].lower().split() if len(p) > 2]
        if r["name"].lower() in low or any(p in low for p in parts):
            return r
    return None


def _all_found(text: str) -> list:
    low, out = (text or "").lower(), []
    for r in views.pool():
        if any(p in low for p in r["name"].lower().split() if len(p) > 2) and r not in out:
            out.append(r)
    return out


def _line(r: dict) -> str:
    bits = [f"**{r['name']}** (#{r['id']})", f"stage {r['stage']}"]
    if r["readiness"] is not None:
        bits.append(f"readiness {r['readiness']} ({r['level']})")
    elif r["match"] is not None:
        bits.append(f"match {r['match']}")
    if r["decision"]:
        bits.append(r["decision"])
    return " - ".join(bits)


# ------------------------------ tools --------------------------------------
def t_pool_overview() -> str:
    k = views.kpis()
    return json.dumps({k2: k[k2] for k2 in ("candidates", "pending", "pending_by_role", "avg_readiness",
                                            "completed", "holds", "ready", "funnel", "levels")})


def t_list_candidates(level: str = None, stage: str = None, min_readiness: float = None) -> str:
    rows = views.pool()
    if level:
        rows = [r for r in rows if (r["level"] or "").lower() == level.lower()]
    if stage:
        rows = [r for r in rows if r["stage"].lower() == stage.lower()]
    if min_readiness is not None:
        rows = [r for r in rows if (r["readiness"] or 0) >= float(min_readiness)]
    rows.sort(key=lambda r: -(r["readiness"] or r["match"] or 0))
    return json.dumps([{k: r[k] for k in ("id", "name", "stage", "match", "readiness", "level",
                                          "decision", "flags")} for r in rows])


def t_candidate_report(candidate: str) -> str:
    r = _find(str(candidate))
    if not r:
        return "No candidate found."
    v = views.case_view(r["id"])
    return json.dumps({"name": v["name"], "stage": v["stage"], "match": v["match"],
                       "skills": v["skills"], "readiness": v["readiness"], "scores": v["scores"],
                       "integrity": v["integrity"], "recommendation": v["recommendation"],
                       "pending_approvals": [a["role"] for a in v["approvals"] if a["status"] == "pending"]},
                      default=str)[:1800]


def t_compare(a: str, b: str) -> str:
    return json.dumps([json.loads(t_candidate_report(x)) if t_candidate_report(x)[0] == "{" else x
                       for x in (a, b)])[:2400]


def t_pending(role: str = None) -> str:
    return json.dumps([{"id": a["id"], "candidate": a["candidate_name"], "step": a["agent"],
                        "role": a["role"], "note": a["summary"][:120]} for a in views.pending(role)])


def t_search(query: str, source: str = None) -> str:
    hits = rag.search(str(query), k=3, source=source if source in ("skills", "catalog", "docs", "jobs") else None)
    return "\n".join(f"[{h['source']}:{h['title']} score={h['score']}] {h['text'][:300]}" for h in hits) or "No results."


def t_draft(candidate: str, kind: str = "feedback") -> str:
    r = _find(str(candidate))
    return reports.draft_message(r["id"], kind if kind in ("feedback", "invite", "brief") else "feedback") if r else "No candidate found."


TOOLS = {
    "pool_overview": (t_pool_overview, "pool_overview() - counts, funnel, readiness levels, pending approvals"),
    "list_candidates": (t_list_candidates, "list_candidates(level, stage, min_readiness) - all optional filters; level is Ready|Conditionally ready|Not ready"),
    "candidate_report": (t_candidate_report, "candidate_report(candidate) - full facts for one person by name or #id"),
    "compare": (t_compare, "compare(a, b) - two candidates side by side"),
    "pending_approvals": (t_pending, "pending_approvals(role) - what humans still need to decide; role optional"),
    "search_knowledge": (t_search, "search_knowledge(query, source) - company policy, competency framework, learning catalog"),
    "draft_message": (t_draft, "draft_message(candidate, kind) - kind is feedback|invite|brief"),
}


# ------------------------------ rule-based answers --------------------------
def _rules(msg: str):
    low, steps = msg.lower(), []
    rows = views.pool()
    found = _all_found(msg)
    if len(found) >= 2 and re.search(r"compar|versus|\bvs\b| and ", low):
        steps.append("compare")
        a, b = found[:2]
        return "\n".join(["Side by side:"] + [f"- {_line(x)}; missing skills: "
                          f"{', '.join(views.case_view(x['id'])['skills']['missing']) or 'none'}" for x in (a, b)]), steps
    if re.search(r"email|draft|message|feedback|invite", low) and found:
        steps.append("draft_message")
        kind = "invite" if "invite" in low else ("brief" if "brief" in low else "feedback")
        return reports.draft_message(found[0]["id"], kind), steps
    if found:
        steps.append("candidate_report")
        v = views.case_view(found[0]["id"])
        r = v["readiness"] or {}
        rec = v["recommendation"] or {}
        lines = [f"**{v['name']}** is at stage **{v['stage']}** for {v['job']['title']}.",
                 f"- Match score: {v['match']} (rank {v['rank']} of {v['of']}); missing: {', '.join(v['skills']['missing']) or 'nothing'}"]
        if r:
            lines.append(f"- Readiness: {r.get('score')} - {r.get('level')}")
        if rec:
            lines.append(f"- Recommendation: {rec.get('hiring')}")
        flags = (v["integrity"] or {}).get("violations", [])
        if flags:
            lines.append("- Integrity flags: " + "; ".join(flags))
        w = v["status"]["waiting"]
        if w:
            lines.append(f"- Waiting for: {', '.join(w.get('roles', [])) or 'the candidate'}")
        return "\n".join(lines), steps
    if re.search(r"pending|approval|waiting|stuck|blocked|my queue", low):
        steps.append("pending_approvals")
        items = views.pending()
        if not items:
            return "Nothing is waiting for a human right now.", steps
        return "Waiting for a human decision:\n" + "\n".join(
            f"- **{a['candidate_name']}** - {a['agent']} - needs **{a['role']}**" for a in items), steps
    if re.search(r"flag|integrity|hold|risk|concern", low) and not re.search(r"policy|rule|guideline|say", low):
        steps.append("list_candidates")
        fl = [r for r in rows if r["flags"] or r["hold"]]
        if not fl:
            return "No candidate has an integrity flag or hold.", steps
        return "Needs attention:\n" + "\n".join(f"- {_line(r)} ({r['flags']} flag(s))" for r in fl), steps
    if re.search(r"ready|best|top|rank|shortlist|who should|hire|strongest", low):
        steps.append("list_candidates")
        ranked = sorted([r for r in rows if r["readiness"] is not None or r["match"] is not None],
                        key=lambda r: -(r["readiness"] or r["match"] or 0))[:5]
        if not ranked:
            return "No candidate has been scored yet.", steps
        return "Top candidates right now:\n" + "\n".join(f"{i + 1}. {_line(r)}" for i, r in enumerate(ranked)), steps
    if re.search(r"policy|rule|guideline|competenc|learn|framework|how does|what is|why", low):
        steps.append("search_knowledge")
        hits = rag.search(msg, k=2, source="docs")
        return "From our knowledge base:\n" + "\n".join(f"- **{h['title']}**: {h['text'][:260]}" for h in hits), steps
    steps.append("pool_overview")
    k = views.kpis()
    return (f"Here is the picture: **{k['candidates']}** candidates, **{k['completed']}** completed, "
            f"**{k['pending']}** waiting for a human, **{k['holds']}** on hold, average readiness "
            f"**{k['avg_readiness']}**.\nTry: 'Who is ready for hire?', 'Summarize Aisha', "
            "'Compare Priya and Sofia', 'What is waiting for approval?', 'What does our policy say about flags?'"), steps


def ask(message: str) -> dict:
    message = (message or "").strip()[:600]
    if not message:
        return {"answer": "Ask me about candidates, approvals, risks or policy.", "steps": [], "used_llm": False}
    if settings.agentic():
        final, trace = rt.react(
            0, _Agent(), f"A leader asks: {message}\nUse data tools to verify facts. "
            'Finish with {"answer": "short factual answer using **bold** and - bullets"}.',
            TOOLS)
        answer = rt.require_text(0, _Agent(), final, key="answer", limit=2499)
        return {"answer": answer, "steps": [t["action"] for t in trace if t.get("action")],
                "used_llm": True}
    if llm.available() and llm.enabled_for("ASK_TALON") and llm.single_shot():
        facts, steps = _rules(message)                    # tools run in code, the model words the answer
        out = llm.chat_json("ASK_TALON", "You are TALON, a talent copilot. Use ONLY the facts given. "
                            'Reply JSON {"answer": "short answer for a leader, **bold** names, - bullets"}',
                            f"Question: {message}\nFacts:\n{facts}", 400)
        ans = (out or {}).get("answer")
        if isinstance(ans, str) and 5 < len(ans) < 2500:
            return {"answer": ans, "steps": steps, "used_llm": True}
        return {"answer": facts, "steps": steps, "used_llm": False}
    if llm.available() and llm.enabled_for("ASK_TALON"):
        final, trace = rt.react(0, _Agent(), f"A leader asks: {message}\nUse tools to find facts, then finish "
                                f'with {{"answer": "short answer using **bold** and - bullets"}}. Never invent data.',
                                TOOLS, max_steps=4)
        ans = (final or {}).get("answer")
        if isinstance(ans, str) and 5 < len(ans) < 2500:
            return {"answer": ans, "steps": [f"{t.get('action')}({json.dumps(t.get('args'))})" for t in trace if t.get("action")],
                    "used_llm": True}
    ans, steps = _rules(message)
    return {"answer": ans, "steps": steps, "used_llm": False}
