"""Self-test (no browser, no AI model needed):   python run_tests.py
Uses a temporary data folder, so your real data is never touched."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

os.environ["TALON_DATA"] = tempfile.mkdtemp()
os.environ["TALON_USE_LLM"] = "off"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from talon import (copilot, db, llm, orchestrator, rag, samples, server, settings,  # noqa: E402
                   skills, views, workflow)
from talon.agents import AGENTS                                                    # noqa: E402
from talon.agents.apex import CODING_TASK                                          # noqa: E402
from talon.agents.titan import run_code_tests                                      # noqa: E402

settings.save({"demo_pace": 0})
orchestrator.init()
rag.ensure_ready()
ok = lambda m: print("  OK  " + m)                                                 # noqa: E731

assert skills.extract_skills("Java and JavaScript") == ["java", "javascript"]
assert run_code_tests(CODING_TASK["solution"])["score"] == 100.0
assert run_code_tests("while True: pass")["error"] == "TimeoutExpired"
ok("skills and the coding evaluator")

st = rag.stats()["by_source"]
assert st["skills"] >= 20 and st["docs"] >= 3, st
assert "hiring_policy" in rag.search("integrity flag hold hiring", k=1, source="docs")[0]["title"]
ok(f"RAG knowledge base {st}")

# ---- agentic loop with a scripted stand-in AI model ----
job_id = orchestrator.add_job("Data Analyst", "d", ["python", "sql", "excel", "statistics"], ["power bi"])
cid = orchestrator.add_candidate("Maria Lopez", "maria@example.com",
                                 (samples.config.SAMPLE_DIR / "resume_maria.txt").read_text(), job_id)


def fake(agent, system, user, max_tokens=300):
    if "Supervisor of a talent workflow" in system:
        return {"extra_review": False, "role": "HR", "reason": "none"}
    if "OBSERVATION" not in user and "search_resume" in system:
        return {"thought": "check", "action": "search_resume", "args": {"query": "python"}}
    return {"final": {"inferred_skills": ["python", "invented_skill"], "summary": "Model summary text."}}


llm.available = lambda: True
llm.chat_json = fake
res = AGENTS["ORIGIN"].run(orchestrator.get_candidate(cid), orchestrator.get_job(job_id))
assert res.data["inferred_by_ai_half_credit"] == ["python"], res.data        # invented skill dropped
trace = db.memory_get(cid, "ORIGIN", "trace")
assert trace[0]["action"] == "search_resume" and any("guardrail" in t for t in trace), trace
ok("agent tool loop + guardrail (invented skill dropped, shown in trace)")
llm.chat_json = lambda *a, **k: None                                          # model fails
res = AGENTS["ATHENA"].run(orchestrator.get_candidate(cid), orchestrator.get_job(job_id))
assert not res.used_llm and res.data["plan"]
llm.available = lambda: False
ok("fallback to rules when the model fails")

# ---- workflow, human STOP, policy ----
ids = samples.load_samples()["candidate_ids"]
rows = {r["name"]: r for r in views.pool()}
assert rows["Arjun Mehta"]["waiting"]["type"] == "approval"
assert rows["Maria Lopez"]["waiting"]["type"] == "candidate"
assert any(r["hold"] for r in rows.values()), "expected one candidate on policy HOLD"
ok("workflow stops for humans; policy rule forces HOLD on flagged candidate")
a = views.pending("Recruiter")[0]
orchestrator.decide(a["id"], True, "ok", "Recruiter")
workflow.run_blocking(a["candidate_id"])
assert orchestrator.get_candidate(a["candidate_id"])["stage"] != "ORIGIN"
ok("approval resumes the workflow")
ans = copilot.ask("Who is ready for hire?")
assert "Top candidates" in ans["answer"]
ok("Ask TALON answers from the data")

# ---- HTTP API ----
httpd = server.make_server("127.0.0.1", 8199)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
get = lambda p: json.loads(urllib.request.urlopen("http://127.0.0.1:8199" + p).read())   # noqa: E731
state = get("/api/state")
assert state["kpis"]["candidates"] >= 6
ass_id = next(r["id"] for r in state["pool"] if r["stage"] == "ASSESSMENT")
assert "answer" not in json.dumps(get(f"/api/candidates/{ass_id}/assessment"))
assert b"Candidate dossier" in urllib.request.urlopen(
    f"http://127.0.0.1:8199/api/candidates/{ids[0]}/dossier").read()
ok("web API (answer keys are never sent to the browser)")
print("\nALL CHECKS PASSED")
