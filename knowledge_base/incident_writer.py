"""Write resolved incidents back into ChromaDB as new KB documents."""

from datetime import datetime, timezone
from pathlib import Path

from knowledge_base.loader import _get_model, get_collection

RESOLVED_INCIDENTS_DIR = Path(__file__).parent / "docs" / "resolved"


def write_resolved_incident(
  service: str,
  error_type: str,
  severity: str,
  original_message: str,
  root_cause: str,
  recommended_steps: list[str],
  confidence: float,
) -> str:
  """Format a resolved incident, persist to disk, and add to ChromaDB. Returns doc_id."""
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  doc_id = f"resolved_incident_{timestamp}"
  filename = f"{doc_id}.md"
  now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

  steps_block = "\n".join(f"- {step}" for step in recommended_steps) or "- (none recorded)"
  content = f"""# Resolved Incident — {service} {error_type}

**Date:** {now}
**Service:** {service}
**Error Type:** {error_type}
**Severity:** {severity}
**Diagnosis Confidence:** {confidence:.0%}

## Original Report
{original_message}

## Root Cause
{root_cause}

## Resolution Steps (Engineer Approved)
{steps_block}

## Notes
This incident was diagnosed by the AI system and approved by an engineer.
Added to the knowledge base automatically after approval.
"""

  RESOLVED_INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
  filepath = RESOLVED_INCIDENTS_DIR / filename
  filepath.write_text(content, encoding="utf-8")

  collection = get_collection()
  model = _get_model()
  embedding = model.encode([content], normalize_embeddings=True).tolist()

  collection.add(
    ids=[doc_id],
    documents=[content],
    embeddings=embedding,
    metadatas=[
      {
        "source": filename,
        "type": "resolved_incident",
        "service": service,
        "error_type": error_type,
        "timestamp": timestamp,
      }
    ],
  )

  return doc_id
