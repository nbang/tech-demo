"""Vector store backed by FAISS.

A database schema is small (tens to low-thousands of tables), so an exhaustive
flat inner-product index is the simplest correct choice. Vectors are L2-normalized,
so inner product == cosine similarity. Persisted as a FAISS index + a JSON sidecar.
"""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

_INDEX_FILE = "index.faiss"
_DOCS_FILE = "documents.json"


class VectorStore:
    def __init__(self, ids: list[str], documents: list[str], index: faiss.Index):
        self.ids = ids
        self.documents = documents
        self.index = index

    @classmethod
    def build(cls, ids: list[str], documents: list[str], vectors: list[list[float]]) -> "VectorStore":
        embeddings = np.asarray(vectors, dtype=np.float32)
        faiss.normalize_L2(embeddings)
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        return cls(ids, documents, index)

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, str, float]]:
        q = np.asarray([query_vector], dtype=np.float32)
        faiss.normalize_L2(q)
        scores, idx = self.index.search(q, min(top_k, len(self.ids)))
        return [
            (self.ids[i], self.documents[i], float(score))
            for i, score in zip(idx[0], scores[0])
            if i != -1
        ]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(directory / _INDEX_FILE))
        (directory / _DOCS_FILE).write_text(
            json.dumps({"ids": self.ids, "documents": self.documents}, ensure_ascii=False)
        )

    @classmethod
    def load(cls, directory: Path) -> "VectorStore":
        data = json.loads((directory / _DOCS_FILE).read_text())
        index = faiss.read_index(str(directory / _INDEX_FILE))
        return cls(data["ids"], data["documents"], index)
