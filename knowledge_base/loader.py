"""Load markdown docs and build ChromaDB vector index."""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

_DOCS_DIR = Path(__file__).parent / "docs"
_CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"
_COLLECTION_NAME = "incident_runbooks"
_MODEL_NAME = "all-MiniLM-L6-v2"
_CHUNK_SIZE = 700
_CHUNK_OVERLAP = 100

_client: chromadb.ClientAPI | None = None
_collection = None
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
  global _model
  if _model is None:
    _model = SentenceTransformer(_MODEL_NAME)
  return _model


def _chunk_text(text: str, source: str) -> list[tuple[str, dict]]:
  chunks: list[tuple[str, dict]] = []
  start = 0
  idx = 0
  while start < len(text):
    end = min(start + _CHUNK_SIZE, len(text))
    chunk = text[start:end].strip()
    if chunk:
      chunks.append((chunk, {"source": source, "chunk_index": idx}))
      idx += 1
    if end >= len(text):
      break
    start = end - _CHUNK_OVERLAP
  return chunks


def _load_documents() -> list[tuple[str, str, dict]]:
  documents: list[tuple[str, str, dict]] = []
  for path in sorted(_DOCS_DIR.glob("*.md")):
    text = path.read_text(encoding="utf-8")
    source = path.name
    for chunk, meta in _chunk_text(text, source):
      doc_id = f"{source}::{meta['chunk_index']}"
      documents.append((doc_id, chunk, meta))
  return documents


def _get_collection():
  global _client, _collection
  if _collection is not None:
    return _collection

  _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
  _client = chromadb.PersistentClient(
    path=str(_CHROMA_DIR),
    settings=Settings(anonymized_telemetry=False),
  )

  try:
    _collection = _client.get_collection(_COLLECTION_NAME)
    if _collection.count() > 0:
      return _collection
  except Exception:
    pass

  _collection = _client.get_or_create_collection(
    name=_COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
  )

  if _collection.count() == 0:
    docs = _load_documents()
    if not docs:
      return _collection
    ids = [d[0] for d in docs]
    texts = [d[1] for d in docs]
    metadatas = [d[2] for d in docs]
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True).tolist()
    _collection.add(
      ids=ids,
      documents=texts,
      embeddings=embeddings,
      metadatas=metadatas,
    )

  return _collection


def get_collection():
  """Public accessor for search module."""
  return _get_collection()


def warmup_kb() -> None:
  """Load embedding model and Chroma index at process start (avoids first-request latency)."""
  get_collection()
  _get_model()


def reset_index() -> None:
  """Clear in-memory clients so the next get_collection() rebuilds from disk."""
  global _client, _collection
  _collection = None
  _client = None


def load_documents() -> int:
  """Rebuild the vector index from all markdown files in knowledge_base/docs/."""
  import shutil

  reset_index()
  if _CHROMA_DIR.exists():
    shutil.rmtree(_CHROMA_DIR)

  collection = get_collection()
  return collection.count()


if __name__ == "__main__":
  count = load_documents()
  print("Knowledge base indexed successfully.")
  print(f"Total documents in index: {count}")
