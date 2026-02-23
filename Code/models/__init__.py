"""LLM provider factory.

Usage::

    from models import create_llm
    llm = create_llm("claude", "claude-3-7-sonnet-20250219")
    response_text = llm.generate(conversation_history)
"""
from models.base_llm import BaseLLM
from models.gemini_llm import GeminiLLM
from models.openai_llm import OpenAICompatibleLLM
from models.anthropic_llm import ClaudeLLM


def create_llm(llm_type: str, model_name: str) -> BaseLLM:
    """Return the correct LLM backend for *llm_type*.

    Args:
        llm_type:   One of ``"gemini"``, ``"gpt"``, ``"claude"``, ``"deepseek"``.
        model_name: Provider-specific model identifier, e.g. ``"gpt-4o"``.

    Raises:
        ValueError: If *llm_type* is not recognised.
    """
    if llm_type == "gemini":
        return GeminiLLM(model_name)
    if llm_type in ("gpt", "deepseek"):
        return OpenAICompatibleLLM(llm_type, model_name)
    if llm_type == "claude":
        return ClaudeLLM(model_name)
    raise ValueError(
        f"Unsupported LLM type: {llm_type!r}. "
        "Choose from: gemini, gpt, claude, deepseek"
    )
