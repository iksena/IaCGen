"""OpenAI-compatible LLM backend (GPT and DeepSeek).

DeepSeek exposes an OpenAI-compatible REST API, so a single class handles
both providers — the only difference is the base URL and API key used.
"""
from openai import OpenAI
from typing import List, Dict

from models.base_llm import BaseLLM
from config import CHATGPT_API_KEY, DEEPSEEK_API_KEY, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# These models use max_completion_tokens instead of max_tokens.
_COMPLETION_TOKEN_MODELS = {"o3-mini", "o1"}


class OpenAICompatibleLLM(BaseLLM):
    """Works for both OpenAI GPT and DeepSeek models."""

    def __init__(self, llm_type: str, model_name: str) -> None:
        if llm_type == "deepseek":
            self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=_DEEPSEEK_BASE_URL)
        else:
            self.client = OpenAI(api_key=CHATGPT_API_KEY)
        self.model_name = model_name
        self._use_completion_tokens = model_name in _COMPLETION_TOKEN_MODELS

    def generate(self, conversation_history: List[Dict[str, str]]) -> str:
        system_content = conversation_history[0]["content"]
        messages = [{"role": "system", "content": system_content}] + list(conversation_history[1:])

        kwargs: dict = {"model": self.model_name, "messages": messages}
        if self._use_completion_tokens:
            kwargs["max_completion_tokens"] = DEFAULT_MAX_TOKENS
        else:
            kwargs["max_tokens"] = DEFAULT_MAX_TOKENS
            kwargs["temperature"] = DEFAULT_TEMPERATURE

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
