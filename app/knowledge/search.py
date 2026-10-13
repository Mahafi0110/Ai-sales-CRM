"""Finding the right passages. Two methods, then merged:

  keyword  (BM25): passages that share the important words with the question. Always available.
  semantic (embeddings): passages that mean the same thing, even with different words. Needs a Gemini key.

The two ranked lists are combined with "reciprocal rank fusion": a passage near the top of both lists wins.
"""
import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from app.knowledge.text import tokenize


@dataclass
class Candidate:
    chunk_id: int
    document_id: int
    title: str
    text: str
    embedding: bytes | None = None
    embedding_model: str | None = None


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    text: str
    score: float
    via: str  # keyword | semantic | both


def encode_vector(vector) -> bytes:
    """Store as compact bytes, scaled to length 1 so a dot product equals cosine similarity."""
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    return (array / norm if norm > 0 else array).tobytes()


def decode_vector(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


def bm25_rank(query: str, candidates: list[Candidate], k1: float = 1.5, b: float = 0.75) -> list[tuple[Candidate, float]]:
    terms = set(tokenize(query))
    if not terms or not candidates:
        return []
    # The title counts as part of every passage, so a question about "pricing" finds the Pricing document.
    docs = [Counter(tokenize(f"{c.title} {c.text}")) for c in candidates]
    lengths = [sum(d.values()) for d in docs]
    average = (sum(lengths) / len(lengths)) or 1.0
    total = len(candidates)
    document_frequency = {t: sum(1 for d in docs if t in d) for t in terms}
    scored = []
    for candidate, counts, length in zip(candidates, docs, lengths):
        score = 0.0
        for term in terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + (total - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += idf * frequency * (k1 + 1) / (frequency + k1 * (1 - b + b * length / average))
        if score > 0:
            scored.append((candidate, score))
    return sorted(scored, key=lambda pair: pair[1], reverse=True)


def semantic_rank(query_vector, candidates: list[Candidate], model_tag: str,
                  min_similarity: float) -> list[tuple[Candidate, float]]:
    query = decode_vector(encode_vector(query_vector))
    usable = [c for c in candidates if c.embedding and c.embedding_model == model_tag]
    usable = [c for c in usable if len(c.embedding) == query.nbytes]  # ignore vectors of a different size
    if not usable:
        return []
    matrix = np.vstack([decode_vector(c.embedding) for c in usable])
    similarities = matrix @ query
    scored = [(c, float(s)) for c, s in zip(usable, similarities) if s >= min_similarity]
    return sorted(scored, key=lambda pair: pair[1], reverse=True)


def fuse(keyword: list[tuple[Candidate, float]], semantic: list[tuple[Candidate, float]], limit: int,
         k: int = 60) -> list[Hit]:
    scores: dict[int, float] = {}
    via: dict[int, set] = {}
    by_id: dict[int, Candidate] = {}
    for name, ranking in (("keyword", keyword), ("semantic", semantic)):
        for rank, (candidate, _) in enumerate(ranking, start=1):
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (k + rank)
            via.setdefault(candidate.chunk_id, set()).add(name)
            by_id[candidate.chunk_id] = candidate
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]
    return [Hit(cid, by_id[cid].document_id, by_id[cid].title, by_id[cid].text, round(scores[cid], 4),
                "both" if len(via[cid]) == 2 else next(iter(via[cid]))) for cid in ordered]
