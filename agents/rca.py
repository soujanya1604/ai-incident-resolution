"""Root Cause Analysis Agent — reason over incident and retrieved docs."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm
from agents.state import AgentState, append_trace

KB_MIN_USE_THRESHOLD = 0.50
KB_STRONG_THRESHOLD = 0.70
LOW_CONFIDENCE_THRESHOLD = 0.55

NOT_DB_ROOT_CAUSE = (
  "This question is not related to database incident resolution. "
  "No diagnosis applicable."
)

VAGUE_CLARIFY_SYSTEM = """You are a senior on-call database engineer receiving a vague \
incident report. You need more information before you can diagnose the issue. Respond in a \
natural, conversational tone — like a colleague who knows what they are doing, not a helpdesk \
ticket form.

Your response must:
1. Acknowledge what little information was given without dismissing it
2. Ask ONE specific follow-up question that will give you the most diagnostic value — not a list of questions
3. Give a brief reason why that specific information matters
4. If you can make any reasonable inference from what was given, state it as a possibility worth checking

Never output bullet lists. Never say 'please provide'.
Write 2-3 sentences maximum. Sound human."""

RCA_SYSTEM_KB = """You are a senior SRE performing root cause analysis on database connection incidents.

Given incident details and retrieved runbook excerpts, determine the most likely root cause.
The runbooks are relevant — use them as primary evidence.

Return JSON only:
{
  "root_cause": "clear 1-2 sentence explanation",
  "confidence": 0.0 to 1.0
}

Be specific to the tools and services the user mentioned. Never give a generic pool/timeout answer
unless those are genuinely relevant to the question."""

RCA_SYSTEM_GENERAL = """You are a senior database and infrastructure engineer with deep knowledge \
of databases (PostgreSQL, Oracle, MySQL, MSSQL), BI tools (Tableau, Power BI, Looker), cloud \
platforms (AWS RDS, Azure SQL, GCP Cloud SQL), and connection protocols.

When answering:
1. Reason specifically about the exact tools and services mentioned by the user — never give a generic answer
2. If a tool has known limitations (e.g. Tableau Public cannot connect to databases), state that limitation clearly
3. Distinguish between product tiers (Tableau Public vs Desktop vs Server/Cloud)
4. If the user's approach is impossible, say so before suggesting alternatives
5. Never default to connection pool or timeout explanations unless genuinely relevant

Return JSON only:
{
  "root_cause": "clear 1-3 sentence explanation addressing the exact question",
  "confidence": 0.0 to 1.0
}"""

RCA_SYSTEM_INFORMATIONAL = """You are a senior database engineer answering factual questions clearly and directly.

The user is NOT reporting an active incident — they want an explanation, definition, or reference value.
Answer like a knowledgeable colleague: concise, accurate, and specific to the tools mentioned.

Do NOT format as an incident diagnosis. Do NOT invent connection pool or timeout causes.
Do NOT include remediation steps unless briefly relevant to clarify the answer.

