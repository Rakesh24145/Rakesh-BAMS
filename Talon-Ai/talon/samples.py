"""Demo data: 1 job + 6 sample candidates, in a state that looks good on screen."""
import threading

from . import config, orchestrator, settings, workflow

_loading = threading.Lock()


def reset_portfolio() -> None:
    if not _loading.acquire(blocking=False):
        raise ValueError("The sample portfolio is still loading. Wait for it to finish before resetting.")
    try:
        workflow.reset_portfolio()
    finally:
        _loading.release()


def start() -> None:
    if not _loading.acquire(blocking=False):
        raise ValueError("The sample portfolio is already loading.")
    if orchestrator.list_candidates():
        _loading.release()
        raise ValueError("Portfolio already exists. Reset portfolio first.")

    def work():
        try:
            _load_samples()
        except Exception as exc:
            from . import observability
            observability.log(None, "SAMPLES", "run_error", str(exc))
        finally:
            _loading.release()

    try:
        threading.Thread(target=work, daemon=True).start()
    except RuntimeError:
        _loading.release()
        raise


def _fields(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if ":" in line[:12]:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def load_samples(showcase: bool = True, wait: bool = True) -> dict:
    with _loading:
        return _load_samples(showcase, wait)


def _load_samples(showcase: bool = True, wait: bool = True) -> dict:
    jd = (config.SAMPLE_DIR / "job_data_analyst.txt").read_text(encoding="utf-8")
    job_id = orchestrator.add_job("Data Analyst", jd,
                                  ["python", "sql", "excel", "statistics"],
                                  ["power bi", "data visualization", "git"])
    ids = []
    for f in sorted(config.SAMPLE_DIR.glob("resume_*.txt")):
        text = f.read_text(encoding="utf-8")
        fl = _fields(text)
        ids.append(orchestrator.add_candidate(fl.get("name", f.stem), fl.get("email", ""),
                                              text, job_id))
    if showcase:                    # a mix on screen: finished, on hold, waiting for people
        if orchestrator.MODE == "lite":
            plan = {0: ("demo", None), 1: ("first_gate", None), 2: ("demo", None),
                    3: ("until", "ATHENA"), 4: ("until", "NORTHSTAR"), 5: ("demo", None)}
        else:
            plan = {0: ("demo", None), 1: ("first_gate", None), 2: ("until", "TITAN"),
                    3: ("until", "ASSESSMENT"), 4: ("demo", None), 5: ("demo", None)}

        def work(cid, kind, arg):
            if settings.agentic():
                workflow.run_blocking(cid, demo=False)
                return
            if kind == "demo":
                workflow.run_blocking(cid, demo=True)
            elif kind == "first_gate":
                workflow.run_blocking(cid, demo=False)
            else:                                  # run automatically up to a stage
                workflow.run_blocking(cid, demo=True, stop_at=arg)
                if arg != "ASSESSMENT":
                    workflow.run_blocking(cid, demo=False)      # that step waits for a human
        threads = [threading.Thread(target=work, args=(cid, *plan.get(i, ("demo", None))))
                   for i, cid in enumerate(ids)]
        for t in threads:                          # all candidates work in parallel
            t.start()
        if wait:
            for t in threads:
                t.join()
    return {"job_id": job_id, "candidate_ids": ids}
