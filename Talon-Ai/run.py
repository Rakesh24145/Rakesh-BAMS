"""Start TALON Studio:   python run.py      (then open http://localhost:8000)"""
import sys
import threading
import webbrowser

from talon import orchestrator, rag, server

PORT = 8000
for _a in sys.argv[1:]:
    if _a.isdigit():
        PORT = int(_a)

orchestrator.init()
rag.ensure_ready()
httpd = None
for p in range(PORT, PORT + 10):                 # use the next free port if busy
    try:
        httpd = server.make_server("127.0.0.1", p)
        PORT = p
        break
    except OSError:
        continue
if httpd is None:
    sys.exit("No free port found between %d and %d" % (PORT, PORT + 9))
url = f"http://localhost:{PORT}"
print(f"\n  TALON Studio is running at {url}\n  Press Ctrl+C to stop.\n")
if "--no-browser" not in sys.argv:
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\nStopped.")
