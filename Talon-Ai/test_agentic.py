"""Offline agentic contract tests; all data and HTTP providers are local fixtures."""
import ast
import http.server
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import patch

_data = tempfile.TemporaryDirectory()
os.environ["TALON_DATA"] = _data.name
os.environ["TALON_MODE"] = "full"
for key in ("TALON_USE_LLM", "TALON_LLM_PROVIDER", "TALON_CUSTOM_KEY"):
    os.environ.pop(key, None)

from talon import agent_runtime as rt
from talon import config, copilot, db, demo, llm, orchestrator as orch, rag, samples, server, settings, workflow
from talon.agents import AGENTS
from talon.tools import make_tools


def scripted(agent, system, user, max_tokens=900):
    first = "OBSERVATION:" not in user
    tools = {
        "ORIGIN": ("search_resume", {"query": "required skills"}),
        "ATHENA": ("get_learning_resources", {}),
        "APEX": ("get_question_bank", {}),
        "NORTHSTAR": ("search_knowledge", {"query": "hiring policy", "source": "docs"}),
        "SUPERVISOR": ("get_review_evidence", {}),
        "ASK_TALON": ("pool_overview", {}),
        "GENESIS": ("get_stage_evidence", {}),
        "NOVA": ("get_stage_evidence", {}),
        "SENTINEL": ("get_stage_evidence", {}),
        "PRISM": ("get_stage_evidence", {}),
    }
    action, args = tools.get(agent, ("get_job_requirements", {}))
    if agent == "ATHENA":
        required = ast.literal_eval(re.search(r"Required gaps: (.*?)\. Optional gaps:", user).group(1))
        optional = ast.literal_eval(re.search(r"Optional gaps: (.*?)\. Use", user).group(1))
        ordered = list(reversed(required)) + optional[:1]
        args = {"skills": ordered}
    if first:
        return {"thought": "Verify stage evidence", "action": action, "args": args}
    final = {"summary": "Reviewed the available evidence; a human makes the final decision."}
    if agent == "ORIGIN":
        final.update(inferred_skills=[], skill_evidence={})
    elif agent == "ATHENA":
        final["ordered_skills"] = ordered
    elif agent == "APEX":
        bank = json.loads(user.rsplit("\nOBSERVATION: ", 1)[1].strip())
        selected = {}
        for q in reversed(bank):
            selected.setdefault(q["skill"], q["id"])
        final["question_ids"] = list(selected.values())
    elif agent in ("GENESIS", "NOVA", "SENTINEL", "PRISM"):
        final["review_required"] = False
    elif agent == "SUPERVISOR":
        final = {"extra_review": False, "role": "HR", "reason": "No additional review needed."}
    elif agent == "ASK_TALON":
        final = {"answer": "The verified pool overview contains the current candidate counts."}
    return {"final": final}


class AgenticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        orch.init()
        rag.ensure_ready()

    def setUp(self):
        settings.save({"execution_mode": "agentic", "provider": "none", "demo_pace": 0,
                       "agent_mode": "single", "ai_agents": [], "ai_call_budget": 10000})
        self.jid = orch.add_job("Analyst", "Required skills", ["python", "sql"], ["git"])
        self.cid = orch.add_candidate(
            "Fixture Candidate", f"fixture{db.now()}@example.test",
            "SQL analyst with 3 years of experience. " + "Built SQL reports. " * 15, self.jid)
        self.cand = orch.get_candidate(self.cid)
        self.job = orch.get_job(self.jid)

    def model(self):
        return patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True, chat_json=scripted)

    def test_agentic_defaults_override_legacy_ai_filters(self):
        self.assertEqual(settings.DEFAULTS["execution_mode"], "agentic")
        settings.save({"provider": "custom"})
        self.assertTrue(llm.enabled_for("GENESIS"))
        self.assertTrue(llm.enabled_for("ASK_TALON"))
        self.assertFalse(llm.single_shot())
        settings.save({"execution_mode": "legacy"})
        self.assertFalse(llm.enabled_for("GENESIS"))
        self.assertTrue(llm.single_shot())

    def test_unavailable_model_stops_without_success_or_approval(self):
        result = orch.run_step(self.cid)
        self.assertEqual(result["status"], "error")
        self.assertEqual(orch.get_candidate(self.cid)["stage"], "ORIGIN")
        self.assertIsNone(db.memory_get(self.cid, "ORIGIN", "result"))
        self.assertFalse(db.q("SELECT id FROM approvals WHERE candidate_id=?", (self.cid,)))
        self.assertEqual(workflow.status(self.cid)["waiting"]["type"], "error")
        self.assertFalse(llm.test()["ok"])
        with self.assertRaises(rt.AgentExecutionError):
            copilot.ask("Who is ready?")

    def test_failed_json_and_exhausted_loop_never_fall_back(self):
        for response in (None, {"action": "unknown", "args": {}}):
            with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True,
                                chat_json=lambda *a, **kw: response):
                with self.assertRaises(rt.AgentExecutionError):
                    AGENTS["ORIGIN"].run(self.cand, self.job)
            self.assertIn("error", db.memory_get(self.cid, "ORIGIN", "trace")[-1])

    def test_invalid_summary_and_unsupported_inference_stop(self):
        for final in ({"summary": "", "inferred_skills": [], "skill_evidence": {}},
                      {"summary": "Valid length summary.", "inferred_skills": ["python"],
                       "skill_evidence": {"python": "invented resume quote"}}):
            def invalid(agent, system, user, max_tokens=900):
                if "OBSERVATION:" not in user:
                    return {"action": "search_resume", "args": {"query": "python"}}
                return {"final": final}
            with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True, chat_json=invalid):
                self.assertEqual(orch.run_step(self.cid)["status"], "error")
            self.assertIsNone(db.memory_get(self.cid, "ORIGIN", "result"))

    def test_repair_unknown_tool_and_last_call_can_finish(self):
        outputs = iter([
            {"action": "bad", "args": {}},
            {"action": "get_job_requirements", "args": {}},
            {"final": {"summary": "Recovered using verified job requirements."}},
        ])
        with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True,
                            chat_json=lambda *a, **kw: next(outputs)):
            final, trace = rt.react(self.cid, AGENTS["OMNIVIEW"], "Check evidence",
                                    make_tools(self.cand, self.job), max_steps=2)
        self.assertIn("Recovered", final["summary"])
        self.assertEqual(len(trace), 3)

    def test_all_ten_agents_pause_for_humans_then_finish(self):
        visited = []
        with self.model():
            for _ in range(40):
                stage = orch.get_candidate(self.cid)["stage"]
                if stage == "DONE":
                    break
                pending = db.q("SELECT id FROM approvals WHERE candidate_id=? AND status='pending'",
                               (self.cid,))
                if pending:
                    for approval in pending:
                        orch.decide(approval["id"], True, "Fixture review", "Test reviewer")
                elif orch.STEP_TYPE[stage] == "human":
                    orch.apply_human_payload(self.cid, orch.demo_payload(self.cid))
                else:
                    visited.append(stage)
                    result = orch.run_step(self.cid)
                    self.assertNotEqual(result["status"], "error", result)
                    saved = db.memory_get(self.cid, stage, "result")
                    self.assertTrue(saved["used_llm"], stage)
                    self.assertTrue(any(t.get("action") for t in db.memory_get(self.cid, stage, "trace")))
            self.assertEqual(orch.get_candidate(self.cid)["stage"], "DONE")
            self.assertEqual(set(visited), set(AGENTS))
            self.assertTrue(copilot.ask("How many candidates?")["used_llm"])
        assessment = db.memory_get(self.cid, "APEX", "assessment")
        self.assertEqual(len(assessment["questions"]), 2)
        plan = db.memory_get(self.cid, "ATHENA", "plan")
        self.assertEqual([p["skill"] for p in plan], ["python", "git"])

    def test_model_directs_learning_order_and_no_gap_stage_still_uses_ai(self):
        job = {**self.job, "required": ["excel", "python"], "nice": []}
        with self.model():
            result = AGENTS["ATHENA"].run(self.cand, job)
            self.assertEqual([p["skill"] for p in result.data["plan"]], ["python", "excel"])
            result = AGENTS["ATHENA"].run(self.cand, {**job, "required": [], "nice": []})
            self.assertEqual(result.data["plan"], [])
            self.assertTrue(result.used_llm)

    def test_invalid_plan_and_assessment_do_not_persist(self):
        for name, override in (("ATHENA", {"ordered_skills": ["invented"]}),
                               ("APEX", {"question_ids": ["invented"]})):
            def invalid(agent, system, user, max_tokens=900):
                out = scripted(agent, system, user, max_tokens)
                if "final" in out:
                    out["final"].update(override)
                return out
            with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True, chat_json=invalid):
                with self.assertRaises(rt.AgentExecutionError):
                    AGENTS[name].run(self.cand, self.job)
            self.assertIsNone(db.memory_get(self.cid, name, "plan" if name == "ATHENA" else "assessment"))

    def test_ai_can_add_review_but_never_remove_mandatory_review(self):
        def add_review(agent, system, user, max_tokens=900):
            out = scripted(agent, system, user, max_tokens)
            if agent == "GENESIS" and "final" in out:
                out["final"]["review_required"] = True
            return out
        with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True, chat_json=add_review):
            self.assertTrue(AGENTS["GENESIS"].run(self.cand, self.job).requires_approval)
        with self.model():
            flagged = AGENTS["GENESIS"].run({**self.cand, "email": "invalid"}, self.job)
            self.assertTrue(flagged.requires_approval)
            db.memory_set(self.cid, "ORIGIN", "result", {"data": {"score": 100, "years": 3}})
            db.memory_set(self.cid, "PRISM", "readiness", {"score": 90, "level": "Ready"})
            db.memory_set(self.cid, "SENTINEL", "compliance_log", {"violations": ["Fixture flag"]})
            self.assertTrue(AGENTS["NORTHSTAR"].run(self.cand, self.job).data["hiring"].startswith("HOLD"))

    def test_retry_clears_persistent_error_only_after_success(self):
        self.assertEqual(orch.run_step(self.cid)["status"], "error")
        with self.model():
            self.assertEqual(orch.run_step(self.cid)["status"], "waiting_approval")
        self.assertIsNone(db.memory_get(self.cid, "ORIGIN", "execution_error"))
        self.assertEqual(workflow.status(self.cid)["waiting"]["type"], "approval")

    def test_supervisor_failure_cannot_create_partial_approvals(self):
        def invalid(agent, system, user, max_tokens=900):
            if agent == "SUPERVISOR":
                return None
            return scripted(agent, system, user, max_tokens)
        with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True, chat_json=invalid):
            self.assertEqual(orch.run_step(self.cid)["status"], "error")
        self.assertFalse(db.q("SELECT id FROM approvals WHERE candidate_id=?", (self.cid,)))
        self.assertIsNone(db.memory_get(self.cid, "ORIGIN", "result"))
        self.assertEqual(orch.get_candidate(self.cid)["stage"], "ORIGIN")

    def test_required_tool_cannot_be_bypassed_by_early_final(self):
        outputs = iter([
            {"final": {"summary": "Unsupported early answer."}},
            {"action": "search_resume", "args": {"query": "python"}},
            {"final": {"summary": "Now verified.", "inferred_skills": [], "skill_evidence": {}}},
        ])
        with patch.multiple(llm, available=lambda: True, enabled_for=lambda a: True,
                            chat_json=lambda *a, **kw: next(outputs)):
            result = AGENTS["ORIGIN"].run(self.cand, self.job)
        self.assertTrue(result.used_llm)
        self.assertIn("error", db.memory_get(self.cid, "ORIGIN", "trace")[0])

    def test_autopilot_is_disabled(self):
        with self.assertRaises(ValueError):
            workflow.start(self.cid, demo=True)
        with self.assertRaises(ValueError):
            workflow.run_blocking(self.cid, demo=True)

    def test_http_errors_are_not_success_shaped(self):
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_port}/api"
        try:
            graph = json.loads(urllib.request.urlopen(base + "/graph").read())
            self.assertEqual(len(graph["nodes"]), len(orch.PIPELINE))
            for path, body, code in (
                ("/chat", {"message": "Who is ready?"}, 503),
                (f"/candidates/{self.cid}/autopilot", {}, 400),
            ):
                request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                                 headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    urllib.request.urlopen(request)
                self.assertEqual(failure.exception.code, code)
                self.assertIn("error", json.loads(failure.exception.read()))
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_custom_http_provider_repeated_tool_protocol_and_budget(self):
        seen = []

        class Provider(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(body)
                content = scripted("ORIGIN", body["system"], body["user"])
                payload = json.dumps({"answer": json.dumps(content)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            settings.save({"provider": "custom", "custom_url": f"http://127.0.0.1:{httpd.server_port}",
                           "custom_key": "local-fixture", "custom_auth_value": "{{key}}",
                           "custom_body": '{"system": "{{system}}", "user": "{{user}}"}',
                           "custom_path": "answer"})
            self.assertTrue(AGENTS["ORIGIN"].run(self.cand, self.job).used_llm)
            self.assertEqual(len(seen), 2)
            self.assertIn("OBSERVATION:", seen[1]["user"])
            settings.save({"ai_call_budget": llm.status()["calls"]})
            with self.assertRaisesRegex(rt.AgentExecutionError, "budget"):
                AGENTS["ORIGIN"].run(self.cand, self.job)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_ollama_checks_selected_model_without_keys(self):
        settings.save({"provider": "ollama", "ollama_model": "qwen2.5:3b", "embed_model": ""})
        for models, expected in (([], False), ([{"name": "qwen2.5:3b"}], True)):
            llm._state["ping_ts"] = 0
            response = BytesIO(json.dumps({"models": models}).encode())
            with patch("urllib.request.urlopen", return_value=response):
                self.assertEqual(llm.available(), expected)
                if not expected:
                    self.assertIn("ollama pull qwen2.5:3b", llm._state["last_error"])
                    # Cached failures must retain the setup instruction.
                    llm._state["last_error"] = ""
                    self.assertFalse(llm.available())
                    self.assertIn("ollama pull", llm._state["last_error"])
        self.assertFalse(llm.embed_available())

    def test_ollama_chat_uses_local_json_endpoint_and_logs_usage(self):
        settings.save({"provider": "ollama", "ollama_model": "qwen2.5:3b"})
        payload = {"response": '{"ok": true}', "prompt_eval_count": 12, "eval_count": 4}
        with patch.object(llm, "available", return_value=True), patch.object(
                llm, "_post", return_value=payload) as post:
            self.assertEqual(llm.chat_json("TEST", "JSON only", "Ready"), {"ok": True})
        args, kwargs = post.call_args
        self.assertEqual(args[0], settings.get()["ollama_url"] + "/api/generate")
        self.assertEqual(args[1]["format"], "json")
        self.assertNotIn("headers", kwargs)
        row = db.q1("SELECT * FROM ledger ORDER BY id DESC LIMIT 1")
        self.assertEqual(row["prompt_tokens"], 12)
        self.assertEqual(row["completion_tokens"], 4)

    def test_ollama_target_change_invalidates_cached_availability(self):
        settings.save({"provider": "ollama", "ollama_model": "qwen2.5:3b"})
        llm._state.update(ping_ts=0)
        with patch("urllib.request.urlopen", return_value=BytesIO(
                b'{"models": [{"name": "qwen2.5:3b"}]}')):
            self.assertTrue(llm.available())
        settings.save({"ollama_model": "missing:latest"})
        with patch("urllib.request.urlopen", return_value=BytesIO(
                b'{"models": [{"name": "qwen2.5:3b"}]}')) as get:
            self.assertFalse(llm.available())
            get.assert_called_once()

    def test_openai_request_is_explicitly_non_streaming(self):
        settings.save({"provider": "openai", "openai_key": "fixture-secret",
                       "openai_base": "https://example.test/v1", "openai_model": "fixture-model"})
        response = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        with patch.object(llm, "_post", return_value=response) as post:
            self.assertEqual(llm.chat_json("TEST", "JSON only", "Ready"), {"ok": True})
        args = post.call_args.args
        self.assertFalse(args[1]["stream"])
        self.assertNotIn("stream_options", args[1])
        self.assertEqual(args[0], "https://example.test/v1/chat/completions")

    def test_wrapped_gateway_error_retains_details_and_redacts_key(self):
        settings.save({"provider": "openai", "openai_key": "fixture-secret"})
        message = ("Gateway upstream error: " + "x" * 220 +
                   " The 'stream_options' parameter is not supported. fixture-secret")
        error = urllib.error.HTTPError("https://example.test", 500, "Gateway error", {},
                                       BytesIO(json.dumps({"message": message}).encode()))
        with patch.object(llm, "_post", side_effect=error) as post:
            self.assertIsNone(llm.chat_json("TEST", "JSON only", "Ready"))
        post.assert_called_once()
        self.assertIn("stream_options", llm._state["last_error"])
        self.assertIn("not supported", llm._state["last_error"])
        self.assertNotIn("fixture-secret", llm._state["last_error"])
        self.assertIn("[REDACTED]", llm._state["last_error"])

    def test_offline_showcase_restores_lite_demo_without_touching_live_state(self):
        settings.save({"provider": "openai", "openai_key": "live-fixture-secret"})
        before_settings = settings.get()
        before_candidates = orch.list_candidates()
        before_calls = db.q1("SELECT COUNT(*) n FROM ledger")["n"]
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            result = demo.launch("lite")
            request = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_port}/api/demo/offline",
                data=b"{}", headers={"Content-Type": "application/json"})
            self.assertEqual(json.loads(urllib.request.urlopen(request, timeout=60).read()), result)
            state = json.loads(urllib.request.urlopen(result["url"] + "/api/state").read())
            self.assertTrue(state["offline_demo"])
            self.assertEqual(state["mode"], "lite")
            self.assertEqual(state["kpis"]["candidates"], 6)
            self.assertGreater(state["kpis"]["completed"], 0)
            self.assertGreater(state["kpis"]["pending"], 0)
            self.assertGreater(state["kpis"]["holds"], 0)
            self.assertEqual(state["ai"]["provider"], "none")
            self.assertEqual(state["ai"]["execution_mode"], "legacy")
            self.assertEqual(state["ai"]["calls"], 0)
            rows = {r["name"]: r for r in state["pool"]}
            self.assertEqual(rows["Aisha Khan"]["stage"], "DONE")
            self.assertEqual(rows["Maria Lopez"]["waiting"]["roles"], ["Learning Team"])
            self.assertEqual(rows["Priya Nair"]["waiting"]["roles"], ["HR"])
            self.assertTrue(rows["Daniel Okafor"]["hold"])
            change = urllib.request.Request(result["url"] + "/api/settings",
                                             data=b'{"provider":"openai"}',
                                             headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(change)
            self.assertEqual(failure.exception.code, 400)
            self.assertEqual(settings.get(), before_settings)
            self.assertEqual(orch.list_candidates(), before_candidates)
            self.assertEqual(db.q1("SELECT COUNT(*) n FROM ledger")["n"], before_calls)
            self.assertFalse(config.OFFLINE_DEMO)
        finally:
            httpd.shutdown()
            httpd.server_close()
            process = demo._process
            demo.close()
            if process is not None:
                self.assertIsNotNone(process.poll())

    def test_offline_showcase_full_mode_has_original_human_gates(self):
        try:
            result = demo.launch("full")
            state = json.loads(urllib.request.urlopen(result["url"] + "/api/state").read())
            self.assertEqual(state["mode"], "full")
            self.assertEqual(state["kpis"]["candidates"], 6)
            self.assertGreater(state["kpis"]["completed"], 0)
            self.assertGreater(state["kpis"]["pending"], 0)
            self.assertTrue(any(r["waiting"] and r["waiting"]["type"] == "candidate"
                                for r in state["pool"]))
            self.assertEqual(state["ai"]["calls"], 0)
        finally:
            demo.close()

    def test_reset_portfolio_preserves_connections_usage_and_static_knowledge(self):
        settings.save({"provider": "openai", "openai_key": "reset-fixture-secret",
                       "openai_base": "https://example.test/v1"})
        before_settings = settings._path().read_bytes()
        db.memory_set(self.cid, "ORIGIN", "execution_error", {"message": "Fixture"})
        db.run("INSERT INTO audit(ts,agent,event) VALUES (?,?,?)", (db.now(), "TEST", "run_error"))
        old_audit = db.q1("SELECT MAX(id) n FROM audit")["n"]
        db.run("INSERT INTO ledger(agent,prompt_tokens,completion_tokens) VALUES (?,?,?)", ("TEST", 1, 1))
        usage = db.q1("SELECT COUNT(*) n FROM ledger")["n"]
        static = db.q("SELECT id FROM chunks WHERE source NOT IN ('resume','jobs') ORDER BY id")
        samples.reset_portfolio()
        self.assertEqual(settings._path().read_bytes(), before_settings)
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM ledger")["n"], usage)
        self.assertEqual(db.q("SELECT id FROM chunks WHERE source NOT IN ('resume','jobs') ORDER BY id"), static)
        for table in ("candidates", "jobs", "memory", "approvals", "audit"):
            self.assertEqual(db.q1(f"SELECT COUNT(*) n FROM {table}")["n"], 0)
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM chunks WHERE source IN ('resume','jobs')")["n"], 0)
        settings.save({"execution_mode": "legacy", "provider": "none"})
        result = samples.load_samples()
        self.assertEqual(len(result["candidate_ids"]), 6)
        self.assertGreater(db.q1("SELECT MAX(id) n FROM audit")["n"], old_audit)
        self.assertTrue(config.DB_PATH.is_file())

    def test_reset_api_reports_active_work_and_then_clears_portfolio(self):
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{httpd.server_port}/api/reset"
        def reset_request():
            return urllib.request.urlopen(urllib.request.Request(
                url, data=b"{}", headers={"Content-Type": "application/json"}))
        try:
            workflow._running.add(self.cid)
            try:
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    reset_request()
                self.assertEqual(failure.exception.code, 409)
                self.assertIn("still working", json.loads(failure.exception.read())["error"])
            finally:
                workflow._running.discard(self.cid)
            samples._loading.acquire()
            try:
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    reset_request()
                self.assertEqual(failure.exception.code, 409)
            finally:
                samples._loading.release()
            self.assertIsNotNone(orch.get_candidate(self.cid))
            with reset_request() as response:
                self.assertEqual(json.loads(response.read()), {"ok": True})
            self.assertEqual(orch.list_candidates(), [])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        _data.cleanup()
