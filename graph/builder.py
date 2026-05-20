"""Build and compile the LangGraph incident-resolution workflow."""

from langgraph.graph import END, START, StateGraph

from agents.intake import intake_node
from agents.rca import rca_node
from agents.recommendation import recommendation_node
from agents.retrieval import retrieval_node
from agents.security import security_node
from agents.state import AgentState, initial_state
from graph.router import route_after_intake, route_after_rca

_graph = None


def build_graph():
  global _graph
  if _graph is not None:
    return _graph

  workflow = StateGraph(AgentState)

  workflow.add_node("intake", intake_node)
  workflow.add_node("retrieval", retrieval_node)
  workflow.add_node("rca", rca_node)
  workflow.add_node("recommendation", recommendation_node)
  workflow.add_node("security", security_node)

  workflow.add_edge(START, "intake")
  workflow.add_conditional_edges(
    "intake",
    route_after_intake,
    {
      "blocked": END,
      "out_of_scope": END,
      "retrieval": "retrieval",
    },
  )
  workflow.add_edge("retrieval", "rca")
  workflow.add_conditional_edges(
    "rca",
    route_after_rca,
    {
      "end": END,
      "recommendation": "recommendation",
    },
  )
  workflow.add_edge("recommendation", "security")
  workflow.add_edge("security", END)

  _graph = workflow.compile()
  return _graph


def run_incident(message: str, state: AgentState | None = None) -> AgentState:
  graph = build_graph()
  initial = state if state is not None else initial_state(message)
  if state is None:
    initial["original_message"] = message.strip()
  return graph.invoke(initial)
