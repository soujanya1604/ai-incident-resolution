"""In-memory incident store for API and approval flow."""

from __future__ import annotations

import uuid
from typing import Any

from agents.state import AgentState
from graph.builder import run_incident


_incidents: dict[str, AgentState] = {}


def _display_response(state: AgentState) -> str:
  if not state.get("is_db_related", True):
    return state.get("sanitized_response") or state.get("root_cause", "")
  if state.get("is_informational") or state.get("is_vague"):
    return state.get("root_cause") or state.get("sanitized_response", "")
  return state.get("sanitized_response") or state.get("root_cause", "")


def _to_api_payload(incident_id: str, state: AgentState, *, locked: bool = True) -> dict[str, Any]:
  steps = state.get("recommended_steps", [])
  requires_approval = bool(state.get("requires_approval", False))
  return {
    "incident_id": incident_id,
    "service": state.get("service", "unknown"),
    "error_type": state.get("error_type", "unknown"),
    "severity": state.get("severity", "medium"),
    "root_cause": state.get("root_cause", ""),
    "confidence": float(state.get("confidence", 0.0)),
    "recommended_steps": [] if locked else steps,
    "steps_locked": locked,
    "human_approved": bool(state.get("human_approved", False)),
    "sanitized_response": _display_response(state),
    "used_fallback": bool(state.get("used_fallback", False)),
    "trace": state.get("trace", []),
    "blocked": bool(state.get("blocked", False)),
    "flagged_steps": state.get("flagged_steps", []),
    "is_db_related": bool(state.get("is_db_related", True)),
    "is_informational": bool(state.get("is_informational", False)),
    "requires_approval": requires_approval,
    "is_vague": bool(state.get("is_vague", False)),
  }


def create_incident(
  message: str,
  conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
  initial = None
  if conversation_history:
    from agents.state import initial_state

    initial = initial_state(message)
    initial["conversation_history"] = conversation_history
  state = run_incident(message, state=initial)
  incident_id = str(uuid.uuid4())
  state["incident_id"] = incident_id
  state["human_approved"] = False
  requires_approval = bool(state.get("requires_approval", False))
  locked = requires_approval and not state.get("blocked", False)
  state["steps_locked"] = locked
  _incidents[incident_id] = state
  return _to_api_payload(incident_id, state, locked=locked)


def get_incident(incident_id: str) -> AgentState | None:
  return _incidents.get(incident_id)


def approve_incident(incident_id: str) -> dict[str, Any]:
  state = _incidents.get(incident_id)
  if state is None:
    raise KeyError(f"Unknown incident: {incident_id}")

  if state.get("blocked"):
    raise ValueError("Cannot approve a blocked incident")

  if not state.get("requires_approval", False):
    raise ValueError("This response does not require approval")

  state = {**state, "human_approved": True, "steps_locked": False}
  _incidents[incident_id] = state

  steps = state.get("recommended_steps", [])
  steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
  final = _display_response(state)
  if steps_text:
    final = f"{final}\n\n--- Approved remediation steps ---\n{steps_text}"

  return {
    "status": "approved",
    "incident_id": incident_id,
    "final_response": final,
    "recommended_steps": steps,
    "human_approved": True,
  }
