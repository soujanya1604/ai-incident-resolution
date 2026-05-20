"""Enhanced Streamlit UI — chat history, inline image upload, human approval gate."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")
try:
  for _key, _value in st.secrets.items():
    if not isinstance(_value, dict):
      os.environ.setdefault(str(_key).upper(), str(_value))
except Exception:
  pass

API_PORT = os.getenv("API_PORT", "8001")
API_URL = os.getenv("API_URL", f"http://localhost:{API_PORT}").rstrip("/")

DB_PATH = Path.home() / ".ai_incident_resolution" / "history.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("""
    CREATE TABLE IF NOT EXISTS chats (
      id TEXT PRIMARY KEY,
      title TEXT,
      created_at TEXT,
      updated_at TEXT,
      messages TEXT
    )
  """)
  cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      chat_id TEXT,
      role TEXT,
      content TEXT,
      meta TEXT,
      timestamp TEXT,
      FOREIGN KEY (chat_id) REFERENCES chats(id)
    )
  """)
  conn.commit()
  conn.close()


init_db()

st.set_page_config(
  page_title="AI Incident Resolution",
  page_icon="🔧",
  layout="wide",
  initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2rem;
    border-radius: 12px;
    color: white;
    margin-bottom: 2rem;
  }
  .main-header h1 { margin: 0; font-size: 2.5rem; }
  .main-header p { margin: 0.5rem 0 0 0; font-size: 1.1rem; opacity: 0.9; }
  .stat-card {
    background: #f0f4f8;
    padding: 1rem;
    border-radius: 8px;
    text-align: center;
    border-left: 4px solid #667eea;
  }
  .image-preview {
    max-height: 300px;
    border-radius: 8px;
    margin: 0.5rem 0;
  }
  .image-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.75rem 0.5rem;
    background: #e8f4f8;
    border-radius: 6px;
    font-size: 1.25rem;
    color: #0088cc;
    min-height: 3rem;
  }
