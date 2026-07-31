"""Temporal client connection helpers for bootstrap and worker entry points."""

from __future__ import annotations

from temporalio.client import Client

from engrammesh.bootstrap.settings import TemporalSettings


async def connect_temporal_client(settings: TemporalSettings) -> Client:
    """Connect a Temporal client from typed settings."""
    return await Client.connect(
        settings.address,
        namespace=settings.namespace,
        tls=True if settings.tls else None,
    )
