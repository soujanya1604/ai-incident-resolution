"""Shared LLM configuration."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

MODEL_NAME = "gpt-4o-mini"

_llm_cache: dict[float, ChatOpenAI] = {}


def get_llm(temperature: float = 0.2) -> ChatOpenAI:
  api_key = os.getenv("OPENAI_API_KEY")
  if not api_key:
    raise ValueError(
      "OPENAI_API_KEY not set. Copy .env.example to .env and add your key."
    )
  if temperature not in _llm_cache:
    _llm_cache[temperature] = ChatOpenAI(
      model=MODEL_NAME,
      temperature=temperature,
      api_key=api_key,
    )
  return _llm_cache[temperature]
