from abc import ABC, abstractmethod


class SessionStore(ABC):
    """Stub interface for conversation history and inter-agent shared state. Real implementation lands in Phase 4."""

    @abstractmethod
    def get(self, session_id: str) -> dict: ...

    @abstractmethod
    def update(self, session_id: str, data: dict) -> None: ...
