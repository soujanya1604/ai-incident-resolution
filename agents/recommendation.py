"""Solution Recommendation Agent — ordered advisory remediation steps."""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.state import AgentState, append_trace

REC_SYSTEM = """You recommend safe, ordered remediation guidance for database and data-platform incidents.

Rules:
- Advisory only — never execute commands
- Only recommend steps for ACTIVE incidents needing remediation — not for purely informational questions
- Reason about the exact tools, product tiers, and versions the user mentioned
- Prefer reversible, low-risk steps first when dealing with operational incidents
- Avoid destructive SQL (DROP, DELETE, TRUNCATE)

You MUST return JSON with this structure:
{
  "primary_steps": ["step 1", "step 2", ...],
  "alternatives": [
    "Option A: ...",
    "Option B: ...",
    "Option C: ..."
  ]
}

Requirements:
- primary_steps: 2-5 concrete steps involving observable actions (check metrics, restart, config change, scale, rollback)
- alternatives: exactly 2-3 different approaches if the primary path may not work
- Each alternative must start with "Option A:", "Option B:", or "Option C:"""

_INCIDENT_ERROR_TYPES = frozenset(
  {
    "pool_exhaustion",
    "timeout",
    "reserved_slots",
    "connection_refused",
  }
)

_SYSTEM_CHANGE_KEYWORDS = (
  "restart",
  "rollback",
  "config",
  "configuration",
  "pool_size",
  "pool size",
  "max_connections",
  "resize",
  "scale",
  "terminate",
  "deploy",
  "pgbouncer",
  "failover",
  "increase",
  "decrease",
  "adjust",
  "set ",
)

_INFORMATIONAL_PATTERNS = re.compile(
  r"^\s*(what is|what are|what does|how does|how do|where is|explain|define)\b",
  re.I,
)


def _parse_json(content: str) -> dict:
  text = content.strip()
  if "```" in text:
    text = text.split("```")[1]
    if text.startswith("json"):
      text = text[4:]
  return json.loads(text.strip())


def _flatten_steps(primary: list[str], alternatives: list[str]) -> list[str]:
  steps: list[str] = ["Primary Fix:"]
  steps.extend(s for s in primary if str(s).strip())
  steps.append("Alternative Approaches:")
  steps.extend(s for s in alternatives if str(s).strip())
  return steps


def _steps_involve_system_changes(steps: list[str]) -> bool:
  blob = " ".join(steps).lower()
  return any(keyword in blob for keyword in _SYSTEM_CHANGE_KEYWORDS)


def _compute_requires_approval(state: AgentState, steps: list[str]) -> bool:
  if not state.get("is_db_related", True):
    return False
  if state.get("is_informational", False):
    return False
  if state.get("is_vague", False):
    return False

  confidence = float(state.get("confidence", 0.0))
  if confidence < 0.40:
    return False
  if confidence < 0.60:
    return False

  message = state.get("original_message", "")
  if _INFORMATIONAL_PATTERNS.search(message):
    return False

  error_type = state.get("error_type", "unknown")
  if error_type in ("unknown", "N/A", "informational"):
    return False

  is_active_incident = error_type in _INCIDENT_ERROR_TYPES or state.get("severity") in (
    "high",
    "critical",
  )
  if not is_active_incident:
    return False

  if not steps:
    return False

  return _steps_involve_system_changes(steps)


def _default_steps(state: AgentState) -> list[str]:
  root = (state.get("root_cause") or "").strip()
  if state.get("used_fallback") and root:
    primary = [root] if root else ["Review the diagnosis above and confirm product tier limitations."]
    alternatives = [
      "Option A: Export data to CSV/Excel and use a tool tier that accepts uploads only.",
      "Option B: Use a paid or enterprise edition that supports native database connectors.",
      "Option C: Use an intermediary (ETL, Google Sheets, or middleware) then connect the supported client.",
    ]
    return _flatten_steps(primary, alternatives)

  error_type = state.get("error_type", "")
  if error_type == "pool_exhaustion":
    primary = [
      "Check pg_stat_activity count vs max_connections on the affected database.",
      "Review recent deploys for increased replica count or pool_size changes.",
      "Identify idle-in-transaction sessions and long-running queries.",
      "Temporarily reduce traffic or scale read replicas if available.",
      "Adjust SQLAlchemy pool_size/max_overflow after calculating connection budget.",
    ]
    alternatives = [
      "Option A: Enable or tune PgBouncer transaction pooling if not already in use.",
      "Option B: Scale RDS instance class for higher max_connections headroom.",
      "Option C: Escalate to DBA on-call if pool exhaustion persists after traffic reduction.",
    ]
    return _flatten_steps(primary, alternatives)
  if error_type == "timeout":
    primary = [
      "Check PgBouncer SHOW POOLS for cl_waiting > 0.",
      "Review application pool_timeout and active connection counts.",
      "Look for long transactions blocking pool checkout.",
      "Increase bouncer default_pool_size incrementally if RDS headroom allows.",
    ]
    alternatives = [
      "Option A: Reduce application pool_size to lower contention at the bouncer.",
      "Option B: Add read replicas and route read traffic away from the primary.",
      "Option C: Escalate to DBA if timeouts correlate with replication or slot issues.",
    ]
    return _flatten_steps(primary, alternatives)
  if error_type == "reserved_slots":
    primary = [
      "Escalate to DBA on-call immediately — critical connection slot exhaustion.",
      "Terminate only approved idle sessions; avoid killing active writers.",
      "Review superuser_reserved_connections and replication slot usage.",
      "Consider RDS Proxy or vertical scaling for max_connections headroom.",
    ]
    alternatives = [
      "Option A: Fail over read traffic and pause non-critical batch jobs.",
      "Option B: Increase instance max_connections after capacity review.",
      "Option C: Open vendor support ticket if slots are held by replication or system processes.",
    ]
    return _flatten_steps(primary, alternatives)

  primary = [
    "Gather pg_stat_activity and connection metrics from monitoring.",
    "Correlate timeline with deploys and traffic changes.",
    "Consult connection pool playbook before making config changes.",
  ]
  alternatives = [
    "Option A: Validate application connection string and network path to the database.",
    "Option B: Review recent configuration or credential changes.",
    "Option C: Escalate to platform/DBA team with timestamps and error logs.",
  ]
  return _flatten_steps(primary, alternatives)


def recommendation_node(state: AgentState) -> dict:
  if not state.get("is_db_related", True):
    return {
      "recommended_steps": [],
      "requires_approval": False,
      "steps_locked": False,
    }

  if state.get("is_informational") or state.get("is_vague"):
    trail = append_trace(
      state,
      "Recommendation",
      "skipped — informational or vague question (no remediation steps)",
    )
    return {
      "recommended_steps": [],
      "requires_approval": False,
      "steps_locked": False,
      "trace": trail,
    }

  prompt = f"""Incident:
- Service: {state.get('service')}
- Error type: {state.get('error_type')}
- Severity: {state.get('severity')}
- Original message: {state.get('original_message')}
- Root cause: {state.get('root_cause')}
- Confidence: {state.get('confidence')}
- Used general-knowledge fallback: {state.get('used_fallback', False)}
"""

  steps: list[str] = []
  try:
    llm = get_llm(temperature=0.2)
    response = llm.invoke(
      [
        SystemMessage(content=REC_SYSTEM),
        HumanMessage(content=prompt),
      ]
    )
    result = _parse_json(response.content)
    primary = [str(s) for s in result.get("primary_steps", []) if str(s).strip()]
    alternatives = [str(s) for s in result.get("alternatives", []) if str(s).strip()]

    if primary or alternatives:
      if not primary:
        primary = [str(state.get("root_cause", "Follow the root cause diagnosis above."))]
      while len(alternatives) < 2:
        alternatives.append(
          f"Option {chr(65 + len(alternatives))}: Consult official documentation or escalate to your platform team."
        )
      alternatives = alternatives[:3]
      steps = _flatten_steps(primary, alternatives)
    else:
      raw = result.get("recommended_steps", [])
      steps = [str(s) for s in raw if str(s).strip()]
  except Exception:
    steps = _default_steps(state)

  if not steps:
    steps = _default_steps(state)

  requires_approval = _compute_requires_approval(state, steps)

  trail = append_trace(
    state,
    "Recommendation",
    f"generated {len(steps)} lines; requires_approval={requires_approval}",
  )

  return {
    "recommended_steps": steps,
    "requires_approval": requires_approval,
    "steps_locked": requires_approval,
    "trace": trail,
  }
