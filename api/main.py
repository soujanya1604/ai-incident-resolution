"""FastAPI backend — POST /incident, POST /approve, GET /health."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.feedback_store import get_feedback_summary, record_approval, record_rejection
from graph.incidents import approve_incident, create_incident, get_incident
from knowledge_base.incident_writer import write_resolved_incident
from knowledge_base.loader import get_collection, warmup_kb

RESOLVED_INCIDENTS_DIR = Path(__file__).resolve().parent.parent / "knowledge_base" / "docs" / "resolved"
KB_WRITE_MIN_CONFIDENCE = 0.60


@asynccontextmanager
async def lifespan(_app: FastAPI):
  warmup_kb()
  yield


app = FastAPI(
  title="AI Incident Resolution API",
  description="Multi-agent database connection failure diagnosis with RAG",
  version="1.0.0",
  lifespan=lifespan,
)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


class ConversationTurn(BaseModel):
  role: str = Field(..., pattern="^(user|assistant)$")
  content: str = Field(..., min_length=1, max_length=8000)


class IncidentRequest(BaseModel):
  message: str = Field(..., min_length=1, max_length=8000)
  conversation_history: list[ConversationTurn] = Field(default_factory=list)
  image_data: str | None = Field(
    default=None,
    description="Hex-encoded PNG image bytes from the UI",
  )


class ApproveRequest(BaseModel):
  incident_id: str = Field(..., min_length=1)


class RejectRequest(BaseModel):
  incident_id: str = Field(..., min_length=1)
  feedback: str = Field(default="", max_length=4000)


class IncidentResponse(BaseModel):
  incident_id: str
  service: str
  error_type: str
  severity: str
  root_cause: str
  confidence: float
  recommended_steps: list[str]
  steps_locked: bool
  human_approved: bool
  sanitized_response: str
  used_fallback: bool
  trace: list[str]
  blocked: bool = False
  flagged_steps: list[str] = []
  is_db_related: bool = True
  is_informational: bool = False
  requires_approval: bool = False
  is_vague: bool = False


class ApproveResponse(BaseModel):
  status: str
  incident_id: str
  final_response: str
  recommended_steps: list[str]
  human_approved: bool
  kb_updated: bool = False
  new_doc_id: str | None = None


class RejectResponse(BaseModel):
  status: str
  incident_id: str
  feedback_recorded: bool = False


class StatsResponse(BaseModel):
  kb_total_documents: int
  resolved_incidents_added: int
  total_approvals: int
  total_rejections: int
  feedback_by_error_type: dict


@app.get("/health")
def health():
  return {"status": "ok"}


@app.get("/stats", response_model=StatsResponse)
def stats():
  collection = get_collection()
  resolved_count = (
    len(list(RESOLVED_INCIDENTS_DIR.glob("*.md")))
    if RESOLVED_INCIDENTS_DIR.exists()
    else 0
  )
  feedback = get_feedback_summary()
  total_approvals = sum(v.get("approvals", 0) for v in feedback.values())
  total_rejections = sum(v.get("rejections", 0) for v in feedback.values())
  return StatsResponse(
    kb_total_documents=collection.count(),
    resolved_incidents_added=resolved_count,
    total_approvals=total_approvals,
    total_rejections=total_rejections,
    feedback_by_error_type=feedback,
  )


@app.post("/incident", response_model=IncidentResponse)
def incident(req: IncidentRequest):
  try:
    message = req.message
    if req.image_data:
      try:
        image_bytes = bytes.fromhex(req.image_data)
      except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid image_data encoding") from exc
      if len(image_bytes) > 5_000_000:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB)")
      message = f"{message}\n\n[Diagnostic image attached ({len(image_bytes)} bytes)]"
    history = [turn.model_dump() for turn in req.conversation_history]
    payload = create_incident(message, conversation_history=history)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except Exception as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
  return IncidentResponse(**payload)


@app.post("/approve", response_model=ApproveResponse)
def approve(req: ApproveRequest):
  try:
    stored = get_incident(req.incident_id)
    if stored is None:
      raise KeyError(f"Unknown incident: {req.incident_id}")

    payload = approve_incident(req.incident_id)
    record_approval(
      error_type=stored.get("error_type", "unknown"),
      confidence=float(stored.get("confidence", 0.0)),
    )

    kb_updated = False
    new_doc_id = None
    confidence = float(stored.get("confidence", 0.0))
    if confidence >= KB_WRITE_MIN_CONFIDENCE:
      new_doc_id = write_resolved_incident(
        service=stored.get("service", "unknown"),
        error_type=stored.get("error_type", "unknown"),
        severity=stored.get("severity", "medium"),
        original_message=stored.get("original_message", ""),
        root_cause=stored.get("root_cause", ""),
        recommended_steps=stored.get("recommended_steps", []),
        confidence=confidence,
      )
      kb_updated = True

    return ApproveResponse(
      **payload,
      kb_updated=kb_updated,
      new_doc_id=new_doc_id,
    )
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/reject", response_model=RejectResponse)
def reject(req: RejectRequest):
  stored = get_incident(req.incident_id)
  if stored is None:
    raise HTTPException(status_code=404, detail="Incident not found")
  feedback_recorded = record_rejection(
    error_type=stored.get("error_type", "unknown"),
    feedback=req.feedback,
  )
  return RejectResponse(
    status="rejected",
    incident_id=req.incident_id,
    feedback_recorded=feedback_recorded,
  )
