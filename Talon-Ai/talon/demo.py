"""Isolated offline showcase, supervised by the main application's process."""
import argparse
import atexit
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading

_lock = threading.Lock()
_process = None
_url = None


def _stop():
    global _process, _url
    if _process is not None:
        if _process.poll() is None:
            _process.stdin.close()
            try:
                _process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _process.terminate()
                _process.wait(timeout=10)
        _process.stdout.close()
    _process, _url = None, None


def close():
    with _lock:
        _stop()


atexit.register(close)


def launch(mode="lite"):
    """Return the URL only once the separate showcase server is responsive."""
    global _process, _url
    if mode not in ("lite", "full"):
        raise ValueError("Demo workflow must be lite or full")
    with _lock:
        if _process is not None and _process.poll() is None:
            return {"url": _url, "offline_demo": True}
        _stop()
        env = dict(os.environ)
        for key in ("TALON_DATA", "TALON_DB", "TALON_KNOWLEDGE", "TALON_LLM_PROVIDER",
                    "TALON_CUSTOM_KEY", "GITHUB_TOKEN", "TALON_GITHUB_TOKEN"):
            env.pop(key, None)
        env.update(TALON_USE_LLM="off", TALON_MODE=mode, TALON_OFFLINE_DEMO="1")
        _process = subprocess.Popen(
            [sys.executable, "-m", "talon.demo", "--serve", "--mode", mode],
            cwd=str(Path(__file__).resolve().parent.parent), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8")
        process = _process
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
        try:
            line = ready.get(timeout=60)
            result = json.loads(line)
            if not isinstance(result.get("url"), str) or not result.get("offline_demo"):
                raise RuntimeError("Offline showcase did not report readiness")
            from urllib.request import urlopen
            with urlopen(result["url"] + "/api/state", timeout=5) as response:
                state = json.loads(response.read())
            if not state.get("offline_demo") or state["ai"]["provider"] != "none":
                raise RuntimeError("Offline showcase isolation check failed")
            _url = result["url"]
            return result
        except queue.Empty as exc:
            _stop()
            raise RuntimeError("Offline showcase did not start within 60 seconds.") from exc
        except (ValueError, RuntimeError, OSError) as exc:
            _stop()
            raise RuntimeError(f"Could not start the offline showcase: {exc}") from exc


def _serve(mode):
    with tempfile.TemporaryDirectory(prefix="talon-offline-demo-") as directory:
        knowledge = Path(directory) / "knowledge"
        shutil.copytree(Path(__file__).resolve().parent.parent / "knowledge", knowledge)
        os.environ.update(TALON_DATA=directory, TALON_DB=str(Path(directory) / "talon.db"),
                          TALON_KNOWLEDGE=str(knowledge), TALON_USE_LLM="off",
                          TALON_OFFLINE_DEMO="1", TALON_MODE=mode)
        from . import orchestrator, rag, samples, server, settings
        settings.get()
        settings.save({"execution_mode": "legacy", "provider": "none", "demo_pace": 0})
        orchestrator.init()
        rag.ensure_ready()
        samples.load_samples()
        httpd = server.make_server("127.0.0.1", 0)

        def supervise():
            sys.stdin.read()
            httpd.shutdown()

        threading.Thread(target=supervise, daemon=True).start()
        print(json.dumps({"url": f"http://127.0.0.1:{httpd.server_port}",
                          "offline_demo": True}), flush=True)
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", required=True)
    parser.add_argument("--mode", choices=("lite", "full"), default="lite")
    args = parser.parse_args()
    _serve(args.mode)
