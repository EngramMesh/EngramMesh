"""Application orchestration for recording immutable memory episodes."""

from datetime import UTC, datetime
from typing import final

from engrammesh.modules.memory.application.contracts import (
    RecordEpisodeCommand,
    RecordEpisodeResult,
)
from engrammesh.modules.memory.application.errors import (
    EpisodeAuthorizationDenied,
)
from engrammesh.modules.memory.domain.model import Episode
from engrammesh.modules.memory.ports import (
    AuthorizationRequest,
    ClockPort,
    MemoryAuthorizationPort,
    MemoryIdentityPort,
    MemoryUnitOfWorkFactory,
)
from engrammesh.shared.kernel.events import EventEnvelope


def _canonical_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


@final
class RecordEpisodeHandler:
    """Authorize and record one immutable cognitive-memory episode."""

    def __init__(
        self,
        *,
        authorization: MemoryAuthorizationPort,
        clock: ClockPort,
        identities: MemoryIdentityPort,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
    ) -> None:
        self._authorization = authorization
        self._clock = clock
        self._identities = identities
        self._unit_of_work_factory = unit_of_work_factory

    async def handle(
        self,
        command: RecordEpisodeCommand,
    ) -> RecordEpisodeResult:
        """Record an authorized episode or return its idempotent replay."""
        authorized = await self._authorization.authorize(
            AuthorizationRequest(
                actor_id=command.actor_id,
                scope=command.scope,
                action="record_episode",
                sensitivity=command.sensitivity,
            )
        )
        if not authorized:
            raise EpisodeAuthorizationDenied()

        ingested_at = _canonical_utc(await self._clock.now(), "clock now")
        observed_at = _canonical_utc(command.observed_at, "observed_at")
        episode_id = await self._identities.new_memory_id()
        episode = Episode(
            id=episode_id,
            scope=command.scope,
            actor_id=command.actor_id,
            source_type=command.source_type,
            content_ref=command.content_ref,
            observed_at=observed_at,
            ingested_at=ingested_at,
            content_hash=command.content_hash,
            idempotency_key=command.idempotency_key,
            sensitivity=command.sensitivity,
            retention_class=command.retention_class,
            consent_basis=command.consent_basis,
        )

        async with self._unit_of_work_factory.create() as unit_of_work:
            append_result = await unit_of_work.episodes.append(episode)
            if (
                append_result.created
                and append_result.episode_id != episode.id
            ):
                msg = "created episode ID does not match generated episode ID"
                raise RuntimeError(msg)
            if append_result.created:
                event_id = await self._identities.new_event_id()
                await unit_of_work.outbox.publish(
                    EventEnvelope(
                        event_id=event_id,
                        event_type="memory.episode-recorded",
                        schema_version=1,
                        tenant_id=command.scope.tenant_id,
                        aggregate_id=append_result.episode_id,
                        aggregate_version=1,
                        correlation_id=command.correlation_id,
                        causation_id=None,
                        occurred_at=ingested_at,
                        payload={
                            "episode_id": str(append_result.episode_id),
                            "scope": {
                                "subject_id": str(command.scope.subject_id),
                                "workspace_id": command.scope.workspace_id,
                                "agent_id": (
                                    str(command.scope.agent_id)
                                    if command.scope.agent_id is not None
                                    else None
                                ),
                            },
                            "actor_id": str(command.actor_id),
                            "source_type": command.source_type.value,
                            "content_ref": str(command.content_ref),
                            "observed_at": observed_at.isoformat(),
                            "ingested_at": ingested_at.isoformat(),
                            "content_hash": command.content_hash,
                            "idempotency_key": command.idempotency_key,
                            "sensitivity": command.sensitivity.value,
                            "retention_class": command.retention_class.value,
                            "consent_basis": command.consent_basis,
                        },
                    )
                )
            await unit_of_work.commit()

        return RecordEpisodeResult(
            episode_id=append_result.episode_id,
            created=append_result.created,
        )
