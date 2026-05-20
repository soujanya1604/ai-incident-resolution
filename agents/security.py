"""Security Agent — input validation, secret masking, unsafe step flags."""

import re

from agents.state import AgentState, append_trace

# Input blocklist patterns (case-insensitive)
INPUT_BLOCK_PATTERNS = [
  re.compile(r"ignore\s+previous\s+instructions", re.I),
  re.compile(r"\bdrop\s+table\b", re.I),
  re.compile(r"\bdelete\s+from\b", re.I),
  re.compile(r"\btruncate\b", re.I),
  re.compile(r"\bexecute\b", re.I),
  re.compile(r"\brun\s+command\b", re.I),
  re.compile(r"\bshell\b", re.I),
]

# Secret masking patterns
AWS_KEY_RE = re.compile(
  r"(AWS_(?:SECRET|ACCESS)_KEY\s*[=:]\s*)(\S+)", re.I
)
PASSWORD_RE = re.compile(
  r"((?:password|pwd)\s*(?:[=:]|is)\s*)(\S+)", re.I
)
TOKEN_RE = re.compile(
  r"((?:token|bearer)\s*[=:]\s*)(\S+)", re.I
)
CONN_STRING_RE = re.compile(
  r"(postgresql://[^:]+:)([^@]+)(@)",
  re.I,
)

DESTRUCTIVE_STEP_KEYWORDS = ("delete", "drop", "truncate")


def validate_input(message: str) -> tuple[bool, str]:
  """Return (blocked, reason). blocked=True means do not run RCA pipeline."""
  text = message.strip()
  for pattern in INPUT_BLOCK_PATTERNS:
    if pattern.search(text):
      return True, f"blocked pattern: {pattern.pattern}"
  return False, ""


def mask_secrets(text: str) -> str:
  if not text:
    return text
  text = AWS_KEY_RE.sub(r"\1****", text)
  text = PASSWORD_RE.sub(r"\1****", text)
  text = TOKEN_RE.sub(r"\1****", text)
  text = CONN_STRING_RE.sub(r"\1****\3", text)
  return text


def audit_steps(steps: list[str]) -> tuple[list[str], list[str]]:
  """Flag steps with destructive keywords. Returns (steps, flagged_indices_messages)."""
  flagged: list[str] = []
  for i, step in enumerate(steps):
    lower = step.lower()
    if any(kw in lower for kw in DESTRUCTIVE_STEP_KEYWORDS):
      flagged.append(f"Step {i + 1} flagged (destructive language): {step[:80]}")
  return steps, flagged


def build_sanitized_response(state: AgentState) -> str:
  parts = [
    f"Service: {state.get('service', 'unknown')}",
    f"Error type: {state.get('error_type', 'unknown')}",
    f"Severity: {state.get('severity', 'medium')}",
    f"Root cause: {state.get('root_cause', 'N/A')}",
    f"Confidence: {state.get('confidence', 0.0):.2f}",
  ]
  if state.get("used_fallback"):
    parts.append("Note: General knowledge fallback was used (weak KB match).")
  flagged = state.get("flagged_steps", [])
  if flagged:
    parts.append("Warnings: " + "; ".join(flagged))
  return mask_secrets("\n".join(parts))


def security_node(state: AgentState) -> dict:
  """Final security pass — mask output and flag unsafe recommendations."""
  trail = append_trace(state, "Security", "reviewing response for secrets and unsafe steps")

  steps = list(state.get("recommended_steps", []))
  steps, flagged = audit_steps(steps)

  sanitized_steps = [mask_secrets(s) for s in steps]
  root_cause = mask_secrets(state.get("root_cause", ""))

  updated: AgentState = {
    **state,
    "recommended_steps": sanitized_steps,
    "root_cause": root_cause,
    "flagged_steps": flagged,
  }
  sanitized = build_sanitized_response(updated)
  updated["sanitized_response"] = sanitized

  if flagged:
    trail = append_trace(
      {**updated, "trace": trail},
      "Security",
      f"flagged {len(flagged)} potentially unsafe step(s)",
    )
  else:
    trail = append_trace(
      {**updated, "trace": trail},
      "Security",
      "response sanitized; no destructive steps flagged",
    )

  return {
    "recommended_steps": sanitized_steps,
    "root_cause": root_cause,
    "flagged_steps": flagged,
    "sanitized_response": sanitized,
    "trace": trail,
  }
