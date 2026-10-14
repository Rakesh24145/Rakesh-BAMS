"""Self-test (no browser, no AI model needed):   python run_tests.py
Runs everything twice: in lite mode (4 agents) and in full mode (10 agents).
Uses a temporary data folder, so your real data is never touched."""
import subprocess
import sys

if len(sys.argv) < 2:
    code = 0
    for m in ("lite", "full"):
        print(f"\n===== {m.upper()} mode =====")
        code |= subprocess.call([sys.executable, __file__, m])
    print("\n===== AGENTIC contracts =====")
    from pathlib import Path
    code |= subprocess.call([sys.executable, str(Path(__file__).with_name("test_agentic.py"))])
    print("\nALL CHECKS PASSED" if code == 0 else "\nSOME CHECKS FAILED")
    sys.exit(code)

import http.server       # noqa: E402
import atexit            # noqa: E402
import json              # noqa: E402
import os                # noqa: E402
import tempfile          # noqa: E402
import threading         # noqa: E402
import urllib.request    # noqa: E402

MODE = sys.argv[1]
_test_data = tempfile.TemporaryDirectory()
atexit.register(_test_data.cleanup)
os.environ.update(TALON_DATA=_test_data.name, TALON_USE_LLM="off", TALON_MODE=MODE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from talon import (config, copilot, db, llm, orchestrator, rag, samples, server,     # noqa: E402
                   settings, skills, views, workflow)
from talon.agents import AGENTS                                                      # noqa: E402
from talon.agents.apex import CODING_TASK                                            # noqa: E402
from talon.agents.titan import run_code_tests                                        # noqa: E402

settings.save({"demo_pace": 0, "execution_mode": "legacy"})
orchestrator.init()
rag.ensure_ready()
assert orchestrator.MODE == MODE, orchestrator.MODE
ok = lambda m: print("  OK  " + m)                                                   # noqa: E731

assert skills.extract_skills("Java and JavaScript") == ["java", "javascript"]
assert skills.extract_years("1 year of work and 3 yrs") == 3
assert run_code_tests(CODING_TASK["solution"])["score"] == 100.0
assert run_code_tests("while True: pass")["error"] == "TimeoutExpired"
ok(f"skills and the coding evaluator; pipeline = {orchestrator.STEP_IDS}")

st = rag.stats()["by_source"]
assert st["skills"] >= 20 and st["docs"] >= 3, st
assert "hiring_policy" in rag.search("integrity flag hold hiring", k=1, source="docs")[0]["title"]
ok(f"RAG knowledge base {st}")

# ---- agentic loop with a scripted stand-in AI model ----
job_id = orchestrator.add_job("Data Analyst", "d", ["python", "sql", "excel", "statistics"], ["power bi"])
cid = orchestrator.add_candidate("Test Person", "test@example.com",
                                 (config.SAMPLE_DIR / "resume_maria.txt").read_text(), job_id)


def fake(agent, system, user, max_tokens=300):
    if "Supervisor of a talent workflow" in system:
        return {"extra_review": False, "role": "HR", "reason": "none"}
    if "OBSERVATION" not in user and "search_resume" in system:
        return {"thought": "check", "action": "search_resume", "args": {"query": "python"}}
    return {"final": {"inferred_skills": ["python", "invented_skill"], "summary": "Model summary text."}}


saved = (llm.available, llm.enabled_for, llm.single_shot, llm.chat_json)
llm.available, llm.enabled_for, llm.single_shot, llm.chat_json = (
    lambda: True, lambda a: True, lambda: False, fake)
res = AGENTS["ORIGIN"].run(orchestrator.get_candidate(cid), orchestrator.get_job(job_id))
assert res.data["inferred_by_ai_half_credit"] == ["python"], res.data           # invented skill dropped
trace = db.memory_get(cid, "ORIGIN", "trace")
assert trace[0]["action"] == "search_resume" and any("guardrail" in t for t in trace), trace
ok("agent tool loop + guardrail (invented skill dropped, shown in trace)")
llm.chat_json = lambda *a, **k: None                                            # the model fails
res = AGENTS["ATHENA"].run(orchestrator.get_candidate(cid), orchestrator.get_job(job_id))
assert not res.used_llm and res.data["plan"]
llm.available, llm.enabled_for, llm.single_shot, llm.chat_json = saved
ok("fallback to rules when the model fails")

# ---- custom API provider (e.g. Capgemini Generative Engine) with a fake server ----
seen = {"urls": [], "auth": set()}


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen["urls"].append(self.path)
        seen["auth"].add(self.headers.get("x-api-key"))
        text = json.dumps({"summary": "Platform agent says: solid fit on SQL and Excel.",
                           "inferred_skills": ["python", "bogus"]})
        out = json.dumps({"result": {"answer": "```json\n" + text + "\n```"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


os.environ.pop("TALON_USE_LLM", None)                  # allow a provider for this test
fs = http.server.ThreadingHTTPServer(("127.0.0.1", 9198), Fake)
threading.Thread(target=fs.serve_forever, daemon=True).start()
settings.save({"provider": "custom", "custom_url": "http://127.0.0.1:9198/agents/{{agent_id}}/chat",
               "custom_auth_header": "x-api-key", "custom_auth_value": "{{key}}", "custom_key": "SECRET-123",
               "custom_body": '{"agentId": "{{agent_id}}", "message": "{{system}}\\n\\n{{user}}"}',
               "custom_path": "result.answer", "custom_agent_ids": {"ORIGIN": "agent-origin-1"},
               "ai_call_budget": 150})
assert llm.available() and llm.single_shot()
r = llm.test()
assert r["ok"], r
res = AGENTS["ORIGIN"].run(orchestrator.get_candidate(cid), orchestrator.get_job(job_id))
assert res.used_llm and res.data["inferred_by_ai_half_credit"] == ["python"], res.data
assert "/agents/agent-origin-1/chat" in seen["urls"] and seen["auth"] == {"SECRET-123"}
assert db.memory_get(cid, "ORIGIN", "trace")[0]["action"] == "prefetch_evidence"
ok("custom API: URL/headers/body templates, per-agent ID, JSON inside a code block, guardrail")
assert not llm.enabled_for("SENTINEL") and llm.enabled_for("NORTHSTAR")
ok("only the chosen agents use the AI model (saves credit)")
used = llm.status()["calls"]
settings.save({"ai_call_budget": used})
assert llm.chat_json("ORIGIN", "s", "u") is None and "budget" in llm.status()["last_error"].lower()
settings.save({"ai_call_budget": 150, "custom_path": "wrong.path"})
assert not llm.test()["ok"] and "Raw reply" in llm.test()["message"]
settings.save({"custom_path": "result.answer"})
ok("AI call budget stops spending; wrong response path shows the raw reply")
settings.save({"provider": "none"})
os.environ["TALON_USE_LLM"] = "off"

# ---- workflow, human STOP, policy ----
ids = samples.load_samples()["candidate_ids"]
rows = {r["name"]: r for r in views.pool()}
assert rows["Arjun Mehta"]["waiting"]["type"] == "approval"
if MODE == "lite":
    assert rows["Maria Lopez"]["waiting"]["roles"] == ["Learning Team"]
    assert rows["Priya Nair"]["waiting"]["roles"] == ["HR"]
    assert rows["Aisha Khan"]["stage"] == "DONE" and rows["Aisha Khan"]["level"] == "Ready"
    assert rows["Daniel Okafor"]["hold"] and "experience" in rows["Daniel Okafor"]["decision"]
    ok("lite: workflow stops for 3 different humans; policy rule 6 puts Daniel on HOLD")
else:
    assert rows["Maria Lopez"]["waiting"]["type"] == "candidate"
    assert any(r["hold"] for r in rows.values()), "expected one candidate on policy HOLD"
    ok("full: workflow stops for humans and the candidate; integrity policy forces a HOLD")
a = views.pending("Recruiter")[0]
orchestrator.decide(a["id"], True, "ok", "Recruiter")
workflow.run_blocking(a["candidate_id"])
assert orchestrator.get_candidate(a["candidate_id"])["stage"] != "ORIGIN"
ok("approval resumes the workflow")
assert "Top candidates" in copilot.ask("Who is ready for hire?")["answer"]
ok("Ask TALON answers from the data")

# ---- HTTP API ----
httpd = server.make_server("127.0.0.1", 8199)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
get = lambda p: json.loads(urllib.request.urlopen("http://127.0.0.1:8199" + p).read())     # noqa: E731
post = lambda p, d: json.loads(urllib.request.urlopen(urllib.request.Request(               # noqa: E731
    "http://127.0.0.1:8199" + p, data=json.dumps(d).encode(),
    headers={"Content-Type": "application/json"})).read())
state = get("/api/state")
assert state["kpis"]["candidates"] >= 6 and state["mode"] == MODE
if MODE == "full":
    ass_id = next(r["id"] for r in state["pool"] if r["stage"] == "ASSESSMENT")
    assert "answer" not in json.dumps(get(f"/api/candidates/{ass_id}/assessment"))
done = next(r["id"] for r in state["pool"] if r["stage"] == "DONE")
assert b"Candidate dossier" in urllib.request.urlopen(f"http://127.0.0.1:8199/api/candidates/{done}/dossier").read()
pp = get(f"/api/candidates/{done}/platform-prompt?agent=NORTHSTAR")["prompt"]
assert "TASK:" in pp and "KNOWLEDGE:" in pp
post(f"/api/candidates/{done}/platform-reply", {"agent": "NORTHSTAR", "text": '```json\n{"summary": "Pasted platform reply."}\n```'})
assert any("Pasted platform reply." in a["summary"] for a in get(f"/api/candidates/{done}")["agents"])
ok("web API, dossier, and the manual bridge (copy prompt to a platform agent, paste its reply back)")
print(f"\n{MODE} OK")
