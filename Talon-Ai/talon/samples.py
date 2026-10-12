"""Demo data: 1 job + 6 sample candidates, in a state that looks good on screen."""
import threading

from . import config, orchestrator, workflow


def _fields(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if ":" in line[:12]:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def load_samples(showcase: bool = True, wait: bool = True) -> dict:
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
        plan = {0: ("demo", None), 1: ("first_gate", None), 2: ("until", "TITAN"),
                3: ("until", "ASSESSMENT"), 4: ("demo", None), 5: ("demo", None)}

        def work(cid, kind, arg):
            if kind == "demo":
                workflow.run_blocking(cid, demo=True)
            elif kind == "first_gate":
                workflow.run_blocking(cid, demo=False)
            else:                                  # run automatically up to a stage
                workflow.run_blocking(cid, demo=True, stop_at=arg)
                if arg == "TITAN":
                    workflow.run_blocking(cid, demo=False)      # TITAN waits for a human
        threads = [threading.Thread(target=work, args=(cid, *plan.get(i, ("demo", None))))
                   for i, cid in enumerate(ids)]
        for t in threads:                          # all candidates work in parallel
            t.start()
        if wait:
            for t in threads:
                t.join()
    return {"job_id": job_id, "candidate_ids": ids}
