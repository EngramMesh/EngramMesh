"""Validates structural invariants for memory.episode-recorded inbox events."""

from collections.abc import Mapping
from typing import final

from engrammesh.shared.kernel.events import EventEnvelope

_EPISODE_RECORDED = "memory.episode-recorded"
_REQUIRED_PAYLOAD_FIELDS = (
    "episode_id",
    "scope",
    "actor_id",
    "source_type",
    "content_ref",
    "observed_at",
    "ingested_at",
    "content_hash",
    "idempotency_key",
    "sensitivity",
    "retention_class",
    "consent_basis",
)
_REQUIRED_SCOPE_FIELDS = ("subject_id",)


@final
class EpisodeRecordedProcessor:
    def supports(self, event_type: str) -> bool:
        return event_type == _EPISODE_RECORDED

    async def process(self, event: EventEnvelope) -> None:
        if event.event_type != _EPISODE_RECORDED:
            msg = f"expected event_type {_EPISODE_RECORDED!r}"
            raise ValueError(msg)
        if event.schema_version != 1:
            msg = "schema_version must be 1"
            raise ValueError(msg)
        payload = event.payload
        for field in _REQUIRED_PAYLOAD_FIELDS:
            if field not in payload:
                msg = f"payload missing required field {field!r}"
                raise ValueError(msg)
        if str(event.aggregate_id) != str(payload["episode_id"]):
            msg = "aggregate_id must match payload episode_id"
            raise ValueError(msg)
        scope = payload["scope"]
        if not isinstance(scope, Mapping):
            msg = "payload.scope must be an object"
            raise TypeError(msg)
        if "tenant_id" in scope:
            msg = "payload.scope must not contain tenant_id"
            raise ValueError(msg)
        for field in _REQUIRED_SCOPE_FIELDS:
            if field not in scope:
                msg = f"payload.scope missing required field {field!r}"
                raise ValueError(msg)
