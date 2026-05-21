"""Track approval and rejection signals per error_type for confidence adjustment."""

import json
from pathlib import Path

FEEDBACK_FILE = Path(__file__).parent.parent / "knowledge_base" / "feedback_store.json"


def _load() -> dict:
  if FEEDBACK_FILE.exists():
    return json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
  return {}


def _save(data: dict) -> None:
  FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
  FEEDBACK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_approval(error_type: str, confidence: float) -> None:
  """Record that an engineer approved a diagnosis for this error_type."""
  data = _load()
  if error_type not in data:
    data[error_type] = {"approvals": 0, "rejections": 0, "total_confidence": 0.0}
  data[error_type]["approvals"] += 1
  data[error_type]["total_confidence"] += confidence
  _save(data)


def record_rejection(error_type: str) -> None:
  """Record that an engineer rejected a diagnosis for this error_type."""
  data = _load()
  if error_type not in data:
    data[error_type] = {"approvals": 0, "rejections": 0, "total_confidence": 0.0}
  data[error_type]["rejections"] += 1
  _save(data)


def get_confidence_adjustment(error_type: str) -> float:
  """
  Return a confidence adjustment (-0.15 to +0.10) based on
  historical approval rate for this error_type.
  """
  data = _load()
  if error_type not in data:
    return 0.0

  record = data[error_type]
  total = record["approvals"] + record["rejections"]
  if total < 3:
    return 0.0

  approval_rate = record["approvals"] / total

  if approval_rate >= 0.85:
    return 0.08
  if approval_rate >= 0.70:
    return 0.04
  if approval_rate <= 0.30:
    return -0.15
  if approval_rate <= 0.50:
    return -0.08
  return 0.0


def get_feedback_summary() -> dict:
  """Return full feedback store for UI display."""
  return _load()
