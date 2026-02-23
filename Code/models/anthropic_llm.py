"""Anthropic Claude LLM backend."""
import anthropic
from typing import List, Dict

from models.base_llm import BaseLLM
from config import CLAUDE_API_KEY, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE


class ClaudeLLM(BaseLLM):
    """Wraps the Anthropic Messages API."""

    def __init__(self, model_name: str) -> None:
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model_name = model_name

    def generate(self, conversation_history: List[Dict[str, str]]) -> str:
        # Claude separates the system prompt from the message list.
        system_content = conversation_history[0]["content"]
        messages = list(conversation_history[1:])

        response = self.client.messages.create(
            model=self.model_name,
            system=system_content,
            messages=messages,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=DEFAULT_TEMPERATURE,
        )
        return response.content[0].text
