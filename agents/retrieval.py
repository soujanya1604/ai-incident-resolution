"""RAG Retrieval Agent — search runbooks and past incidents."""

from agents.state import AgentState, append_trace
from knowledge_base.search import search_kb, should_use_fallback


def retrieval_node(state: AgentState) -> dict:
  service = state.get("service", "unknown")
  error_type = state.get("error_type", "unknown")
  snippet = (state.get("original_message", "") or "")[:200]
  query = f"{service} {error_type} database connection {snippet}"

  docs = search_kb(query, top_k=3)
  used_fallback = should_use_fallback(docs)

  doc_summary = ", ".join(
    f"{d['source']} ({d['score']:.2f})" for d in docs
  ) or "no matches"
  trail = append_trace(
    state,
    "Retrieval",
    f"found {len(docs)} docs: {doc_summary}",
  )

  if used_fallback:
    trail = append_trace(
      {**state, "trace": trail},
      "Retrieval",
      "weak KB match — fallback knowledge may be used in RCA",
    )

  return {
    "retrieved_docs": docs,
    "used_fallback": used_fallback,
    "trace": trail,
  }
