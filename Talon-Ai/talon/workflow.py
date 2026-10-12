"""WORKFLOW RUNNER - runs a candidate's journey in the background, step by step,
and pauses (STOP) whenever a human is needed. Works like a small state graph:

    supervisor -> agent -> (extra review?) -> STOP for human -> supervisor -> ...

Progress is streamed to the web UI through the audit log (live activity)."""
import threading
import time

from . import db, observability, orchestrator as orch, settings, llm

_locks: dict = {}
_running: set = set()
_guard = threading.Lock()

# Used by the "Workflow map" page
NODES = [
    ("ORIGIN", "Talent discovery", "agent"), ("GENESIS", "Onboarding", "agent"),
    ("ATHENA", "Learning plan", "agent"), ("LEARNING", "Candidate learns", "human"),
    ("NOVA", "Progress", "agent"), ("APEX", "Assessment design", "agent"),
    ("ASSESSMENT", "Candidate test", "human"), ("SENTINEL", "Integrity", "agent"),
    ("TITAN", "Scoring", "agent"), ("PRISM", "Readiness", "agent"),
    ("NORTHSTAR", "Recommendation", "agent"), ("OMNIVIEW", "Executive report", "agent"),
]


def is_running(cid: int) -> bool:
    return cid in _running


def status(cid: int) -> dict:
    cand = orch.get_candidate(cid)
    stage = cand["stage"]
    out = {"stage": stage, "running": is_running(cid), "waiting": None}
    if stage in orch.TERMINAL:
        return out
    pend = db.q("SELECT id, role, agent FROM approvals WHERE candidate_id=? AND "
                "status='pending' ORDER BY id", (cid,))
    if pend:
        out["waiting"] = {"type": "approval", "roles": [p["role"] for p in pend],
                          "approval_ids": [p["id"] for p in pend], "agent": pend[0]["agent"]}
    elif orch.STEP_TYPE.get(stage) == "human":
        out["waiting"] = {"type": "candidate", "step": stage}
    return out


def _pace():
    if llm.available():
        return 0.2
    return float(settings.get().get("demo_pace", 0.8))


def _run(cid: int, demo: bool, stop_at: str = None) -> None:
    lock = _locks.setdefault(cid, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        _running.add(cid)
        for _ in range(80):
            orch.maybe_skip(cid)
            cand = orch.get_candidate(cid)
            stage = cand["stage"]
            if stage in orch.TERMINAL or (stop_at and stage == stop_at):
                break
            pend = db.q("SELECT id FROM approvals WHERE candidate_id=? AND status='pending'",
                        (cid,))
            if pend:
                if not demo:
                    break
                for p in pend:
                    orch.decide(p["id"], True, "Auto-approved (DEMO autopilot)",
                                "DEMO autopilot")
                continue
            if orch.STEP_TYPE[stage] == "human":
                if not demo:
                    break
                observability.log(cid, "ORCHESTRATOR", "demo_simulated_input", stage)
                orch.apply_human_payload(cid, orch.demo_payload(cid))
                continue
            observability.log(cid, stage, "agent_started", "")
            time.sleep(_pace())
            res = orch.run_step(cid)
            if res["status"] == "error":
                break
    except Exception as exc:                       # never kill the server thread
        observability.log(cid, "ORCHESTRATOR", "run_error", repr(exc))
    finally:
        _running.discard(cid)
        observability.log(cid, "ORCHESTRATOR", "case_paused", orch.get_candidate(cid)["stage"])
        lock.release()


def start(cid: int, demo: bool = False) -> bool:
    with _guard:
        if cid in _running:
            return False
        threading.Thread(target=_run, args=(cid, demo), daemon=True).start()
    return True


def run_blocking(cid: int, demo: bool = False, stop_at: str = None) -> None:
    """Same as start() but waits (used by tests and demo data)."""
    _run(cid, demo, stop_at)
