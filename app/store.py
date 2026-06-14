"""Tiny local vector store: numpy cosine search over embedded chunks.

Storage layout (in db/):
  vectors.npy   — float32 matrix, one row per chunk
  chunks.json   — list of {id, text, source, doc_type, mtime} aligned with rows
  hashes.json   — {file_path: sha256} for incremental ingestion
"""

import json
import unicodedata
from pathlib import Path

import numpy as np
import ollama

EMBED_MODEL = "nomic-embed-text"
DB_DIR = Path(__file__).parent / "db"


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text)


class VectorStore:
    def __init__(self, db_dir: Path = DB_DIR):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(exist_ok=True)
        self.vectors_path = self.db_dir / "vectors.npy"
        self.chunks_path = self.db_dir / "chunks.json"
        self.hashes_path = self.db_dir / "hashes.json"
        self.vectors = (
            np.load(self.vectors_path) if self.vectors_path.exists() else None
        )
        self.chunks = (
            json.loads(self.chunks_path.read_text())
            if self.chunks_path.exists()
            else []
        )
        self.hashes = (
            json.loads(self.hashes_path.read_text())
            if self.hashes_path.exists()
            else {}
        )

    # -- embedding ---------------------------------------------------------
    @staticmethod
    def embed(texts: list[str]) -> np.ndarray:
        resp = ollama.embed(model=EMBED_MODEL, input=[_norm(t) for t in texts])
        mat = np.asarray(resp["embeddings"], dtype=np.float32)
        mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        return mat

    # -- writes ------------------------------------------------------------
    def remove_source(self, source: str) -> None:
        keep = [i for i, c in enumerate(self.chunks) if c["source"] != source]
        if len(keep) == len(self.chunks):
            return
        self.chunks = [self.chunks[i] for i in keep]
        self.vectors = self.vectors[keep] if self.chunks else None

    def add(self, chunks: list[dict]) -> None:
        """chunks: [{text, source, doc_type, ...meta}] — embeds and appends."""
        if not chunks:
            return
        mat = self.embed([f"search_document: {c['text']}" for c in chunks])
        self.vectors = mat if self.vectors is None else np.vstack([self.vectors, mat])
        self.chunks.extend(chunks)

    def save(self) -> None:
        if self.vectors is not None:
            np.save(self.vectors_path, self.vectors)
        self.chunks_path.write_text(json.dumps(self.chunks, ensure_ascii=False))
        self.hashes_path.write_text(json.dumps(self.hashes, ensure_ascii=False))

    # -- search ------------------------------------------------------------
    def search_grouped(self, query: str, specs: list[tuple]) -> dict[str, list[dict]]:
        """Bucketed retrieval in ONE embedding pass.

        specs: list of (doc_type, k, floor). Returns {doc_type: [hits]} where each
        bucket holds up to k hits scoring >= floor, sorted by relevance. Lets the
        caller pull experience and application material into separate, labeled
        groups (and use a softer floor for résumé content) without re-embedding.
        """
        if self.vectors is None or not self.chunks:
            return {}
        q = self.embed([f"search_query: {query}"])[0]
        scores = self.vectors @ q
        order = np.argsort(scores)[::-1]
        want = {dt: (k, floor) for dt, k, floor in specs}
        out: dict[str, list[dict]] = {dt: [] for dt in want}
        for i in order:
            c = self.chunks[int(i)]
            dt = c.get("doc_type")
            if dt not in want:
                continue
            k, floor = want[dt]
            if len(out[dt]) >= k:
                continue
            s = float(scores[int(i)])
            if s < floor:
                continue
            out[dt].append({**c, "score": s})
        return out

    def search(self, query: str, k: int = 6, doc_type: str | None = None) -> list[dict]:
        if self.vectors is None or not self.chunks:
            return []
        q = self.embed([f"search_query: {query}"])[0]
        scores = self.vectors @ q
        order = np.argsort(scores)[::-1]
        out = []
        for i in order:
            c = self.chunks[int(i)]
            if doc_type and c.get("doc_type") != doc_type:
                continue
            out.append({**c, "score": float(scores[int(i)])})
            if len(out) >= k:
                break
        return out
