"""Temporal client connection settings and helpers."""

from __future__ import annotations

from dataclasses import dataclass

from temporalio.client import Client


@dataclass(frozen=True, slots=True)
class TemporalConnectionSettings:
    """Adapter-local Temporal connection boundary."""

    address: str
    namespace: str
    tls: bool = False


async def connect_temporal_client(
    settings: TemporalConnectionSettings,
) -> Client:
    """Connect a Temporal client from adapter-local settings."""
    return await Client.connect(
        settings.address,
        namespace=settings.namespace,
        tls=True if settings.tls else None,
    )
