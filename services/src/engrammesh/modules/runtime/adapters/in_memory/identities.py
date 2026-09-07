"""Default identity generators for in-memory runtime adapters."""

from __future__ import annotations

from typing import final
from uuid import uuid4

from engrammesh.shared.kernel.ids import EventId, ExecutionId


@final
class UuidRuntimeIdentityPort:
    async def new_execution_id(self) -> ExecutionId:
        return ExecutionId(uuid4())

    async def new_event_id(self) -> EventId:
        return EventId(uuid4())
