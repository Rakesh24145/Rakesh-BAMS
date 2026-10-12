"""ORIGIN - Talent Discovery Agent: resume analysis, skill matching, ranking.
Rules compute the score. The LLM agent (if available) may use RAG to find extra
evidence for skills the keyword match missed - those get only HALF credit."""
from .. import agent_runtime as rt
from .. import db, skills
from ..tools import make_tools
from .base import AgentResult, BaseAgent


class Origin(BaseAgent):
    name = "ORIGIN"
    title = "Talent Discovery Agent"
    goal = "Find and rank the best-fit candidates, fast"
    approver_role = "Recruiter"

    def run(self, cand, job):
        found = skills.extract_skills(cand["resume_text"])
        years = skills.extract_years(cand["resume_text"])
        req, nice = job["required"], job["nice"]
        m_req = [s for s in req if s in found]
        m_nice = [s for s in nice if s in found]
        missing = [s for s in req if s not in found]

        # --- agentic part: look for evidence of missing skills with RAG --------
        inferred, llm_text = [], None
        task = (f"Job: {job['title']}. Skills matched by keywords: {m_req}. "
                f"Missing required skills: {missing}. For each missing skill, call "
                f"search_resume to check if the resume shows real evidence. Finish "
                f'with {{"inferred_skills": [skills with evidence], "summary": '
                f'"2 factual sentences"}}.')
        final, trace = rt.react(cand["id"], self, task, make_tools(cand, job))
        if final:
            claimed = [s for s in (final.get("inferred_skills") or []) if isinstance(s, str)]
            inferred = [s for s in claimed if s in missing]                # guardrail
            dropped = [s for s in claimed if s not in missing]
            if dropped:
                trace.append({"guardrail": f"Dropped skills that are not on the missing list: {dropped}"})
                rt._save(cand["id"], self, trace)
            llm_text = rt.clean_text(final.get("summary"))

        req_cov = (len(m_req) + 0.5 * len(inferred)) / len(req) if req else 1.0
        nice_cov = len(m_nice) / len(nice) if nice else 0.0
        score = round(70 * req_cov + 20 * nice_cov + min(years, 10), 1)

        db.memory_set(cand["id"], self.name, "score", score)
        peers = db.q(
            "SELECT m.candidate_id cid, m.value v FROM memory m "
            "JOIN candidates c ON c.id = m.candidate_id "
            "WHERE m.agent='ORIGIN' AND m.key='score' AND c.job_id=?", (job["id"],))
        ranked = sorted(peers, key=lambda r: -float(r["v"]))
        rank = [r["cid"] for r in ranked].index(cand["id"]) + 1
        still_missing = [s for s in missing if s not in inferred]
        fallback = (f"Match score {score}/100 (rank {rank} of {len(ranked)}). "
                    f"Matched required: {', '.join(m_req) or 'none'}. "
                    f"Missing: {', '.join(still_missing) or 'none'}.")
        text = (llm_text + " " + fallback) if llm_text else fallback
        data = {"skills_found": found, "years": years, "matched_required": m_req,
                "matched_nice": m_nice, "missing_required": still_missing,
                "inferred_by_ai_half_credit": inferred,
                "score": score, "rank": rank, "of": len(ranked)}
        db.memory_set(cand["id"], self.name, "skills", found)
        return AgentResult(text, data, True, self.approver_role, bool(llm_text))
