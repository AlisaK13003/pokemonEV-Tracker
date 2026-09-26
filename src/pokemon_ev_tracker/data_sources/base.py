"""Common interfaces for tracker data backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DataSourceSnapshot:
    """Small diagnostic snapshot exposed to the UI."""

    backend_name: str
    connected: bool
    details: Mapping[str, Any]


class GameDataSource(ABC):
    """Runtime source for game state or backend diagnostics."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend name."""

    @abstractmethod
    def start(self) -> None:
        """Start any background listeners needed by the backend."""

    @abstractmethod
    def stop(self) -> None:
        """Stop background backend work."""

    @abstractmethod
    def snapshot(self) -> DataSourceSnapshot:
        """Return the latest backend diagnostics."""
