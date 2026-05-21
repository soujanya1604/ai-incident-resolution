"""Intake Agent — validate input, extract structured incident fields."""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.security import mask_secrets, validate_input
from agents.state import AgentState, append_trace

INTAKE_UNIFIED_SYSTEM = """
Rules:
- is_db_related: true for:
  - active database failures and errors
  - database connectivity issues and configuration
  - how to connect to a database or data tool
  - questions about database drivers, connection strings, 
    BI tool connections (Tableau, Power BI, Looker)
  - questions about database limits, settings, error codes
- is_db_related: false ONLY for topics completely unrelated 
  to databases or data infrastructure 
  (airports, weather, geography, sports, recipes, etc.)
"""

Return JSON only:
{
  "is_db_related": true or false,
  "is_informational": true or false,
  "service": "database or service name, or unknown",
  "error_type": "pool_exhaustion|timeout|reserved_slots|connection_refused|unknown",
  "severity": "low|medium|high|critical"
}

Rules:
- is_db_related: true only for database, data platform, or infrastructure connectivity issues
- is_db_related: false for general knowledge unrelated to DB/infra (airports, weather, geography, etc.)
- is_informational: true for factual questions (what does X mean, what is the limit, how does Y work)
- is_informational: false for active failures needing diagnosis (errors, timeouts, cannot connect)
- When is_db_related is false, set service/error_type to unknown and severity to low

