"""FastAPI backend — POST /incident, POST /approve, GET /health."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graph.incidents import approve_incident, create_incident
from knowledge_base.loader import warmup_kb


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


class ApproveRequest(BaseModel):
  incident_id: str = Field(..., min_length=1)


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


@app.get("/health")
def health():
  return {"status": "ok"}


@app.post("/incident", response_model=IncidentResponse)
def incident(req: IncidentRequest):
  try:
    history = [turn.model_dump() for turn in req.conversation_history]
    payload = create_incident(req.message, conversation_history=history)
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  except Exception as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
  return IncidentResponse(**payload)


@app.post("/approve", response_model=ApproveResponse)
def approve(req: ApproveRequest):
  try:
    payload = approve_incident(req.incident_id)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  return ApproveResponse(**payload)
