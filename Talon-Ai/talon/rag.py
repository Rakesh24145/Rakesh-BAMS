"""RAG: a small local vector store inside SQLite.

* Chunks of text (skills framework, learning catalog, policy documents, job
  descriptions, resumes) are turned into vectors and saved in the `chunks` table.
* search() embeds the question and returns the most similar chunks.
* Embeddings: Ollama `nomic-embed-text` if available, otherwise a built-in
  hashing embedder (keyword-style, works offline with nothing installed).
"""
import hashlib
import json
import re

from . import config, db, llm
import math
from . import skills as sk

DIM = 256


def _norm(v: list) -> list:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def hash_embed(text: str) -> list:
    v = [0.0] * DIM
    toks = re.findall(r"[a-z0-9+#]+", text.lower())
    for f in toks + [a + "_" + b for a, b in zip(toks, toks[1:])]:
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 20) & 1 else -1.0
    return _norm(v)


def current_embedder() -> str:
    return "ollama" if llm.embed_available() else "hash256"


def embed_texts(texts: list, embedder: str):
    """Returns (list of numpy vectors, embedder actually used)."""
    if embedder == "ollama":
        out = []
        for i in range(0, len(texts), 32):
            part = llm.embed(texts[i:i + 32])
            if part is None:
                out = None
                break
            out += part
        if out is not None:
            return [_norm([float(x) for x in v]) for v in out], embedder
    return [hash_embed(t) for t in texts], "hash256"


def chunk_text(text: str, size: int = 500) -> list:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 <= size:
            cur = (cur + "\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            while len(p) > size:                 # very long paragraph
                chunks.append(p[:size])
                p = p[size:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def add_chunks(source: str, ref: str, title: str, texts: list) -> None:
    if not texts:
        return
    vecs, used = embed_texts(texts, current_embedder())
    with db.conn() as c:
        for t, v in zip(texts, vecs):
            c.execute("INSERT INTO chunks(source,ref,title,text,vec,embedder) "
                      "VALUES (?,?,?,?,?,?)",
                      (source, str(ref), title, t,
                       json.dumps([round(float(x), 5) for x in v]), used))


def _delete(source: str, ref: str = None) -> None:
    if ref is None:
        db.run("DELETE FROM chunks WHERE source=?", (source,))
    else:
        db.run("DELETE FROM chunks WHERE source=? AND ref=?", (source, str(ref)))


def reindex_all(embedder: str) -> None:
    rows = db.q("SELECT id, text FROM chunks")
    if not rows:
        return
    vecs, used = embed_texts([r["text"] for r in rows], embedder)
    with db.conn() as c:
        for r, v in zip(rows, vecs):
            c.execute("UPDATE chunks SET vec=?, embedder=? WHERE id=?",
                      (json.dumps([round(float(x), 5) for x in v]), used, r["id"]))


def _ensure_consistent() -> None:
    cur = current_embedder()
    if any(r["e"] != cur for r in db.q("SELECT DISTINCT embedder e FROM chunks")):
        reindex_all(cur)


# ----------------------------- what gets indexed ---------------------------
def index_static() -> None:
    """Skills framework + learning catalog + every .txt/.md in /knowledge."""
    for s in ("skills", "catalog", "docs"):
        _delete(s)
    add_chunks("skills", "framework", "skills framework", [
        f"{name} (competency category: {sk.CATEGORY.get(name, 'General')}). "
        f"Also written as: {', '.join(words)}." for name, words in sk.SKILLS.items()])
    add_chunks("catalog", "catalog", "learning catalog", [
        f"Learning resource for {name}: {title}. Estimated {hours} hours."
        for name, (title, hours) in sk.CATALOG.items()])
    folder = config.KNOWLEDGE_DIR
    if folder.exists():
        for f in sorted(list(folder.glob("*.txt")) + list(folder.glob("*.md"))):
            add_chunks("docs", f.name, f.name,
                       chunk_text(f.read_text(encoding="utf-8", errors="ignore")))


def index_job(job_id: int, title: str, description: str, required: list, nice: list):
    _delete("jobs", job_id)
    text = f"{title}\n\n{description}\n\nRequired skills: {', '.join(required)}. " \
           f"Nice to have: {', '.join(nice)}."
    add_chunks("jobs", job_id, title, chunk_text(text))


def index_resume(cid: int, name: str, text: str) -> None:
    _delete("resume", cid)
    add_chunks("resume", cid, f"resume of {name}", chunk_text(text, 400))


def ensure_ready() -> None:
    if not db.q1("SELECT 1 FROM chunks WHERE source='skills' LIMIT 1"):
        index_static()


def stats() -> dict:
    rows = db.q("SELECT source, COUNT(*) n FROM chunks GROUP BY source")
    emb = db.q("SELECT DISTINCT embedder e FROM chunks")
    return {"by_source": {r["source"]: r["n"] for r in rows},
            "embedder": ", ".join(r["e"] for r in emb) or "(empty)"}


# ----------------------------------- search --------------------------------
def search(query: str, k: int = 4, source=None, ref=None) -> list:
    _ensure_consistent()
    sql, args = "SELECT * FROM chunks WHERE 1=1", []
    if source:
        srcs = [source] if isinstance(source, str) else list(source)
        sql += " AND source IN (%s)" % ",".join("?" * len(srcs))
        args += srcs
    if ref is not None:
        sql += " AND ref=?"
        args.append(str(ref))
    rows = db.q(sql, tuple(args))
    if not rows:
        return []
    qv, _ = embed_texts([query], rows[0]["embedder"])
    q = qv[0]
    scored = []
    for r in rows:
        v = json.loads(r["vec"])
        scored.append((sum(a * b for a, b in zip(q, v)), r))
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(s, 3), "source": r["source"], "ref": r["ref"],
             "title": r["title"], "text": r["text"]} for s, r in scored[:k]]
