"""TALON ORCHESTRATOR - core workflow functions with human approval gates.
(In v2 the LangGraph graph in graph.py calls these functions; engine.py chooses.)

Each candidate has a `stage`. The orchestrator runs the agent for that stage.
If the agent asks for approval, the candidate WAITS (STOP) until a human decides.
Steps marked "human" need input from a person (candidate), not from an agent.
"""
import json

from . import db, observability, rag, supervisor
from .agents import AGENTS
from .agents.apex import CODING_TASK

PIPELINE = [
    ("ORIGIN", "agent"), ("GENESIS", "agent"), ("ATHENA", "agent"),
    ("LEARNING", "human"),                      # candidate logs course progress
    ("NOVA", "agent"), ("APEX", "agent"),
    ("ASSESSMENT", "human"),                    # candidate takes the assessment
    ("SENTINEL", "agent"), ("TITAN", "agent"), ("PRISM", "agent"),
    ("NORTHSTAR", "agent"), ("OMNIVIEW", "agent"),
]
STEP_TYPE = dict(PIPELINE)
STEP_IDS = [s for s, _ in PIPELINE]
TERMINAL = ("DONE", "REJECTED")
ROLES = ["Recruiter", "HR", "Learning Team", "Manager", "Assessment Owner",
         "Interviewer", "Hiring Manager", "Executive"]


def init() -> None:
    db.init_db()


# ------------------------------ jobs & candidates ---------------------------
def add_job(title, description, required, nice) -> int:
    jid = db.run("INSERT INTO jobs(title,description,required,nice,created) "
                 "VALUES (?,?,?,?,?)",
                 (title, description, json.dumps(required), json.dumps(nice), db.now()))
    try:                                   # RAG: make the job searchable
        rag.index_job(jid, title, description, required, nice)
    except Exception as exc:
        observability.log(None, "RAG", "index_error", repr(exc))
    return jid


def get_job(job_id: int) -> dict:
    j = db.q1("SELECT * FROM jobs WHERE id=?", (job_id,))
    j["required"] = json.loads(j["required"] or "[]")
    j["nice"] = json.loads(j["nice"] or "[]")
    return j


def list_jobs() -> list:
    return db.q("SELECT * FROM jobs ORDER BY id")


def add_candidate(name, email, resume_text, job_id) -> int:
    cid = db.run("INSERT INTO candidates(name,email,resume_text,job_id,stage,created) "
                 "VALUES (?,?,?,?,?,?)",
                 (name, email, resume_text, job_id, STEP_IDS[0], db.now()))
    observability.log(cid, "ORCHESTRATOR", "candidate_created", name)
    try:                                   # RAG: make the resume searchable
        rag.index_resume(cid, name, resume_text)
    except Exception as exc:
        observability.log(cid, "RAG", "index_error", repr(exc))
    return cid


def get_candidate(cid: int) -> dict:
    return db.q1("SELECT * FROM candidates WHERE id=?", (cid,))


def list_candidates() -> list:
    return db.q("SELECT id,name,email,job_id,stage FROM candidates ORDER BY id")


# ------------------------------ workflow core -------------------------------
def _set_stage(cid: int, stage: str) -> None:
    db.run("UPDATE candidates SET stage=? WHERE id=?", (stage, cid))
    observability.log(cid, "ORCHESTRATOR", "stage_changed", stage)


def _advance(cid: int) -> None:
    stage = get_candidate(cid)["stage"]
    i = STEP_IDS.index(stage)
    _set_stage(cid, STEP_IDS[i + 1] if i + 1 < len(STEP_IDS) else "DONE")


def maybe_skip(cid: int) -> bool:
    """Smart routing: if ATHENA found no skill gaps, skip LEARNING and NOVA."""
    if get_candidate(cid)["stage"] == "LEARNING" and \
            not db.memory_get(cid, "ATHENA", "plan", []):
        db.memory_set(cid, "NOVA", "completion_records",
                      {"completion_pct": 100.0, "hours_done": 0.0})
        observability.log(cid, "ORCHESTRATOR", "steps_skipped",
                          "No skill gaps: LEARNING and NOVA skipped")
        _set_stage(cid, "APEX")
        return True
    return False


def run_step(cid: int) -> dict:
    maybe_skip(cid)
    cand = get_candidate(cid)
    stage = cand["stage"]
    if stage in TERMINAL:
        return {"status": "finished", "stage": stage}
    pending = db.q1("SELECT id FROM approvals WHERE candidate_id=? AND status='pending'",
                    (cid,))
    if pending:
        return {"status": "waiting_approval", "approval_id": pending["id"]}
    if STEP_TYPE[stage] == "human":
        return {"status": "human_input_needed", "stage": stage}
    job = get_job(cand["job_id"])
    try:
        res = AGENTS[stage].run(cand, job)
    except Exception as exc:                      # keep the app alive, log for ATLAS
        observability.log(cid, stage, "run_error", repr(exc))
        return {"status": "error", "message": repr(exc)}
    db.memory_set(cid, stage, "result", {
        "summary": res.summary, "data": res.data, "used_llm": res.used_llm})
    observability.log(cid, stage, "run_ok", res.summary)
    if res.requires_approval:
        aid = db.run("INSERT INTO approvals(candidate_id,agent,role,summary,status,"
                     "created) VALUES (?,?,?,?,?,?)",
                     (cid, stage, res.approver_role, res.summary, "pending", db.now()))
        observability.log(cid, stage, "approval_requested", res.approver_role)
        extra = supervisor.extra_review(cid, stage, res, ROLES)
        if extra:                                   # the supervisor can only ADD review
            db.run("INSERT INTO approvals(candidate_id,agent,role,summary,status,"
                   "created) VALUES (?,?,?,?,?,?)",
                   (cid, stage, extra["role"], "Supervisor escalation: " + extra["reason"],
                    "pending", db.now()))
            observability.log(cid, "SUPERVISOR", "escalation",
                              f"{extra['role']}: {extra['reason']}")
        return {"status": "waiting_approval", "approval_id": aid}
    _advance(cid)
    return {"status": "advanced"}


