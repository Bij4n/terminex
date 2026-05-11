"""Provider ABC — all data sources implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..quote import AssetClass, Snapshot


class ProviderError(RuntimeError):
    """Raised when a provider can't produce a snapshot."""


class RateLimitError(ProviderError):
    """Raised when a provider is rate-limited.

    ``retry_after`` is the number of seconds the caller should wait
    before retrying.
    """

    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class Provider(ABC):
    name: str
    asset_class: AssetClass
    # Minimum seconds between fetches regardless of the user's interval.
    # 0 means no floor (follow the user's interval exactly).
    min_poll_interval: float = 0.0

    @abstractmethod
    def fetch(self) -> Snapshot:
        """Fetch a fresh snapshot. Raise ProviderError on failure."""
