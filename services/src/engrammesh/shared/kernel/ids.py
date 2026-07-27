"""Strongly typed UUID identifiers."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class UUIDValue:
    """An immutable UUID-backed value object."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            msg = "value must be a UUID"
            raise TypeError(msg)

    @classmethod
    def new(cls) -> Self:
        """Create a new identifier of the concrete class."""
        return cls(uuid4())

    def __str__(self) -> str:
        """Return the canonical UUID text representation."""
        return str(self.value)


class TenantId(UUIDValue):
    __slots__ = ()


class SubjectId(UUIDValue):
    __slots__ = ()


class AgentDefinitionId(UUIDValue):
    __slots__ = ()


class AgentInstanceId(UUIDValue):
    __slots__ = ()


class ExecutionId(UUIDValue):
    __slots__ = ()


class NodeId(UUIDValue):
    __slots__ = ()


class AttemptId(UUIDValue):
    __slots__ = ()


class EffectId(UUIDValue):
    __slots__ = ()


class EventId(UUIDValue):
    __slots__ = ()


class CorrelationId(UUIDValue):
    __slots__ = ()


class ArtifactId(UUIDValue):
    __slots__ = ()


class MemoryId(UUIDValue):
    __slots__ = ()
