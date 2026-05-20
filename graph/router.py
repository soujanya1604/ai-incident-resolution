"""Conditional routing for the incident-resolution graph."""

from typing import Literal

from agents.state import AgentState


def route_after_intake(state: AgentState) -> Literal["blocked", "out_of_scope", "retrieval"]:
  if state.get("blocked"):
    return "blocked"
  if not state.get("is_db_related", True):
    return "out_of_scope"
  return "retrieval"


def route_after_rca(state: AgentState) -> Literal["end", "recommendation"]:
  if state.get("is_informational"):
    return "end"
  return "recommendation"
