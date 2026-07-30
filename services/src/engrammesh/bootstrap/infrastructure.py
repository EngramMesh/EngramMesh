"""Default bootstrap implementations for memory application ports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import final
from uuid import uuid4

from engrammesh.bootstrap.settings import Environment
from engrammesh.modules.memory.ports import AuthorizationRequest
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import EventId, MemoryId


@final
class SystemUtcClock:
    async def now(self) -> datetime:
        return datetime.now(UTC)


@final
class UuidMemoryIdentityPort:
    async def new_memory_id(self) -> MemoryId:
        return MemoryId(uuid4())

    async def new_event_id(self) -> EventId:
        return EventId(uuid4())


@final
class LoggingOutboxEventPublisher:
    """In-process publisher that records dispatched events for tests."""

    __slots__ = ("_published",)

    def __init__(self) -> None:
        self._published: list[EventEnvelope] = []

    @property
    def published(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._published)

    async def publish(self, event: EventEnvelope) -> None:
        self._published.append(event)


@final
class EnvironmentGatedMemoryAuthorization:
    __slots__ = ("_environment",)

    def __init__(self, environment: Environment) -> None:
        self._environment = environment

    async def authorize(self, request: AuthorizationRequest) -> bool:
        del request
        return self._environment in {
            Environment.DEVELOPMENT,
            Environment.TEST,
        }
