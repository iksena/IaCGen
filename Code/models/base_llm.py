"""Abstract base class for all LLM provider backends."""
from abc import ABC, abstractmethod
from typing import List, Dict


class BaseLLM(ABC):
    """Common interface every LLM adapter must implement.

    A *conversation_history* is a list of message dicts, each with:
    - ``"role"``    – ``"system"``, ``"user"``, or ``"assistant"``
    - ``"content"`` – the message text
    """

    @abstractmethod
    def generate(self, conversation_history: List[Dict[str, str]]) -> str:
        """Call the underlying model and return its raw text response."""
        raise NotImplementedError