def decide(approval_id: int, approve: bool, comment: str = "",
           decided_by: str = "") -> str:
    a = db.q1("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not a or a["status"] != "pending":
        raise ValueError("Approval not found or already decided")
    db.run("UPDATE approvals SET status=?, comment=?, decided=?, decided_by=? "
           "WHERE id=?", ("approved" if approve else "rejected", comment, db.now(),
                          decided_by, approval_id))
    cid = a["candidate_id"]
    observability.log(cid, a["agent"], "approval_approved" if approve
                      else "approval_rejected", f"{decided_by}: {comment}")
    if not approve:
        _set_stage(cid, "REJECTED")
        return "REJECTED"
    if db.q1("SELECT id FROM approvals WHERE candidate_id=? AND status='pending'", (cid,)):
        return get_candidate(cid)["stage"]         # another reviewer is still needed
    if a["agent"] == "NORTHSTAR":
        rec = db.memory_get(cid, "NORTHSTAR", "recommendation", {})
        db.memory_set(cid, "ORCHESTRATOR", "decision", {
            "decision": rec.get("hiring"), "deployment": rec.get("deployment"),
            "approved_by": decided_by, "at": db.now()})
    _advance(cid)
    return get_candidate(cid)["stage"]


def pending_approvals(role: str = None) -> list:
    sql = ("SELECT a.*, c.name candidate_name FROM approvals a "
           "JOIN candidates c ON c.id=a.candidate_id WHERE a.status='pending'")
    args: tuple = ()
    if role:
        sql += " AND a.role=?"
        args = (role,)
    return db.q(sql + " ORDER BY a.id", args)


# ------------------------------ human input steps ---------------------------
def submit_learning(cid: int, progress: dict) -> None:
    if get_candidate(cid)["stage"] != "LEARNING":
        raise ValueError("Candidate is not at the LEARNING step")
    db.memory_set(cid, "NOVA", "progress", progress)
    observability.log(cid, "NOVA", "human_input", "learning progress submitted")
    _advance(cid)


def submit_assessment(cid: int, answers: dict, code: str, seconds_total: float,
                      declared_external_help: bool = False) -> None:
    if get_candidate(cid)["stage"] != "ASSESSMENT":
        raise ValueError("Candidate is not at the ASSESSMENT step")
    assessment = db.memory_get(cid, "APEX", "assessment", {})
    db.memory_set(cid, "APEX", "submission", {
        "answers": answers, "code": code, "seconds_total": seconds_total,
        "n_questions": len(assessment.get("questions", [])),
        "declared_external_help": declared_external_help})
    observability.log(cid, "APEX", "human_input", "assessment submitted")
    _advance(cid)


# ------------------------------ demo helpers --------------------------------
def demo_payload(cid: int) -> dict:
    """Simulated candidate input (for demos/tests)."""
    stage = get_candidate(cid)["stage"]
    if stage == "LEARNING":
        plan = db.memory_get(cid, "ATHENA", "plan", [])
        pct = 40 if cid % 3 == 2 else 90
        return {"type": "learning", "progress": {p["course"]: pct for p in plan}}
    a = db.memory_get(cid, "APEX", "assessment", {})
    answers = {}
    for i, q in enumerate(a.get("questions", [])):
        wrong = (i + cid) % 4 == 0
        answers[q["id"]] = (q["answer"] + 1) % len(q["options"]) if wrong else q["answer"]
    code = (CODING_TASK["solution"] + f"# demo candidate {cid}\n") if a.get("coding") else ""
    n = len(a.get("questions", []))
    return {"type": "assessment", "answers": answers, "code": code,
            "seconds_total": 2 * n if cid % 3 == 0 else 25 * n, "declared": False}


def apply_human_payload(cid: int, payload: dict) -> None:
    if payload["type"] == "learning":
        submit_learning(cid, payload["progress"])
    else:
        submit_assessment(cid, payload["answers"], payload.get("code", ""),
                          payload["seconds_total"], payload.get("declared", False))


def demo_human_input(cid: int) -> None:
    observability.log(cid, "ORCHESTRATOR", "demo_simulated_input",
                      get_candidate(cid)["stage"])
    apply_human_payload(cid, demo_payload(cid))


def run_until_blocked(cid: int, demo: bool = False, max_steps: int = 60) -> dict:
    """Keep going until a human is needed. demo=True auto-approves everything."""
    last: dict = {}
    for _ in range(max_steps):
        stage = get_candidate(cid)["stage"]
        if stage in TERMINAL:
            return {"status": "finished", "stage": stage}
        last = run_step(cid)
        if last["status"] == "waiting_approval" and demo:
            decide(last["approval_id"], True, "Auto-approved (DEMO mode)",
                   "DEMO auto-approval")
        elif last["status"] == "human_input_needed" and demo:
            demo_human_input(cid)
        elif last["status"] in ("waiting_approval", "human_input_needed", "error"):
            return last
    return last
