"""Web server (Python standard library only - nothing to install).
Serves the web app from /web and a JSON API under /api, plus a live event stream."""
import base64
import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import (config, copilot, db, demo, llm, observability, orchestrator as orch, rag, reports,
               resume_io, samples, settings, views, workflow)
from .agents import AGENTS


def _name_email(text: str):
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or "")
    nm = re.search(r"(?im)^\s*name\s*:\s*(.+)$", text or "")
    first = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
    name = nm.group(1).strip() if nm else (first if len(first) < 40 else "New candidate")
    return name, email.group(0) if email else ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):          # quiet console
        pass

    # ---------------- helpers ----------------
    def _send(self, code, body: bytes, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str).encode())

    def _body(self) -> dict:
        try:
            return json.loads(self._raw or b"{}")
        except Exception:
            return {}

    # ---------------- routing ----------------
    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        self._raw = self.rfile.read(n) if n else b""      # always consume the body (keep-alive)
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)
        try:
            if path.startswith("/api/"):
                return self._api(method, path[4:], qs)
            return self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:                       # never crash the server
            try:
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            except Exception:
                pass

    def _static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (config.WEB_DIR / rel).resolve()
        if not str(f).startswith(str(config.WEB_DIR.resolve())) or not f.is_file():
            return self._send(404, b"Not found", "text/plain")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") or "javascript" in ctype else ""))

    # ---------------- API ----------------
    def _api(self, method, p, qs):
        m = re.match
        if p == "/demo/offline" and method == "POST":
            if config.OFFLINE_DEMO:
                return self._json({"error": "You are already in the isolated offline showcase."}, 400)
            try:
                return self._json(demo.launch(orch.MODE))
            except RuntimeError as exc:
                observability.log(None, "DEMO", "run_error", str(exc))
                return self._json({"error": str(exc)}, 503)
        if p == "/state":
            return self._json({"kpis": views.kpis(), "pool": views.pool(), "ai": llm.status(),
                               "offline_demo": config.OFFLINE_DEMO,
                               "impact": views.impact(), "roles": orch.ROLES, "phases": views.phases(), "mode": orch.MODE,
                               "jobs": orch.list_jobs()})
        if p == "/events":
            return self._sse()
        if p == "/activity":
            return self._json(views.activity(int(qs.get("since", ["0"])[0]), 60))
        if p == "/approvals":
            return self._json(views.pending(qs.get("role", [None])[0]))
        if p == "/health":
            return self._json(views.health())
        if p == "/graph":
            counts = {}
            for r in views.pool():
                counts[r["stage"]] = counts.get(r["stage"], 0) + 1
            nodes = [{"id": i, "title": t, "type": ty, "count": counts.get(i, 0),
                      "goal": AGENTS[i].goal if i in AGENTS else "A person acts here"}
                     for i, t, ty in workflow.nodes()]
            return self._json({"nodes": nodes, "done": counts.get("DONE", 0),
                               "running": [c for c in [r["id"] for r in views.pool()] if workflow.is_running(c)]})
        if p == "/settings" and method == "GET":
            return self._json({"settings": settings.public(), "ai": llm.status()})
        if p == "/settings" and method == "POST":
            if config.OFFLINE_DEMO:
                return self._json({"error": "Offline showcase settings are fixed; configure AI in the main window."}, 400)
            settings.save(self._body())
            llm._state["ping_ts"] = 0
            rag.ensure_ready()
            return self._json({"settings": settings.public(), "ai": llm.status()})
        if p == "/settings/test":
            return self._json(llm.test())
        if p == "/settings/github-models":
            return self._json({"models": llm.list_github_models(), "error": llm.status()["last_error"]})
        if p == "/chat" and method == "POST":
            msg = self._body().get("message", "")
            observability.log(None, "ASK_TALON", "chat", msg)
            from .agent_runtime import AgentExecutionError
            try:
                return self._json(copilot.ask(msg))
            except AgentExecutionError as exc:
                observability.log(None, "ASK_TALON", "run_error", str(exc))
                return self._json({"error": str(exc)}, 503)
        if p == "/kb":
            return self._json(rag.stats() | {"files": sorted(f.name for f in config.KNOWLEDGE_DIR.glob("*") if f.is_file())})
        if p == "/kb/search" and method == "POST":
            b = self._body()
            src = b.get("source")
            return self._json(rag.search(b.get("q", ""), k=5, source=None if src in (None, "", "all") else src))
        if p == "/kb/reindex" and method == "POST":
            rag.index_static()
            return self._json(rag.stats())
        if p == "/kb/upload" and method == "POST":
            b = self._body()
            name = re.sub(r"[^\w.\-]", "_", b.get("filename", "note.txt"))
            if not name.lower().endswith((".txt", ".md")):
                name += ".txt"
            (config.KNOWLEDGE_DIR / name).write_text(base64.b64decode(b.get("data", "")).decode("utf-8", "ignore"), encoding="utf-8")
            rag.index_static()
            return self._json(rag.stats())
        if p == "/samples" and method == "POST":
            try:
                samples.start()
            except ValueError as exc:
                return self._json({"error": str(exc)}, 409)
            return self._json({"started": True})
        if p == "/reset" and method == "POST":
            try:
                samples.reset_portfolio()
            except ValueError as exc:
                return self._json({"error": str(exc)}, 409)
            return self._json({"ok": True})
        if p == "/jobs" and method == "POST":
            b = self._body()
            jid = orch.add_job(b["title"], b.get("description", ""), b.get("required", []), b.get("nice", []))
            return self._json({"id": jid})
        if p == "/skills":
            from . import skills
            return self._json(sorted(skills.SKILLS))
        if p == "/candidates" and method == "POST":
            b = self._body()
            if settings.agentic() and b.get("autopilot"):
                return self._json({"error": "Agentic mode requires human approvals; autopilot is disabled."}, 400)
            text = b.get("resume_text", "")
            if b.get("data"):
                text = resume_io.extract_text(b.get("filename", "resume.txt"), base64.b64decode(b["data"]))
            if len(text.strip()) < 30:
                return self._json({"error": "The resume has no readable text. Paste the text instead."}, 400)
            name, email = _name_email(text)
            name, email = b.get("name") or name, b.get("email") or email
            job_id = int(b.get("job_id") or orch.list_jobs()[0]["id"])
            cid = orch.add_candidate(name, email, text, job_id)
            workflow.start(cid, demo=bool(b.get("autopilot")))
            return self._json({"id": cid})
        r = m(r"^/candidates/(\d+)(/.*)?$", p)
        if r:
            return self._candidate(method, int(r.group(1)), r.group(2) or "", qs)
        r = m(r"^/approvals/(\d+)/decide$", p)
        if r and method == "POST":
            b = self._body()
            a = db.q1("SELECT candidate_id FROM approvals WHERE id=?", (int(r.group(1)),))
            if not a:
                return self._json({"error": "Approval not found"}, 404)
            orch.decide(int(r.group(1)), bool(b.get("approve")), b.get("comment", ""), b.get("by", "Reviewer"))
            workflow.start(a["candidate_id"])
            return self._json({"ok": True})
        return self._json({"error": "Unknown endpoint " + p}, 404)

    def _candidate(self, method, cid, sub, qs):
        if not orch.get_candidate(cid):
            return self._json({"error": "Candidate not found"}, 404)
        if sub == "" and method == "GET":
            return self._json(views.case_view(cid))
        if sub == "/run" and method == "POST":
            return self._json({"started": workflow.start(cid)})
        if sub == "/autopilot" and method == "POST":
            if settings.agentic():
                return self._json({"error": "Agentic mode requires human approvals; autopilot is disabled."}, 400)
            return self._json({"started": workflow.start(cid, demo=True)})
        if sub == "/platform-prompt":
            ag = qs.get("agent", [""])[0]
            return self._json({"agent": ag, "prompt": reports.platform_prompt(cid, ag)})
        if sub == "/platform-reply" and method == "POST":
            b = self._body()
            ag, text = b.get("agent", ""), (b.get("text") or "").strip()
            res = db.memory_get(cid, ag, "result")
            if not res or ag not in reports.PLATFORM_TASK or len(text) < 5:
                return self._json({"error": "Nothing to attach (run the agent first and paste a reply)."}, 400)
            try:
                parsed = json.loads(text[text.index("{"):text.rindex("}") + 1])
                text = parsed.get("summary", text) if isinstance(parsed, dict) else text
            except Exception:
                pass
            res["summary"], res["used_llm"] = str(text)[:900], True
            res["data"]["platform_reply"] = True
            db.memory_set(cid, ag, "result", res)
            observability.log(cid, ag, "platform_reply_pasted", "Reply from a platform agent attached")
            return self._json({"ok": True})
        if sub == "/dossier":
            return self._send(200, reports.dossier_html(cid).encode(), "text/html; charset=utf-8")
        if sub == "/draft":
            return self._json({"text": reports.draft_message(cid, qs.get("kind", ["feedback"])[0])})
        if sub == "/interview-guide":
            return self._json({"questions": reports.interview_guide(cid)})
        if sub == "/assessment" and method == "GET":
            a = db.memory_get(cid, "APEX", "assessment", {})
            qs_ = [{k: v for k, v in q.items() if k != "answer"} for q in a.get("questions", [])]
            coding = a.get("coding")
            return self._json({"questions": qs_, "coding": ({"prompt": coding["prompt"], "starter": coding["starter"]} if coding else None)})
        if sub == "/assessment" and method == "POST":
            b = self._body()
            orch.submit_assessment(cid, {k: int(v) for k, v in b.get("answers", {}).items()}, b.get("code", ""),
                                   float(b.get("seconds", 0)), bool(b.get("declared")))
            workflow.start(cid)
            return self._json({"ok": True})
        if sub == "/learning" and method == "POST":
            orch.submit_learning(cid, {k: float(v) for k, v in self._body().get("progress", {}).items()})
            workflow.start(cid)
            return self._json({"ok": True})
        if sub == "/simulate" and method == "POST":
            observability.log(cid, "ORCHESTRATOR", "demo_simulated_input", orch.get_candidate(cid)["stage"])
            orch.apply_human_payload(cid, orch.demo_payload(cid))
            workflow.start(cid)
            return self._json({"ok": True})
        return self._json({"error": "Unknown endpoint"}, 404)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = (db.q1("SELECT COALESCE(MAX(id),0) m FROM audit")["m"])
        beat = 0
        while True:
            rows = views.activity(last, 50)
            for r in rows:
                last = max(last, r["id"])
                self.wfile.write(b"data: " + json.dumps(r, default=str).encode() + b"\n\n")
            beat += 1
            if not rows and beat % 20 == 0:
                self.wfile.write(b": keep-alive\n\n")
            self.wfile.flush()
            time.sleep(0.5)


def make_server(host="127.0.0.1", port=8000):
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer((host, port), Handler)
