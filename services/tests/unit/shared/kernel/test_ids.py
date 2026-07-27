from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from engrammesh.shared.kernel.ids import (
    AgentDefinitionId,
    AgentInstanceId,
    ArtifactId,
    AttemptId,
    CorrelationId,
    EffectId,
    EventId,
    ExecutionId,
    MemoryId,
    NodeId,
    SubjectId,
    TenantId,
    UUIDValue,
)

ID_TYPES = (
    UUIDValue,
    TenantId,
    SubjectId,
    AgentDefinitionId,
    AgentInstanceId,
    ExecutionId,
    NodeId,
    AttemptId,
    EffectId,
    EventId,
    CorrelationId,
    ArtifactId,
    MemoryId,
)


@pytest.mark.parametrize("id_type", ID_TYPES)
def test_id_rejects_non_uuid_values(id_type: type[UUIDValue]) -> None:
    with pytest.raises(TypeError, match="UUID"):
        id_type("550e8400-e29b-41d4-a716-446655440000")  # type: ignore[arg-type]


@pytest.mark.parametrize("id_type", ID_TYPES)
def test_new_id_retains_its_concrete_type(id_type: type[UUIDValue]) -> None:
    generated = id_type.new()

    assert type(generated) is id_type
    assert isinstance(generated.value, UUID)


def test_id_string_uses_canonical_uuid_representation() -> None:
    value = UUID("550E8400-E29B-41D4-A716-446655440000")

    assert str(TenantId(value)) == "550e8400-e29b-41d4-a716-446655440000"


def test_new_ids_are_unique() -> None:
    assert EventId.new() != EventId.new()


def test_ids_are_immutable() -> None:
    identifier = SubjectId.new()

    with pytest.raises(FrozenInstanceError):
        identifier.value = UUID("550e8400-e29b-41d4-a716-446655440000")
