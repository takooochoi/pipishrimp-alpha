from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Small environment-backed configuration surface for local Alpha development."""

    cors_origins: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> Settings:
        raw_origins = os.getenv(
            "PIPISHRIMP_CORS_ORIGINS",
            "http://localhost:8081,http://localhost:19006,http://10.0.2.2:8000",
        )
        origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())
        return cls(cors_origins=origins)


settings = Settings.from_environment()
