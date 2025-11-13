"""Provider ABC — all data sources implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..quote import AssetClass, Snapshot


class ProviderError(RuntimeError):
    """Raised when a provider can't produce a snapshot."""


class Provider(ABC):
    name: str
    asset_class: AssetClass

    @abstractmethod
    def fetch(self) -> Snapshot:
        """Fetch a fresh snapshot. Raise ProviderError on failure."""