Mapping hints when is_db_related is true:
- "too many clients", "53300" -> pool_exhaustion, high
- "connection timeout", "timed out" -> timeout, medium
- "reserved connection slots" -> reserved_slots, critical
- "connection refused" -> connection_refused, high"""

NOT_DB_ROOT_CAUSE = (
  "This question is not related to database incident resolution. "
  "No diagnosis applicable."
)

OUT_OF_SCOPE_MESSAGE = (
  "This system is specialized for database connection incident resolution. "
  "Your question appears to be outside that scope. "
  "Please describe a database connectivity issue and I will help diagnose it."
)

SERVICE_RE = re.compile(
  r"\b([\w-]+-(?:db|database|postgres|pgsql))\b", re.I
)

# Fast path — skip LLM for obvious non-DB questions (~0ms vs ~1-2s per call)
_NON_DB_PATTERNS = re.compile(
  r"\b(where is|what is the weather|who won|capital of|how old is|"
  r"airport|flight|restaurant|movie|recipe)\b",
  re.I,
)

_DB_HINTS = (
  "database",
  "-db",
  "postgres",
  "postgresql",
  "mysql",
  "oracle",
  "mssql",
  "sql",
  "rds",
  "pgbouncer",
  "tableau",
  "53300",
  "connection pool",
  "too many client",
  "timeout",
  "connection refused",
  "connect",
  "how to connect",
  "driver",
  "jdbc",
  "odbc"
)


def _parse_json(content: str) -> dict:
  text = content.strip()
  if "```" in text:
    text = text.split("```")[1]
    if text.startswith("json"):
      text = text[4:]
  return json.loads(text.strip())


def _heuristic_non_db(message: str) -> bool:
  lower = message.lower().strip()
  if _NON_DB_PATTERNS.search(lower):
    return not any(h in lower for h in _DB_HINTS)
  return False


def _classify_and_extract(message: str) -> dict:
  """Single LLM call: db-related + informational + field extraction (was 3 calls)."""
  llm = get_llm(temperature=0)
  response = llm.invoke(
    [
      SystemMessage(content=INTAKE_UNIFIED_SYSTEM),
      HumanMessage(content=f"User message:\n{message}"),
    ]
  )
  return _parse_json(response.content)


def _heuristic_classify(message: str) -> dict:
  lower = message.lower()
  is_db = any(h in lower for h in _DB_HINTS)
  is_info = any(
    p in lower
    for p in ("what is", "what does", "what are", "how does", "how do", "maximum", "explain")
  ) and not any(
    h in lower
    for h in ("error", "failing", "failed", "down", "cannot connect", "can't connect", "timeout", "refused", "too many")
  )
  extracted = _heuristic_extract(message)
  return {
    "is_db_related": is_db,
    "is_informational": is_info and is_db,
    **extracted,
  }


def _is_vague_message(message: str, extracted: dict) -> bool:
  text = message.strip()
  if len(text) < 25:
    return True
  lower = text.lower()
  vague_only = (
    "help",
    "not working",
    "broken",
    "issue",
    "problem",
    "db issue",
    "database issue",
    "connectivity issue",
    "connection issue",
    "connection error",
    "connection timeout",
    "connection refused",
    "connection lost",
    "connection reset",
    "connection closed",
    "connection interrupted",
    "connection failed",
    "connection blocked",
    "database down",
    "database error",
    "database timeout",
    "database refused",
    "database lost",
    "database reset",
  )
  if lower in vague_only or lower.rstrip("?.!") in vague_only:
    return True
  if (
    extracted.get("error_type") == "unknown"
    and extracted.get("service") == "unknown"
    and not any(k in lower for k in ("error", "timeout", "refused", "53300", "pool"))
  ):
    return True
  return False


def _heuristic_extract(message: str) -> dict:
  lower = message.lower()
  service = "unknown"
  match = SERVICE_RE.search(message)
  if match:
    service = match.group(1).lower()

  error_type = "unknown"
  severity = "medium"

  if "too many client" in lower or "too many connection" in lower or "53300" in lower:
    error_type = "pool_exhaustion"
    severity = "high"
  elif "timeout" in lower or "timed out" in lower:
    error_type = "timeout"
    severity = "medium"
  elif "reserved" in lower and "connection slot" in lower:
    error_type = "reserved_slots"
    severity = "critical"
  elif "connection refused" in lower:
    error_type = "connection_refused"
    severity = "high"
  elif "after deployment" in lower or "after deploy" in lower:
    severity = "high"

  return {"service": service, "error_type": error_type, "severity": severity}


def intake_node(state: AgentState) -> dict:
  message = state.get("original_message", "")
  trail = list(state.get("trace", []))

  blocked, reason = validate_input(message)
  if blocked:
    trail.append(f"Security: blocked — {reason}")
    return {
      "blocked": True,
      "sanitized_response": (
        "Incident blocked for security reasons. "
        "Remove destructive commands or prompt-injection patterns and retry."
      ),
      "trace": trail,
      "root_cause": "",
      "confidence": 0.0,
      "recommended_steps": [],
      "requires_approval": False,
      "is_db_related": True,
      "is_informational": False,
    }

  masked_message = mask_secrets(message)
  trail = append_trace({**state, "trace": trail}, "Intake", "passed security input check")

  if _heuristic_non_db(masked_message):
    trail = append_trace(
      {**state, "trace": trail},
      "Intake",
      "heuristic out-of-scope (no LLM)",
    )
    return {
      "original_message": masked_message,
      "service": "N/A",
      "error_type": "N/A",
      "severity": "none",
      "is_db_related": False,
      "is_informational": False,
      "is_vague": False,
      "requires_approval": False,
      "root_cause": NOT_DB_ROOT_CAUSE,
      "sanitized_response": OUT_OF_SCOPE_MESSAGE,
      "confidence": 0.20,
      "recommended_steps": [],
      "steps_locked": False,
      "blocked": False,
      "trace": trail,
    }

  try:
    parsed = _classify_and_extract(masked_message)
    trail = append_trace(
      {**state, "trace": trail},
      "Intake",
      "unified classify+extract (1 LLM call)",
    )
  except Exception:
    parsed = _heuristic_classify(masked_message)
    trail = append_trace(
      {**state, "trace": trail},
      "Intake",
      "heuristic classify+extract (LLM fallback)",
    )

  is_db_related = bool(parsed.get("is_db_related", True))
  is_informational = bool(parsed.get("is_informational", False))

  if not is_db_related:
    trail = append_trace(
      {**state, "trace": trail},
      "Intake",
      "out of scope — skipping diagnosis pipeline",
    )
    return {
      "original_message": masked_message,
      "service": "N/A",
      "error_type": "N/A",
      "severity": "none",
      "is_db_related": False,
      "is_informational": False,
      "is_vague": False,
      "requires_approval": False,
      "root_cause": NOT_DB_ROOT_CAUSE,
      "sanitized_response": OUT_OF_SCOPE_MESSAGE,
      "confidence": 0.20,
      "recommended_steps": [],
      "steps_locked": False,
      "blocked": False,
      "trace": trail,
    }

  service = str(parsed.get("service", "unknown"))
  error_type = str(parsed.get("error_type", "unknown"))
  severity = str(parsed.get("severity", "medium"))
  if is_informational:
    error_type = "informational"

  is_vague = False if is_informational else _is_vague_message(
    masked_message,
    {"service": service, "error_type": error_type},
  )

  trail = append_trace(
    {**state, "trace": trail},
    "Intake",
    f"is_informational={is_informational}, service={service}, error_type={error_type}",
  )

  return {
    "original_message": masked_message,
    "service": service,
    "error_type": error_type,
    "severity": severity,
    "blocked": False,
    "is_db_related": True,
    "is_informational": is_informational,
    "is_vague": is_vague,
    "requires_approval": False,
    "trace": trail,
  }