Return JSON only:
{
  "root_cause": "direct answer to the question (2-4 sentences max)",
  "confidence": 0.0 to 1.0
}"""

_INCIDENT_ERROR_TYPES = frozenset(
  {
    "pool_exhaustion",
    "timeout",
    "reserved_slots",
    "connection_refused",
  }
)


def _max_kb_score(docs: list) -> float:
  if not docs:
    return 0.0
  return max(float(d.get("score", 0.0)) for d in docs)


def _ignore_kb(docs: list) -> bool:
  return _max_kb_score(docs) < KB_MIN_USE_THRESHOLD


def _format_docs(docs: list, *, ignore_kb: bool) -> str:
  if ignore_kb:
    return (
      "Knowledge base results were ignored (highest similarity below 0.50 — not relevant). "
      "Reason from general engineering knowledge about the specific tools mentioned."
    )
  if not docs:
    return "No relevant documents retrieved."
  parts = []
  for d in docs:
    parts.append(f"### {d.get('source', 'unknown')} (score={d.get('score', 0)})\n{d.get('content', '')}")
  return "\n\n".join(parts)


def _parse_json(content: str) -> dict:
  text = content.strip()
  if "```" in text:
    text = text.split("```")[1]
    if text.startswith("json"):
      text = text[4:]
  return json.loads(text.strip())


def _has_clarification_context(state: AgentState) -> bool:
  history = state.get("conversation_history") or []
  if len(history) < 2:
    return False
  roles = {m.get("role") for m in history if isinstance(m, dict)}
  return "user" in roles and "assistant" in roles


def _format_conversation_history(state: AgentState) -> str:
  history = state.get("conversation_history") or []
  if not history:
    return ""
  lines = ["Previous exchange:"]
  for msg in history:
    if not isinstance(msg, dict):
      continue
    role = msg.get("role", "")
    content = (msg.get("content") or "").strip()
    if not content:
      continue
    label = "Engineer" if role == "user" else "Agent"
    lines.append(f"{label}: {content}")
  lines.append(f"Engineer: {state.get('original_message', '')}")
  lines.append("")
  lines.append("Now diagnose with this additional context.")
  return "\n".join(lines)


def _generate_clarifying_question(state: AgentState) -> str:
  llm = get_llm(temperature=0.4)
  history_block = _format_conversation_history(state)
  user_msg = state.get("original_message", "")
  parts = []
  if history_block:
    parts.append(history_block)
  else:
    parts.append(f"Engineer: {user_msg}")
  response = llm.invoke(
    [
      SystemMessage(content=VAGUE_CLARIFY_SYSTEM),
      HumanMessage(content="\n".join(parts)),
    ]
  )
  text = (response.content or "").strip()
  return text or (
    "That could be a few different things on the database side — connection limits, "
    "instance health, or something in the app layer. What error message are you seeing "
    "in the application logs or database? That will tell us which direction to go."
  )


def _clarifying_response(state: AgentState, *, reason: str) -> dict:
  question = _generate_clarifying_question(state)
  confidence = 0.48
  trail = append_trace(state, "RCA", f"{reason} (confidence={confidence:.2f})")
  return {
    "root_cause": question,
    "confidence": confidence,
    "is_vague": True,
    "requires_approval": False,
    "sanitized_response": question,
    "recommended_steps": [],
    "steps_locked": False,
    "trace": trail,
  }


def _needs_clarification(state: AgentState, confidence: float) -> bool:
  if state.get("is_informational"):
    return False
  if _has_clarification_context(state):
    return False
  return bool(state.get("is_vague")) or confidence < LOW_CONFIDENCE_THRESHOLD


def _is_active_db_incident(state: AgentState) -> bool:
  if state.get("is_informational"):
    return False
  error_type = state.get("error_type", "unknown")
  if error_type in _INCIDENT_ERROR_TYPES:
    return True
  severity = state.get("severity", "medium")
  return severity in ("high", "critical")


def _derive_confidence(
  *,
  is_db_related: bool,
  is_informational: bool,
  is_vague: bool,
  max_kb_score: float,
  is_active_incident: bool,
  has_clarification: bool,
) -> float:
  if not is_db_related:
    return 0.20

  if is_vague and not has_clarification:
    return 0.48

  if is_informational:
    if max_kb_score >= KB_STRONG_THRESHOLD:
      return 0.90
    if max_kb_score >= KB_MIN_USE_THRESHOLD:
      return 0.78
    return 0.68

  if has_clarification and is_active_incident:
    if max_kb_score >= KB_STRONG_THRESHOLD:
      return 0.90
    if max_kb_score >= KB_MIN_USE_THRESHOLD:
      return 0.82
    return 0.72

  if has_clarification:
    if max_kb_score >= KB_MIN_USE_THRESHOLD:
      return 0.78
    return 0.70

  if max_kb_score >= KB_STRONG_THRESHOLD and is_active_incident:
    return 0.92

  if max_kb_score >= KB_MIN_USE_THRESHOLD:
    return 0.78

  return 0.68


def rca_node(state: AgentState) -> dict:
  if not state.get("is_db_related", True):
    return {}

  has_clarification = _has_clarification_context(state)

  if state.get("is_vague") and not has_clarification:
    return _clarifying_response(state, reason="vague input — conversational follow-up")

  docs = state.get("retrieved_docs", [])
  max_score = _max_kb_score(docs)
  ignore_kb = _ignore_kb(docs)
  used_fallback = bool(state.get("used_fallback", False)) or ignore_kb
  is_informational = bool(state.get("is_informational"))
  is_active = _is_active_db_incident(state)

  if is_informational:
    system_prompt = RCA_SYSTEM_INFORMATIONAL
  elif ignore_kb:
    system_prompt = RCA_SYSTEM_GENERAL
  else:
    system_prompt = RCA_SYSTEM_KB

  docs_text = _format_docs(docs, ignore_kb=ignore_kb)
  history_text = _format_conversation_history(state) if has_clarification else ""

  prompt = f"""Question / incident:
- Service: {state.get('service')}
- Error type: {state.get('error_type')}
- Severity: {state.get('severity')}
- Message: {state.get('original_message')}
- Informational question: {is_informational}
- Active DB connection incident: {is_active}
- Follow-up with prior context: {has_clarification}

Highest KB similarity score: {max_score:.2f}
KB ignored (weak match): {ignore_kb}

{history_text}

Retrieved documentation:
{docs_text}
"""

  root_cause = "Unable to determine root cause from available information."
  confidence = 0.30

  try:
    llm = get_llm(temperature=0.1)
    response = llm.invoke(
      [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
      ]
    )
    result = _parse_json(response.content)
    root_cause = str(result.get("root_cause", root_cause))
    confidence = _derive_confidence(
      is_db_related=True,
      is_informational=is_informational,
      is_vague=False,
      max_kb_score=max_score,
      is_active_incident=is_active,
      has_clarification=has_clarification,
    )
  except Exception:
    if is_informational:
      root_cause = (
        "I couldn't pull together a solid answer from that — which database product "
        "and detail are you asking about?"
      )
      confidence = 0.45
    elif ignore_kb:
      root_cause = (
        "I'm not confident enough to call this without more context — what error "
        "or symptom are you seeing in the app or database logs?"
      )
      confidence = 0.45
    else:
      error_type = state.get("error_type", "")
      if error_type == "pool_exhaustion":
        root_cause = "Connection pool likely exhausted — too many clients for available slots."
        confidence = 0.92
      elif error_type == "timeout":
        root_cause = "Connection timeout likely due to pool or PgBouncer queue saturation."
        confidence = 0.78
      elif error_type == "reserved_slots":
        root_cause = "All non-superuser connection slots exhausted; critical escalation required."
        confidence = 0.92
      else:
        confidence = 0.48

  if _needs_clarification(state, confidence):
    return _clarifying_response(state, reason="low confidence — conversational follow-up")

  trail = append_trace(
    state,
    "RCA",
    f"analysis complete (confidence={confidence:.2f}, kb_max={max_score:.2f}, informational={is_informational})",
  )

  result: dict = {
    "root_cause": root_cause,
    "confidence": confidence,
    "used_fallback": used_fallback,
    "is_vague": False,
    "trace": trail,
  }

  if is_informational:
    result["sanitized_response"] = root_cause
    result["requires_approval"] = False
    result["recommended_steps"] = []
    result["steps_locked"] = False

  return result
