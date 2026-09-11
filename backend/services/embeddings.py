"""
Shared embedding shim for IP-Sakti.
Imported by both ingest.py and retriever.py.

fastembed >= 0.6 changed multilingual-e5-large to mean pooling without
normalization (norm ~30). This shim L2-normalizes every vector so cosine
space works correctly.
"""
from __future__ import annotations
import numpy as np
from fastembed import TextEmbedding


class FastEmbedEmbeddings:
    def __init__(self, model_name: str):
        self._model_name = model_name
        self._m = TextEmbedding(model_name, providers=["CPUExecutionProvider"])
        self._assert_normalized()

    @staticmethod
    def _normalize(vecs: list) -> list:
        arr = np.array(vecs, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (arr / norms).tolist()

    def _assert_normalized(self) -> None:
        test_vec = self.embed_query("query: normalization self-test")
        norm = float(np.linalg.norm(test_vec))
        if abs(norm - 1.0) > 1e-3:
            raise RuntimeError(
                f"[embeddings] Normalization assertion failed: norm={norm:.6f} "
                f"(expected 1.0 +/- 0.001). Model: {self._model_name}"
            )

    def embed_documents(self, texts: list) -> list:
        prefixed = [f"passage: {t}" for t in texts]
        raw = [
            v.tolist() if hasattr(v, "tolist") else list(v)
            for v in self._m.embed(prefixed, batch_size=16)
        ]
        return self._normalize(raw)

    def embed_query(self, text: str) -> list:
        prefixed = f"query: {text}"
        vec = next(iter(self._m.embed([prefixed])))
        raw = vec.tolist() if hasattr(vec, "tolist") else list(vec)
        return self._normalize([raw])[0]
