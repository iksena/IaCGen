"""Google Gemini LLM backend."""
import google.generativeai as genai
from typing import List, Dict

from models.base_llm import BaseLLM
from config import GEMINI_API_KEY, DEFAULT_MAX_TOKENS


class GeminiLLM(BaseLLM):
    """Wraps the Gemini GenerativeModel API.

    Gemini does not support a dedicated system-message role, so system
    content is silently dropped before building the prompt.
    """

    def __init__(self, model_name: str) -> None:
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(model_name)

    def generate(self, conversation_history: List[Dict[str, str]]) -> str:
        # Flatten all non-system messages into a single prompt string.
        prompt = "\n".join(
            msg["content"]
            for msg in conversation_history
            if msg["role"] != "system"
        )
        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=DEFAULT_MAX_TOKENS,
                temperature=0.1,
            ),
        )
        return response.text
