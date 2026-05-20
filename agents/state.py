"""Shared graph state for all incident-resolution agents."""

from typing import Any, TypedDict


class RetrievedDoc(TypedDict, total=False):
  source: str
  content: str
  score: float


class AgentState(TypedDict, total=False):
  original_message: str
  service: str
  error_type: str
  severity: str
  retrieved_docs: list[RetrievedDoc]
  root_cause: str
  confidence: float
  recommended_steps: list[str]
  human_approved: bool
  sanitized_response: str
  used_fallback: bool
  trace: list[str]
  blocked: bool
  incident_id: str
  steps_locked: bool
  flagged_steps: list[str]
  is_db_related: bool
  is_informational: bool
  requires_approval: bool
  is_vague: bool


def append_trace(state: AgentState, agent: str, message: str) -> list[str]:
  trail = list(state.get("trace", []))
  trail.append(f"{agent}: {message}")
  return trail


def initial_state(message: str) -> AgentState:
  return {
    "original_message": message.strip(),
    "service": "unknown",
    "error_type": "unknown",
    "severity": "medium",
    "retrieved_docs": [],
    "root_cause": "",
    "confidence": 0.0,
    "recommended_steps": [],
    "human_approved": False,
    "sanitized_response": "",
    "used_fallback": False,
    "trace": [],
    "blocked": False,
    "incident_id": "",
    "steps_locked": True,
    "flagged_steps": [],
    "is_db_related": True,
    "is_informational": False,
    "requires_approval": False,
    "is_vague": False,
  }
