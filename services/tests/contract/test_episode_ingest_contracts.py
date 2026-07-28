import inspect
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, datetime
from typing import get_type_hints

import pytest

from engrammesh.modules.memory import public as memory_public
from engrammesh.modules.memory.application.contracts import (
    RecordEpisodeCommand,
    RecordEpisodeResult,
)
from engrammesh.modules.memory.application.errors import (
    EpisodeAuthorizationDenied,
)
from engrammesh.modules.memory.domain.errors import EpisodeIdempotencyConflict
from engrammesh.modules.memory.domain.model import (
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.shared.kernel.ids import (
    ArtifactId,
    CorrelationId,
    MemoryId,
    SubjectId,
    TenantId,
)

COMMAND_FIELDS = (
    ("correlation_id", CorrelationId),
    ("actor_id", SubjectId),
    ("scope", MemoryScope),
    ("source_type", SourceType),
    ("content_ref", ArtifactId),
    ("observed_at", datetime),
    ("content_hash", str),
    ("idempotency_key", str),
    ("sensitivity", Sensitivity),
    ("retention_class", RetentionClass),
    ("consent_basis", str),
)


def make_command() -> RecordEpisodeCommand:
    return RecordEpisodeCommand(
        correlation_id=CorrelationId.new(),
        actor_id=SubjectId.new(),
        scope=MemoryScope(
            tenant_id=TenantId.new(),
            subject_id=SubjectId.new(),
        ),
        source_type=SourceType.USER,
        content_ref=ArtifactId.new(),
        observed_at=datetime(2026, 7, 27, 10, 30, tzinfo=UTC),
        content_hash="sha256:episode",
        idempotency_key="episode-1",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


@pytest.mark.parametrize(
    ("contract", "expected_fields"),
    (
        (RecordEpisodeCommand, COMMAND_FIELDS),
        (
            RecordEpisodeResult,
            (("episode_id", MemoryId), ("created", bool)),
        ),
    ),
)
def test_episode_contracts_have_exact_field_order_annotations_and_no_defaults(
    contract: type[object],
    expected_fields: tuple[tuple[str, object], ...],
) -> None:
    actual_fields = fields(contract)
    type_hints = get_type_hints(contract)

    assert tuple(field.name for field in actual_fields) == tuple(
        name for name, _ in expected_fields
    )
    for field, (_, expected_annotation) in zip(
        actual_fields,
        expected_fields,
        strict=True,
    ):
        assert type_hints[field.name] is expected_annotation
        assert field.default is MISSING
        assert field.default_factory is MISSING


@pytest.mark.parametrize(
    "contract",
    (RecordEpisodeCommand, RecordEpisodeResult),
)
def test_episode_contracts_are_frozen_slotted_dataclasses(
    contract: type[object],
) -> None:
    assert is_dataclass(contract)
    assert "__slots__" in contract.__dict__
    assert contract.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_episode_contracts_are_immutable() -> None:
    command = make_command()
    result = RecordEpisodeResult(episode_id=MemoryId.new(), created=True)

    with pytest.raises(FrozenInstanceError):
        command.content_hash = "changed"
    with pytest.raises(FrozenInstanceError):
        result.created = False


def test_record_episode_command_rejects_naive_observed_at() -> None:
    command = make_command()

    with pytest.raises(ValueError, match="observed_at"):
        replace(
            command,
            observed_at=datetime(2026, 7, 27, 10, 30),  # noqa: DTZ001
        )


@pytest.mark.parametrize(
    "field_name",
    ("content_hash", "idempotency_key", "consent_basis"),
)
def test_record_episode_command_rejects_blank_required_text(
    field_name: str,
) -> None:
    command = make_command()

    with pytest.raises(ValueError, match=field_name):
        replace(command, **{field_name: " \t"})


def test_episode_authorization_denied_is_final_permission_error() -> None:
    assert issubclass(EpisodeAuthorizationDenied, PermissionError)
    assert EpisodeAuthorizationDenied.__bases__ == (PermissionError,)
    assert EpisodeAuthorizationDenied.__final__


def test_episode_authorization_denied_retains_no_sensitive_input() -> None:
    class CommandLikePayload:
        content_hash = "sensitive-content-hash"
        consent_basis = "sensitive-consent-basis"

    sentinel = CommandLikePayload()

    with pytest.raises(TypeError):
        EpisodeAuthorizationDenied(sentinel)
    with pytest.raises(TypeError):
        EpisodeAuthorizationDenied(command=sentinel)

    error = EpisodeAuthorizationDenied()

    assert tuple(inspect.signature(EpisodeAuthorizationDenied).parameters) == ()
    assert error.args == ()
    assert vars(error) == {}
    assert not hasattr(error, "command")
    assert sentinel not in error.args
    assert sentinel not in vars(error).values()


def test_memory_public_exports_episode_application_contracts() -> None:
    expected_exports = {
        "EpisodeAuthorizationDenied",
        "EpisodeIdempotencyConflict",
        "RecordEpisodeCommand",
        "RecordEpisodeResult",
    }

    assert expected_exports <= set(memory_public.__all__)
    assert memory_public.RecordEpisodeCommand is RecordEpisodeCommand
    assert memory_public.RecordEpisodeResult is RecordEpisodeResult
    assert memory_public.EpisodeAuthorizationDenied is EpisodeAuthorizationDenied
    assert (
        memory_public.EpisodeIdempotencyConflict
        is EpisodeIdempotencyConflict
    )


def test_episode_idempotency_conflict_is_final_value_error() -> None:
    assert issubclass(EpisodeIdempotencyConflict, ValueError)
    assert EpisodeIdempotencyConflict.__bases__ == (ValueError,)
    assert EpisodeIdempotencyConflict.__final__


def test_episode_idempotency_conflict_retains_no_sensitive_input() -> None:
    class EpisodeLikePayload:
        content_hash = "sensitive-content-hash"
        consent_basis = "sensitive-consent-basis"

    sentinel = EpisodeLikePayload()

    with pytest.raises(TypeError):
        EpisodeIdempotencyConflict(sentinel)
    with pytest.raises(TypeError):
        EpisodeIdempotencyConflict(episode=sentinel)

    error = EpisodeIdempotencyConflict()

    assert tuple(inspect.signature(EpisodeIdempotencyConflict).parameters) == ()
    assert error.args == ()
    assert vars(error) == {}
    assert not hasattr(error, "episode")
    assert sentinel not in error.args
    assert sentinel not in vars(error).values()


def test_memory_public_does_not_export_episode_infrastructure() -> None:
    prohibited_exports = {
        "ClockPort",
        "MemoryIdentityPort",
        "MemoryUnitOfWork",
        "MemoryUnitOfWorkFactory",
        "OutboxPort",
        "EpisodeStore",
        "ClaimStore",
    }

    assert not prohibited_exports & set(memory_public.__all__)
    assert not prohibited_exports & set(vars(memory_public))


def test_episode_contract_constructors_have_only_declared_parameters() -> None:
    for contract, expected_fields in (
        (RecordEpisodeCommand, COMMAND_FIELDS),
        (
            RecordEpisodeResult,
            (("episode_id", MemoryId), ("created", bool)),
        ),
    ):
        signature = inspect.signature(contract)
        assert tuple(signature.parameters) == tuple(
            name for name, _ in expected_fields
        )
        assert all(
            parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            for parameter in signature.parameters.values()
        )