</style>
""", unsafe_allow_html=True)

_DEFAULTS = {
  "messages": [],
  "api_pending": None,
  "latest_incident": None,
  "steps_revealed": False,
  "approved_payload": None,
  "current_chat_id": None,
  "uploaded_image": None,
  "chat_history_list": [],
}

for key, value in _DEFAULTS.items():
  if key not in st.session_state:
    st.session_state[key] = value if not isinstance(value, list) else []


def get_chat_history_list() -> list[tuple[str, str, str]]:
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
    "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC LIMIT 20"
  )
  chats = cursor.fetchall()
  conn.close()
  return chats


def ensure_chat_session() -> None:
  if st.session_state.current_chat_id:
    return
  chat_id = datetime.now().strftime("%Y%m%d_%H%M%S")
  title = f"Incident Analysis {datetime.now().strftime('%Y-%m-%d %H:%M')}"
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
    """
    INSERT INTO chats (id, title, created_at, updated_at, messages)
    VALUES (?, ?, ?, ?, ?)
    """,
    (chat_id, title, datetime.now().isoformat(), datetime.now().isoformat(), "[]"),
  )
  conn.commit()
  conn.close()
  st.session_state.current_chat_id = chat_id


def create_new_chat() -> None:
  chat_id = datetime.now().strftime("%Y%m%d_%H%M%S")
  title = f"Incident Analysis {datetime.now().strftime('%Y-%m-%d %H:%M')}"
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
    """
    INSERT INTO chats (id, title, created_at, updated_at, messages)
    VALUES (?, ?, ?, ?, ?)
    """,
    (chat_id, title, datetime.now().isoformat(), datetime.now().isoformat(), "[]"),
  )
  conn.commit()
  conn.close()
  st.session_state.current_chat_id = chat_id
  st.session_state.messages = []
  st.session_state.latest_incident = None
  st.session_state.steps_revealed = False
  st.session_state.approved_payload = None
  st.session_state.uploaded_image = None
  st.rerun()


def load_chat(chat_id: str) -> None:
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("SELECT messages FROM chats WHERE id = ?", (chat_id,))
  result = cursor.fetchone()
  conn.close()
  if result:
    st.session_state.current_chat_id = chat_id
    st.session_state.messages = json.loads(result[0]) if result[0] else []
    st.session_state.latest_incident = None
    st.session_state.steps_revealed = False
    st.session_state.approved_payload = None
    st.rerun()


def save_chat() -> None:
  if st.session_state.current_chat_id:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
      """
      UPDATE chats SET messages = ?, updated_at = ?
      WHERE id = ?
      """,
      (
        json.dumps(st.session_state.messages),
        datetime.now().isoformat(),
        st.session_state.current_chat_id,
      ),
    )
    conn.commit()
    conn.close()


def clear_cache() -> None:
  for key, value in _DEFAULTS.items():
    st.session_state[key] = value if not isinstance(value, list) else []
  st.rerun()


def _build_conversation_history(*, exclude_latest_user: bool = False) -> list[dict[str, str]]:
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


def post_incident(
  message: str,
  conversation_history: list[dict[str, str]] | None = None,
  image_data: str | None = None,
) -> dict:
  payload: dict = {"message": message}
  if conversation_history:
    payload["conversation_history"] = conversation_history
  if image_data:
    payload["image_data"] = image_data
  resp = httpx.post(f"{API_URL}/incident", json=payload, timeout=180.0)
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


def queue_user_message(user_input: str, image_data: str | None = None) -> None:
  user_input = user_input.strip()
  if not user_input:
    return
  msg_obj: dict = {"role": "user", "content": user_input}
  if image_data:
    msg_obj["image_data"] = image_data
  st.session_state.messages.append(msg_obj)
  st.session_state.api_pending = user_input
  st.session_state.steps_revealed = False
  st.session_state.latest_incident = None
  st.rerun()


def complete_api_response(message: str, image_data: str | None = None) -> None:
  history = _build_conversation_history(exclude_latest_user=True)
  try:
    with st.spinner("Analyzing incident..."):
      data = post_incident(message, conversation_history=history, image_data=image_data)
  except httpx.ConnectError:
    st.session_state.messages.pop()
    st.error(
      f"Cannot reach the API at `{API_URL}`. "
      "Use `streamlit run streamlit_app.py` or start the API with "
      f"`uvicorn api.main:app --port {API_PORT}`."
    )
    return
  except httpx.TimeoutException:
    st.session_state.messages.pop()
    st.error(
      "The API request timed out. The backend may still be loading — wait and try again."
    )
    return
  except Exception as exc:
    st.session_state.messages.pop()
    st.error(f"Request failed: {exc}")
    return

  st.session_state.latest_incident = data
  summary = _answer_text(data) or "Analysis complete."
  st.session_state.messages.append(
    {"role": "assistant", "content": summary, "meta": data}
  )
  save_chat()


# Sidebar
with st.sidebar:
  st.markdown("### Chat Management")

  col1, col2, col3 = st.columns(3)
  with col1:
    if st.button("New Chat", use_container_width=True):
      create_new_chat()
  with col2:
    if st.button("Clear Cache", use_container_width=True):
      clear_cache()
  with col3:
    if st.button("Re-run", use_container_width=True):
      st.rerun()

  st.divider()
  st.markdown("### Chat History")
  chat_history = get_chat_history_list()

  if chat_history:
    for chat_id, title, _updated_at in chat_history:
      prefix = ">> " if chat_id == st.session_state.current_chat_id else ""
      if st.button(f"{prefix}{title}", use_container_width=True, key=f"load_{chat_id}"):
        load_chat(chat_id)
  else:
    st.info("No chat history yet. Start a new chat to begin.")

  st.divider()
  if st.session_state.messages:
    col1, col2 = st.columns(2)
    with col1:
      user_msgs = sum(1 for m in st.session_state.messages if m.get("role") == "user")
      st.metric("Messages", len(st.session_state.messages), f"{user_msgs} user")
    with col2:
      if st.session_state.latest_incident:
        confidence = float(st.session_state.latest_incident.get("confidence", 0.0))
        st.metric("Confidence", f"{confidence:.0%}")


# Main content
st.markdown("""
<div class="main-header">
  <h1>AI Incident Resolution</h1>
  <p>Multi-agent diagnosis for database connection failures</p>
