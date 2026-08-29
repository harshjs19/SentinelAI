import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

API_BASE_URL_ENV = "SENTINELAI_API_BASE_URL"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class SimulatorConfig:
    """Runtime configuration kept at the external HTTP boundary."""

    api_base_url: str = DEFAULT_API_BASE_URL
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 120.0
    write_timeout_seconds: float = 30.0
    pool_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        normalized = self.api_base_url.rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("SentinelAI API base URL must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("SentinelAI API base URL cannot contain a query or fragment")
        if (
            min(
                self.connect_timeout_seconds,
                self.read_timeout_seconds,
                self.write_timeout_seconds,
                self.pool_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("HTTP timeouts must be positive")
        object.__setattr__(self, "api_base_url", normalized)

    @classmethod
    def from_environment(cls, api_base_url: str | None = None) -> "SimulatorConfig":
        return cls(api_base_url=api_base_url or os.getenv(API_BASE_URL_ENV, DEFAULT_API_BASE_URL))

    def httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )
