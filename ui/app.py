"""Streamlit UI — incident input, agent trace, human approval gate."""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_PORT = os.getenv("API_PORT", "8001")
API_URL = os.getenv("API_URL", f"http://localhost:{API_PORT}").rstrip("/")

st.set_page_config(
  page_title="AI Incident Resolution",
  page_icon="🔧",
  layout="wide",
)

_DEFAULTS = {
  "messages": [],
  "api_pending": None,
  "latest_incident": None,
  "steps_revealed": False,
  "approved_payload": None,
}
for key, value in _DEFAULTS.items():
  if key not in st.session_state:
    st.session_state[key] = value if not isinstance(value, list) else []


def _build_conversation_history(*, exclude_latest_user: bool = False) -> list[dict[str, str]]:
  """Prior turns only; the current user message is sent separately as `message`."""
  msgs = st.session_state.messages
  if exclude_latest_user and msgs and msgs[-1].get("role") == "user":
    msgs = msgs[:-1]
  history: list[dict[str, str]] = []
  for msg in msgs:
    role = msg.get("role")
    content = (msg.get("content") or "").strip()
    if role in ("user", "assistant") and content:
      history.append({"role": role, "content": content})
  return history


def post_incident(message: str, conversation_history: list[dict[str, str]] | None = None) -> dict:
  payload: dict = {"message": message}
  if conversation_history:
    payload["conversation_history"] = conversation_history
  resp = httpx.post(
    f"{API_URL}/incident",
    json=payload,
    timeout=180.0,
  )
  resp.raise_for_status()
  return resp.json()


def post_approve(incident_id: str) -> dict:
  resp = httpx.post(
    f"{API_URL}/approve",
    json={"incident_id": incident_id},
    timeout=30.0,
  )
  resp.raise_for_status()
  return resp.json()


def _answer_text(meta: dict) -> str:
  if _is_clarifying_turn(meta):
    return meta.get("root_cause") or meta.get("sanitized_response", "")
  if not meta.get("is_db_related", True):
    return meta.get("sanitized_response") or meta.get("root_cause", "")
  if meta.get("is_informational") or meta.get("error_type") == "informational":
    return meta.get("root_cause") or meta.get("sanitized_response", "")
  if not meta.get("requires_approval", False):
    return meta.get("root_cause") or meta.get("sanitized_response", "")
  return meta.get("sanitized_response") or meta.get("root_cause", "")


def _is_clarifying_turn(meta: dict) -> bool:
  return float(meta.get("confidence", 1.0)) < 0.55 and bool(meta.get("is_vague", False))


def _show_metadata(meta: dict) -> bool:
  if _is_clarifying_turn(meta):
    return False
  if not meta.get("requires_approval", False):
    return False
  service = (meta.get("service") or "").strip()
  error_type = (meta.get("error_type") or "").strip()
  if service in ("unknown", "N/A", ""):
    return False
  if error_type in ("unknown", "N/A", "", "informational"):
    return False
  return True


def _show_fallback_banner(meta: dict) -> bool:
  confidence = float(meta.get("confidence", 0.0))
  if meta.get("is_vague") or confidence < 0.55:
    return False
  if not meta.get("is_db_related", True):
    return False
  if not meta.get("used_fallback"):
    return False
  if meta.get("is_informational"):
    return confidence < 0.60
  return confidence < 0.80


def queue_user_message(user_input: str) -> None:
  user_input = user_input.strip()
  if not user_input:
    return
  st.session_state.messages.append({"role": "user", "content": user_input})
  st.session_state.api_pending = user_input
  st.session_state.steps_revealed = False
  st.session_state.latest_incident = None
  st.rerun()


def complete_api_response(message: str) -> None:
  history = _build_conversation_history(exclude_latest_user=True)
  try:
    with st.spinner("Analyzing incident..."):
      data = post_incident(message, conversation_history=history)
  except httpx.ConnectError:
    st.session_state.messages.pop()
    st.error(
      f"Cannot reach API at `{API_URL}`. "
      f"Start the API: `uvicorn api.main:app --reload --port {API_PORT}`"
    )
    return
  except Exception as exc:
    st.session_state.messages.pop()
    st.error(f"Request failed: {exc}")
    return

  st.session_state.latest_incident = data
  summary = _answer_text(data) or "Analysis complete."
  st.session_state.messages.append(
    {
      "role": "assistant",
      "content": summary,
      "meta": data,
    }
  )


st.title("AI Incident Resolution")
st.caption(
  "Multi-agent diagnosis for database connection failures — "
  "remediation steps require engineer approval when an active incident is detected."
)

for msg in st.session_state.messages:
  with st.chat_message(msg["role"]):
    meta = msg.get("meta")
    content = msg["content"]
    if meta and msg["role"] == "assistant":
      content = _answer_text(meta) or content

    st.markdown(content)

    if meta and msg["role"] == "assistant" and not _is_clarifying_turn(meta):
      requires_approval = bool(meta.get("requires_approval", False))
      confidence = float(meta.get("confidence", 0.0))

      if _show_metadata(meta):
        st.caption(
          f"Service: {meta.get('service')} | "
          f"Error type: {meta.get('error_type')} | "
          f"Severity: {meta.get('severity')} | "
          f"Confidence: {confidence:.2f}"
        )

      if _show_fallback_banner(meta):
        st.info(
          "ℹ️ This answer was reasoned from general engineering knowledge — "
          "no matching runbook was found in the knowledge base. The diagnosis "
          "is based on known behavior of the specific tools mentioned. "
          "Verify critical steps against official documentation before applying."
        )

      with st.expander("Agent trace", expanded=False):
        for line in meta.get("trace", []):
          st.text(line)

      if meta.get("blocked"):
        st.error("Incident blocked by Security Agent. No remediation steps available.")
      elif requires_approval and not st.session_state.steps_revealed:
        st.info("Remediation steps are locked until you approve the analysis.")
        incident_id = meta.get("incident_id")
        if incident_id and st.button("Approve & Show Fix Steps", key=f"approve_{incident_id}"):
          try:
            approved = post_approve(incident_id)
            st.session_state.steps_revealed = True
            st.session_state.approved_payload = approved
            st.success("Approved — remediation steps revealed below.")
            steps = approved.get("recommended_steps", [])
            if steps:
              st.markdown("**Remediation steps (advisory only):**")
              for i, step in enumerate(steps, 1):
                st.markdown(f"{i}. {step}")
            flagged = meta.get("flagged_steps", [])
            if flagged:
              st.warning("Flagged steps: " + "; ".join(flagged))
          except Exception as exc:
            st.error(f"Approval failed: {exc}")
      elif requires_approval and st.session_state.steps_revealed:
        steps = meta.get("recommended_steps", [])
        latest = st.session_state.latest_incident or meta
        if latest.get("human_approved") or st.session_state.steps_revealed:
          approve_data = st.session_state.get("approved_payload")
          steps = (approve_data or {}).get("recommended_steps") or steps
        if steps:
          st.markdown("**Remediation steps (advisory only):**")
          for i, step in enumerate(steps, 1):
            st.markdown(f"{i}. {step}")

if st.session_state.api_pending:
  pending = st.session_state.api_pending
  st.session_state.api_pending = None
  complete_api_response(pending)
  st.rerun()

if prompt := st.chat_input("Describe the database incident..."):
  queue_user_message(prompt)