</div>
""", unsafe_allow_html=True)

st.caption(
  "Describe your database incident and attach diagnostic images below the chat box. "
  "Remediation steps require engineer approval when critical incidents are detected."
)

for msg in st.session_state.messages:
  with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
    meta = msg.get("meta")
    content = msg["content"]
    if meta and msg["role"] == "assistant":
      content = _answer_text(meta) or content

    st.markdown(content)

    if msg.get("image_data") and msg["role"] == "user":
      try:
        image_bytes = io.BytesIO(bytes.fromhex(msg["image_data"]))
        img = Image.open(image_bytes)
        st.image(img, use_container_width=True, caption="Attached image")
      except Exception:
        st.text("[Image attachment]")

    if meta and msg["role"] == "assistant" and not _is_clarifying_turn(meta):
      requires_approval = bool(meta.get("requires_approval", False))
      confidence = float(meta.get("confidence", 0.0))

      if _show_metadata(meta):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
          st.caption(f"**Service:** {meta.get('service')}")
        with col2:
          st.caption(f"**Error type:** {meta.get('error_type')}")
        with col3:
          st.caption(f"**Severity:** {meta.get('severity')}")
        with col4:
          st.caption(f"**Confidence:** {confidence:.0%}")

      if _show_fallback_banner(meta):
        st.info(
          "Fallback response — no matching runbook found. "
          "Verify against official documentation before applying."
        )

      with st.expander("Agent Trace", expanded=False):
        for line in meta.get("trace", []):
          st.code(line, language="text")

      if meta.get("blocked"):
        st.error("Incident blocked by Security Agent. No remediation available.")
      elif requires_approval and not st.session_state.steps_revealed:
        st.warning("Remediation steps are locked until you approve the analysis.")
        incident_id = meta.get("incident_id")
        if incident_id and st.button(
          "Approve & Unlock Fix Steps",
          key=f"approve_{incident_id}",
          use_container_width=True,
          type="primary",
        ):
          try:
            with st.spinner("Processing approval..."):
              approved = post_approve(incident_id)
            st.session_state.steps_revealed = True
            st.session_state.approved_payload = approved
            st.success("Approved — remediation steps revealed.")
            steps = approved.get("recommended_steps", [])
            if steps:
              st.markdown("### Remediation Steps (Advisory Only)")
              for i, step in enumerate(steps, 1):
                st.markdown(f"**{i}.** {step}")
            flagged = meta.get("flagged_steps", [])
            if flagged:
              st.warning(f"Flagged steps: {'; '.join(flagged)}")
            st.rerun()
          except httpx.ConnectError:
            st.error(f"Cannot reach the API at `{API_URL}`.")
          except Exception as exc:
            st.error(f"Approval failed: {exc}")
      elif requires_approval and st.session_state.steps_revealed:
        approve_data = st.session_state.get("approved_payload")
        steps = (approve_data or {}).get("recommended_steps") or meta.get(
          "recommended_steps", []
        )
        if steps:
          st.markdown("### Remediation Steps (Advisory Only)")
          for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")


if st.session_state.api_pending:
  pending = st.session_state.api_pending
  image_data = None
  if st.session_state.messages:
    image_data = st.session_state.messages[-1].get("image_data")
  st.session_state.api_pending = None
  complete_api_response(pending, image_data=image_data)
  st.rerun()


# Input area — image upload + chat input with indicator
st.divider()
st.markdown("### Report Incident")

uploaded_file = st.file_uploader(
  "Add diagnostic image",
  type=["jpg", "jpeg", "png"],
  key="image_uploader",
  help="PNG or JPG, max 1024×1024 after compression",
)

if uploaded_file:
  try:
    img = Image.open(uploaded_file)
    img.thumbnail((1024, 1024))
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    st.session_state.uploaded_image = img_bytes.getvalue().hex()
    st.success(f"Image attached: {uploaded_file.name}")
    st.image(img, use_container_width=True, caption="Preview")
    if st.button("Remove image", key="remove_image"):
      st.session_state.uploaded_image = None
      st.rerun()
  except Exception as e:
    st.error(f"Failed to process image: {e}")

if st.session_state.uploaded_image:
  col_input, col_icon = st.columns([0.92, 0.08])
  with col_icon:
    st.markdown("<div class='image-indicator' title='Image attached'>📸</div>", unsafe_allow_html=True)
  with col_input:
    user_input = st.chat_input(
      "Describe the database incident (timeouts, auth failures, query errors)...",
      key="chat_input",
    )
else:
  user_input = st.chat_input(
    "Describe the database incident (timeouts, auth failures, query errors)...",
    key="chat_input",
  )

if user_input:
  ensure_chat_session()
  queue_user_message(user_input, image_data=st.session_state.uploaded_image)
  st.session_state.uploaded_image = None
