"""Streamlit Cloud entrypoint — starts FastAPI in a subprocess, then runs the UI."""

from __future__ import annotations

import atexit
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = os.getenv("API_PORT", "8001")
DEFAULT_API_URL = f"http://localhost:{API_PORT}"


def _secrets_to_env(secrets: dict[str, Any], parent_key: str = "") -> None:
  """Map Streamlit secrets (flat or nested TOML) into os.environ."""
  for key, value in secrets.items():
    env_key = f"{parent_key}_{key}" if parent_key else str(key)
    if isinstance(value, dict):
      _secrets_to_env(value, env_key)
    else:
      os.environ.setdefault(env_key.upper(), str(value))


def apply_environment() -> None:
  from dotenv import load_dotenv

  load_dotenv(ROOT / ".env")
  try:
    _secrets_to_env(dict(st.secrets))
  except Exception:
    pass
  os.environ.setdefault("API_PORT", API_PORT)
  os.environ.setdefault("API_URL", DEFAULT_API_URL)


def _wait_for_api(timeout_sec: float = 180.0) -> bool:
  health_url = f"http://{API_HOST}:{API_PORT}/health"
  deadline = time.monotonic() + timeout_sec
  while time.monotonic() < deadline:
    try:
      resp = httpx.get(health_url, timeout=3.0)
      if resp.status_code == 200:
        return True
    except (httpx.HTTPError, OSError):
      pass
    time.sleep(0.5)
  return False


def _terminate_process(proc: subprocess.Popen) -> None:
  if proc.poll() is not None:
    return
  proc.terminate()
  try:
    proc.wait(timeout=8)
  except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait(timeout=5)


@st.cache_resource
def _start_api_server() -> subprocess.Popen:
  env = os.environ.copy()
  env.setdefault("API_URL", DEFAULT_API_URL)
  env.setdefault("API_PORT", API_PORT)

  cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "api.main:app",
    "--host",
    API_HOST,
    "--port",
    API_PORT,
  ]
  proc = subprocess.Popen(
    cmd,
    cwd=str(ROOT),
    env=env,
  )

  atexit.register(lambda: _terminate_process(proc))

  if not _wait_for_api():
    _terminate_process(proc)
    raise RuntimeError(
      f"FastAPI backend did not become healthy at http://{API_HOST}:{API_PORT}/health "
      f"within 180 seconds. Check Streamlit logs for uvicorn errors."
    )

  return proc


def ensure_api_running() -> None:
  proc = _start_api_server()
  if proc.poll() is not None:
    _start_api_server.clear()
    proc = _start_api_server()
  os.environ["API_URL"] = DEFAULT_API_URL
  os.environ["API_PORT"] = API_PORT


apply_environment()

try:
  ensure_api_running()
except RuntimeError as exc:
  st.error(str(exc))
  st.stop()

runpy.run_path(str(ROOT / "ui" / "app.py"), run_name="__main__")
