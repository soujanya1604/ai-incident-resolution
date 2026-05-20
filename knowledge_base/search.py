"""Semantic search over the incident runbook knowledge base."""

from __future__ import annotations

from knowledge_base.loader import _get_model, get_collection

FALLBACK_SCORE_THRESHOLD = 0.45


def search_kb(query: str, top_k: int = 3) -> list[dict]:
  """Return top matching chunks: source, content, score."""
  collection = get_collection()
  model = _get_model()
  query_embedding = model.encode([query], normalize_embeddings=True).tolist()

  count = collection.count()
  if count == 0:
    return []

  k = min(top_k, count)
  results = collection.query(
    query_embeddings=query_embedding,
    n_results=k,
    include=["documents", "metadatas", "distances"],
  )

  docs: list[dict] = []
  if not results["ids"] or not results["ids"][0]:
    return docs

  for doc_id, content, meta, distance in zip(
    results["ids"][0],
    results["documents"][0],
    results["metadatas"][0],
    results["distances"][0],
    strict=True,
  ):
    # Chroma cosine distance: 0 = identical; convert to similarity
    score = 1.0 - float(distance)
    source = meta.get("source", doc_id) if meta else doc_id
    docs.append(
      {
        "source": source,
        "content": content,
        "score": round(score, 4),
      }
    )

  return docs


def should_use_fallback(docs: list[dict]) -> bool:
  if not docs:
    return True
  return float(docs[0].get("score", 0.0)) < FALLBACK_SCORE_THRESHOLD
