"""Tools an LLM agent may call. Read-only: tools can look things up but cannot
change scores or approvals."""
import json

from . import db, rag


def _fmt(hits: list) -> str:
    if not hits:
        return "No results."
    return "\n".join(f"[{h['source']}:{h['title']} score={h['score']}] {h['text'][:350]}"
                     for h in hits)


def make_tools(cand: dict, job: dict) -> dict:
    cid = cand["id"]

    def search_knowledge(query: str, source: str = None) -> str:
        src = source if source in ("skills", "catalog", "docs", "jobs") else None
        return _fmt(rag.search(str(query), k=3, source=src))

    def search_resume(query: str) -> str:
        return _fmt(rag.search(str(query), k=3, source="resume", ref=cid))

    def get_job_requirements() -> str:
        return json.dumps({"title": job["title"], "required": job["required"],
                           "nice_to_have": job["nice"]})

    def get_candidate_context() -> str:
        memory = db.memory_all(cid)
        return json.dumps({
            "name": cand["name"], "email": cand["email"], "stage": cand["stage"],
            "resume": cand["resume_text"],
            "evidence": {name: {k: v for k, v in values.items()
                                if k not in ("trace", "execution_error")}
                         for name, values in memory.items()},
        })

    def get_learning_resources(skills: list) -> str:
        from .agents.athena import retrieve_course
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            raise ValueError("skills must be a list of skill names")
        if any(s not in job["required"] + job["nice"] for s in skills):
            raise ValueError("Only this job's skills may be requested")
        return json.dumps([retrieve_course(s) for s in skills])

    return {
        "search_knowledge": (search_knowledge,
                             'search_knowledge(query, source) - look up the skills '
                             'framework, learning catalog or policy docs; source is '
                             'optional: skills|catalog|docs|jobs'),
        "search_resume": (search_resume,
                          "search_resume(query) - search THIS candidate's resume"),
        "get_job_requirements": (get_job_requirements,
                                 "get_job_requirements() - required skills of the job"),
        "get_candidate_context": (get_candidate_context,
                                  "get_candidate_context() - resume and previous stage evidence for THIS candidate"),
        "get_learning_resources": (get_learning_resources,
                                   "get_learning_resources(skills) - catalog courses for a list of job skills"),
    }
