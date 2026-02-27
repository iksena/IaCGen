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
            self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://openrouter.ai/api/v1"
                if "openrouter" in model_name
                else _DEEPSEEK_BASE_URL)
        else:
            self.client = OpenAI(api_key=CHATGPT_API_KEY)
        self.model_name = model_name.replace("openrouter/", "")  # OpenRouter models are named like "openrouter/gpt-4o"
        self._use_completion_tokens = self.model_name in _COMPLETION_TOKEN_MODELS

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
        print(response)

        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError(
                f"LLM returned no choices for model '{self.model_name}'. "
                f"Response preview: {self._response_preview(response)}"
            )

        message = getattr(choices[0], "message", None)
        if message is None:
            raise RuntimeError(
                f"LLM returned an empty message object for model '{self.model_name}'. "
                f"Response preview: {self._response_preview(response)}"
            )

        content = getattr(message, "content", None)
        if content is None:
            raise RuntimeError(
                f"LLM returned message.content=None for model '{self.model_name}'. "
                f"Response preview: {self._response_preview(response)}"
            )

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
                if text:
                    text_parts.append(text)
            content = "".join(text_parts).strip()

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(
                f"LLM returned empty/non-text content for model '{self.model_name}'. "
                f"Response preview: {self._response_preview(response)}"
            )

        return content

    @staticmethod
    def _response_preview(response) -> str:
        try:
            if hasattr(response, "model_dump_json"):
                preview = response.model_dump_json()
            elif hasattr(response, "model_dump"):
                preview = str(response.model_dump())
            else:
                preview = repr(response)
        except Exception as exc:  # noqa: BLE001
            preview = f"<unavailable: {exc}>"
        return preview[:1000]
