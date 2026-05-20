"""Pytest configuration — load env and set project root on path."""

import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


@pytest.fixture(scope="session")
def project_root():
  return ROOT
