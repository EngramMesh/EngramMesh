import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import Never, Self
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engrammesh.modules.memory.application.contracts import RecordEpisodeCommand
from engrammesh.modules.memory.application.errors import (
    EpisodeAuthorizationDenied,
)
from engrammesh.modules.memory.application.record_episode import (
    RecordEpisodeHandler,
)
from engrammesh.modules.memory.domain.model import (
    Episode,
    MemoryScope,
    RetentionClass,
    Sensitivity,
    SourceType,
)
from engrammesh.modules.memory.ports import AppendResult, AuthorizationRequest
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    CorrelationId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

REPOSITORY_ROOT = Path(__file__).parents[6]
EPISODE_SCHEMA = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "jsonschema"
    / "memory"
    / "v1"
    / "episode-recorded.schema.json"
)
ACTOR_ID = SubjectId(UUID("29ee5d4a-8988-48b9-bd24-e65ba7eb3de5"))
AGENT_ID = AgentInstanceId(UUID("b93676a1-4671-47da-a32e-cd4615588188"))
CONTENT_REF = ArtifactId(UUID("a49f42ec-453a-46ba-98d7-32dda8d6ad7e"))
CORRELATION_ID = CorrelationId(
    UUID("223fdcf1-87da-43f4-b453-02bded156035")
)
EPISODE_ID = MemoryId(UUID("25a36ed6-ac12-43ce-820a-d179d7c79ac9"))
EVENT_ID = EventId(UUID("7ea6087d-7b99-4c2a-8aa5-ff006be3cbaf"))
EXISTING_EPISODE_ID = MemoryId(
    UUID("605fe709-954b-49e7-80c7-a70764127a88")
)
SUBJECT_ID = SubjectId(UUID("436b95a8-df23-4d6e-8200-d2058ad62d86"))
TENANT_ID = TenantId(UUID("2361d58c-5608-418f-9c7a-605793ccb311"))
OBSERVED_AT = datetime(2026, 7, 27, 8, 29, 58, tzinfo=UTC)
INGESTED_AT = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)


def make_command() -> RecordEpisodeCommand:
    return RecordEpisodeCommand(
        correlation_id=CORRELATION_ID,
        actor_id=ACTOR_ID,
        scope=MemoryScope(
            tenant_id=TENANT_ID,
            subject_id=SUBJECT_ID,
            workspace_id="workspace-42",
            agent_id=AGENT_ID,
        ),
        source_type=SourceType.USER,
        content_ref=CONTENT_REF,
        observed_at=OBSERVED_AT,
        content_hash="sha256:88c7355c",
        idempotency_key="episode-42",
        sensitivity=Sensitivity.CONFIDENTIAL,
        retention_class=RetentionClass.STANDARD,
        consent_basis="user_request",
    )


class DenyingAuthorization:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.requests: list[AuthorizationRequest] = []

    async def authorize(self, request: AuthorizationRequest) -> bool:
        self.calls.append("authorize")
        self.requests.append(request)
        return False


class AllowingAuthorization(DenyingAuthorization):
    async def authorize(self, request: AuthorizationRequest) -> bool:
        self.calls.append("authorize")
        self.requests.append(request)
        return True


class FailingAuthorization(DenyingAuthorization):
    def __init__(self, calls: list[str], error: BaseException) -> None:
        super().__init__(calls)
        self.error = error

    async def authorize(self, request: AuthorizationRequest) -> bool:
        self.calls.append("authorize")
        self.requests.append(request)
        raise self.error


class MustNotBeUsed:
    def __getattr__(self, name: str) -> Never:
        msg = f"unexpected dependency access: {name}"
        raise AssertionError(msg)


class AdapterFailure(RuntimeError):
    pass


class FixedClock:
    def __init__(
        self,
        calls: list[str],
        *,
        value: datetime = INGESTED_AT,
        error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.value = value
        self.error = error
        self.call_count = 0

    async def now(self) -> datetime:
        self.calls.append("clock.now")
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.value


class FixedIdentities:
    def __init__(
        self,
        calls: list[str],
        *,
        memory_error: BaseException | None = None,
        event_error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.memory_error = memory_error
        self.event_error = event_error
        self.memory_call_count = 0
        self.event_call_count = 0

    async def new_memory_id(self) -> MemoryId:
        self.calls.append("identities.new_memory_id")
        self.memory_call_count += 1
        if self.memory_error is not None:
            raise self.memory_error
        return EPISODE_ID

    async def new_event_id(self) -> EventId:
        self.calls.append("identities.new_event_id")
        self.event_call_count += 1
        if self.event_error is not None:
            raise self.event_error
        return EVENT_ID


class RecordingEpisodeStore:
    def __init__(
        self,
        calls: list[str],
        result: AppendResult | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.result = result or AppendResult(episode_id=EPISODE_ID, created=True)
        self.error = error
        self.episodes: list[Episode] = []

    async def append(self, episode: Episode) -> AppendResult:
        self.calls.append("episodes.append")
        self.episodes.append(episode)
        if self.error is not None:
            raise self.error
        return self.result


class RecordingOutbox:
    def __init__(
        self,
        calls: list[str],
        error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.error = error
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self.calls.append("outbox.publish")
        self.events.append(event)
        if self.error is not None:
            raise self.error


class RecordingUnitOfWork:
    def __init__(
        self,
        calls: list[str],
        *,
        append_result: AppendResult | None = None,
        append_error: BaseException | None = None,
        outbox_error: BaseException | None = None,
        enter_error: BaseException | None = None,
        commit_error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.episode_store = RecordingEpisodeStore(
            calls,
            append_result,
            append_error,
        )
        self.outbox_adapter = RecordingOutbox(calls, outbox_error)
        self.enter_error = enter_error
        self.commit_error = commit_error
        self.commit_count = 0
        self.successful_commit_count = 0
        self.exit_arguments: list[
            tuple[
                type[BaseException] | None,
                BaseException | None,
                TracebackType | None,
            ]
        ] = []

    async def __aenter__(self) -> Self:
        self.calls.append("uow.enter")
        if self.enter_error is not None:
            raise self.enter_error
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.calls.append("uow.exit")
        self.exit_arguments.append((exc_type, exc_value, traceback))

    @property
    def episodes(self) -> RecordingEpisodeStore:
        self.calls.append("uow.episodes")
        return self.episode_store

    @property
    def claims(self) -> Never:
        raise AssertionError("claim store must not be accessed")

    @property
    def outbox(self) -> RecordingOutbox:
        self.calls.append("uow.outbox")
        return self.outbox_adapter

    async def commit(self) -> None:
        self.calls.append("uow.commit")
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error
        self.successful_commit_count += 1


class FixedUnitOfWorkFactory:
    def __init__(
        self,
        calls: list[str],
        unit_of_work: RecordingUnitOfWork,
        error: BaseException | None = None,
    ) -> None:
        self.calls = calls
        self.unit_of_work = unit_of_work
        self.error = error
        self.call_count = 0

    def create(self) -> RecordingUnitOfWork:
        self.calls.append("uow_factory.create")
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.unit_of_work


def event_document(event: EventEnvelope) -> dict[str, object]:
    payload = dict(event.payload)
    scope = payload["scope"]
    assert isinstance(scope, Mapping)
    payload["scope"] = dict(scope)
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "tenant_id": str(event.tenant_id),
        "aggregate_id": str(event.aggregate_id),
        "aggregate_version": event.aggregate_version,
        "correlation_id": str(event.correlation_id),
        "causation_id": (
            str(event.causation_id) if event.causation_id is not None else None
        ),
        "occurred_at": event.occurred_at.isoformat(),
        "payload": payload,
    }


@pytest.mark.asyncio
async def test_denial_authorizes_first_and_accesses_nothing_else() -> None:
    calls: list[str] = []
    authorization = DenyingAuthorization(calls)
    command = make_command()
    handler = RecordEpisodeHandler(
        authorization=authorization,
        clock=MustNotBeUsed(),
        identities=MustNotBeUsed(),
        unit_of_work_factory=MustNotBeUsed(),
    )

    with pytest.raises(EpisodeAuthorizationDenied) as raised:
        await handler.handle(command)

    assert raised.value.args == ()
    assert authorization.requests == [
        AuthorizationRequest(
            actor_id=command.actor_id,
            scope=command.scope,
            action="record_episode",
            sensitivity=command.sensitivity,
        )
    ]
    assert calls == ["authorize"]


@pytest.mark.asyncio
async def test_first_write_records_episode_publishes_exact_v1_event_and_commits(
) -> None:
    calls: list[str] = []
    authorization = AllowingAuthorization(calls)
    clock = FixedClock(calls)
    identities = FixedIdentities(calls)
    unit_of_work = RecordingUnitOfWork(calls)
    factory = FixedUnitOfWorkFactory(calls, unit_of_work)
    command = make_command()
    handler = RecordEpisodeHandler(
        authorization=authorization,
        clock=clock,
        identities=identities,
        unit_of_work_factory=factory,
    )

    result = await handler.handle(command)

    assert result.episode_id == EPISODE_ID
    assert result.created is True
    assert unit_of_work.episode_store.episodes == [
        Episode(
            id=EPISODE_ID,
            scope=command.scope,
            actor_id=ACTOR_ID,
            source_type=SourceType.USER,
            content_ref=CONTENT_REF,
            observed_at=OBSERVED_AT,
            ingested_at=INGESTED_AT,
            content_hash="sha256:88c7355c",
            idempotency_key="episode-42",
            sensitivity=Sensitivity.CONFIDENTIAL,
            retention_class=RetentionClass.STANDARD,
            consent_basis="user_request",
        )
    ]
    assert len(unit_of_work.outbox_adapter.events) == 1
    document = event_document(unit_of_work.outbox_adapter.events[0])
    assert document == {
        "event_id": str(EVENT_ID),
        "event_type": "memory.episode-recorded",
        "schema_version": 1,
        "tenant_id": str(TENANT_ID),
        "aggregate_id": str(EPISODE_ID),
        "aggregate_version": 1,
        "correlation_id": str(CORRELATION_ID),
        "causation_id": None,
        "occurred_at": INGESTED_AT.isoformat(),
        "payload": {
            "episode_id": str(EPISODE_ID),
            "scope": {
                "subject_id": str(SUBJECT_ID),
                "workspace_id": "workspace-42",
                "agent_id": str(AGENT_ID),
            },
            "actor_id": str(ACTOR_ID),
            "source_type": "user",
            "content_ref": str(CONTENT_REF),
            "observed_at": OBSERVED_AT.isoformat(),
            "ingested_at": INGESTED_AT.isoformat(),
            "content_hash": "sha256:88c7355c",
            "idempotency_key": "episode-42",
            "sensitivity": "confidential",
            "retention_class": "standard",
            "consent_basis": "user_request",
        },
    }
    schema_value = json.loads(EPISODE_SCHEMA.read_text(encoding="utf-8"))
    assert isinstance(schema_value, Mapping)
    Draft202012Validator(
        schema_value,
        format_checker=FormatChecker(),
    ).validate(document)
    assert clock.call_count == 1
    assert identities.memory_call_count == 1
    assert identities.event_call_count == 1
    assert factory.call_count == 1
    assert unit_of_work.commit_count == 1
    assert unit_of_work.exit_arguments == [(None, None, None)]
    assert calls == [
        "authorize",
        "clock.now",
        "identities.new_memory_id",
        "uow_factory.create",
        "uow.enter",
        "uow.episodes",
        "episodes.append",
        "identities.new_event_id",
        "uow.outbox",
        "outbox.publish",
        "uow.commit",
        "uow.exit",
    ]


@pytest.mark.asyncio
async def test_aware_second_offsets_are_canonicalized_to_utc_and_schema_valid(
) -> None:
    calls: list[str] = []
    observed_at = datetime(
        2026,
        7,
        27,
        14,
        0,
        tzinfo=timezone(timedelta(hours=5, minutes=30, seconds=45)),
    )
    ingested_at = datetime(
        2026,
        7,
        27,
        2,
        0,
        tzinfo=timezone(-timedelta(hours=3, minutes=15, seconds=30)),
    )
    command = replace(make_command(), observed_at=observed_at)
    unit_of_work = RecordingUnitOfWork(calls)
    handler = RecordEpisodeHandler(
        authorization=AllowingAuthorization(calls),
        clock=FixedClock(calls, value=ingested_at),
        identities=FixedIdentities(calls),
        unit_of_work_factory=FixedUnitOfWorkFactory(calls, unit_of_work),
    )

    await handler.handle(command)

    expected_observed_at = observed_at.astimezone(UTC)
    expected_ingested_at = ingested_at.astimezone(UTC)
    episode = unit_of_work.episode_store.episodes[0]
    event = unit_of_work.outbox_adapter.events[0]
    document = event_document(event)

    assert episode.observed_at == expected_observed_at
    assert episode.ingested_at == expected_ingested_at
    assert event.occurred_at == expected_ingested_at
    assert document["occurred_at"] == expected_ingested_at.isoformat()
    payload = document["payload"]
    assert isinstance(payload, Mapping)
    assert payload["observed_at"] == expected_observed_at.isoformat()
    assert payload["ingested_at"] == expected_ingested_at.isoformat()
    schema_value = json.loads(EPISODE_SCHEMA.read_text(encoding="utf-8"))
    assert isinstance(schema_value, Mapping)
    Draft202012Validator(
        schema_value,
        format_checker=FormatChecker(),
    ).validate(document)


@pytest.mark.asyncio
async def test_naive_clock_is_rejected_before_identity_or_uow() -> None:
    calls: list[str] = []
    handler = RecordEpisodeHandler(
        authorization=AllowingAuthorization(calls),
        clock=FixedClock(
            calls,
            value=datetime(2026, 7, 27, 8, 30),  # noqa: DTZ001
        ),
        identities=MustNotBeUsed(),
        unit_of_work_factory=MustNotBeUsed(),
    )

    with pytest.raises(ValueError, match="clock now must be timezone-aware"):
        await handler.handle(make_command())

    assert calls == ["authorize", "clock.now"]


@pytest.mark.asyncio
async def test_duplicate_returns_existing_id_without_event_and_still_commits(
) -> None:
    calls: list[str] = []
    authorization = AllowingAuthorization(calls)
    clock = FixedClock(calls)
    identities = FixedIdentities(calls)
    unit_of_work = RecordingUnitOfWork(
        calls,
        append_result=AppendResult(
            episode_id=EXISTING_EPISODE_ID,
            created=False,
        ),
    )
    factory = FixedUnitOfWorkFactory(calls, unit_of_work)
    handler = RecordEpisodeHandler(
        authorization=authorization,
        clock=clock,
        identities=identities,
        unit_of_work_factory=factory,
    )

    result = await handler.handle(make_command())

    assert result.episode_id == EXISTING_EPISODE_ID
    assert result.created is False
    assert identities.event_call_count == 0
    assert unit_of_work.outbox_adapter.events == []
    assert unit_of_work.commit_count == 1
    assert unit_of_work.exit_arguments == [(None, None, None)]
    assert calls == [
        "authorize",
        "clock.now",
        "identities.new_memory_id",
        "uow_factory.create",
        "uow.enter",
        "uow.episodes",
        "episodes.append",
        "uow.commit",
        "uow.exit",
    ]


@pytest.mark.asyncio
async def test_created_id_mismatch_fails_before_event_or_commit() -> None:
    calls: list[str] = []
    authorization = AllowingAuthorization(calls)
    clock = FixedClock(calls)
    identities = FixedIdentities(calls)
    unit_of_work = RecordingUnitOfWork(
        calls,
        append_result=AppendResult(
            episode_id=EXISTING_EPISODE_ID,
            created=True,
        ),
    )
    factory = FixedUnitOfWorkFactory(calls, unit_of_work)
    handler = RecordEpisodeHandler(
        authorization=authorization,
        clock=clock,
        identities=identities,
        unit_of_work_factory=factory,
    )

    with pytest.raises(RuntimeError) as raised:
        await handler.handle(make_command())

    assert identities.event_call_count == 0
    assert unit_of_work.outbox_adapter.events == []
    assert unit_of_work.commit_count == 0
    assert len(unit_of_work.exit_arguments) == 1
    exc_type, exc_value, traceback = unit_of_work.exit_arguments[0]
    assert exc_type is RuntimeError
    assert exc_value is raised.value
    assert traceback is not None
    assert calls == [
        "authorize",
        "clock.now",
        "identities.new_memory_id",
        "uow_factory.create",
        "uow.enter",
        "uow.episodes",
        "episodes.append",
        "uow.exit",
    ]


@pytest.mark.parametrize(
    ("failure_point", "expected_calls"),
    (
        ("authorization", ["authorize"]),
        ("clock", ["authorize", "clock.now"]),
        (
            "memory_id",
            ["authorize", "clock.now", "identities.new_memory_id"],
        ),
        (
            "domain",
            ["authorize", "clock.now"],
        ),
        (
            "factory",
            [
                "authorize",
                "clock.now",
                "identities.new_memory_id",
                "uow_factory.create",
            ],
        ),
        (
            "enter",
            [
                "authorize",
                "clock.now",
                "identities.new_memory_id",
                "uow_factory.create",
                "uow.enter",
            ],
        ),
    ),
)
@pytest.mark.asyncio
async def test_pretransaction_failures_propagate_without_commit(
    failure_point: str,
    expected_calls: list[str],
) -> None:
    calls: list[str] = []
    failure = AdapterFailure(failure_point)
    authorization = (
        FailingAuthorization(calls, failure)
        if failure_point == "authorization"
        else AllowingAuthorization(calls)
    )
    clock = FixedClock(
        calls,
        value=(
            datetime(2026, 7, 27, 8, 30)  # noqa: DTZ001
            if failure_point == "domain"
            else INGESTED_AT
        ),
        error=failure if failure_point == "clock" else None,
    )
    identities = FixedIdentities(
        calls,
        memory_error=failure if failure_point == "memory_id" else None,
    )
    unit_of_work = RecordingUnitOfWork(
        calls,
        enter_error=failure if failure_point == "enter" else None,
    )
    factory = FixedUnitOfWorkFactory(
        calls,
        unit_of_work,
        error=failure if failure_point == "factory" else None,
    )
    handler = RecordEpisodeHandler(
        authorization=authorization,
        clock=clock,
        identities=identities,
        unit_of_work_factory=factory,
    )

    expected_error = ValueError if failure_point == "domain" else AdapterFailure
    with pytest.raises(expected_error) as raised:
        await handler.handle(make_command())

    if failure_point != "domain":
        assert raised.value is failure
    assert unit_of_work.commit_count == 0
    assert unit_of_work.successful_commit_count == 0
    assert unit_of_work.outbox_adapter.events == []
    assert unit_of_work.exit_arguments == []
    assert calls == expected_calls


@pytest.mark.parametrize(
    ("failure_point", "expected_calls", "commit_attempts"),
    (
        (
            "append",
            [
                "authorize",
                "clock.now",
                "identities.new_memory_id",
                "uow_factory.create",
                "uow.enter",
                "uow.episodes",
                "episodes.append",
                "uow.exit",
            ],
            0,
        ),
        (
            "event_id",
            [
                "authorize",
                "clock.now",
                "identities.new_memory_id",
                "uow_factory.create",
                "uow.enter",
                "uow.episodes",
                "episodes.append",
                "identities.new_event_id",
                "uow.exit",
            ],
            0,
        ),
        (
            "outbox",
            [
                "authorize",
                "clock.now",
                "identities.new_memory_id",
                "uow_factory.create",
                "uow.enter",
                "uow.episodes",
                "episodes.append",
                "identities.new_event_id",
                "uow.outbox",
                "outbox.publish",
                "uow.exit",
            ],
            0,
        ),
        (
            "commit",
            [
                "authorize",
                "clock.now",
                "identities.new_memory_id",
                "uow_factory.create",
                "uow.enter",
                "uow.episodes",
                "episodes.append",
                "identities.new_event_id",
                "uow.outbox",
                "outbox.publish",
                "uow.commit",
                "uow.exit",
            ],
            1,
        ),
    ),
)
@pytest.mark.asyncio
async def test_transaction_failures_reach_uow_exit_without_successful_commit(
    failure_point: str,
    expected_calls: list[str],
    commit_attempts: int,
) -> None:
    calls: list[str] = []
    failure = AdapterFailure(failure_point)
    authorization = AllowingAuthorization(calls)
    clock = FixedClock(calls)
    identities = FixedIdentities(
        calls,
        event_error=failure if failure_point == "event_id" else None,
    )
    unit_of_work = RecordingUnitOfWork(
        calls,
        append_error=failure if failure_point == "append" else None,
        outbox_error=failure if failure_point == "outbox" else None,
        commit_error=failure if failure_point == "commit" else None,
    )
    factory = FixedUnitOfWorkFactory(calls, unit_of_work)
    handler = RecordEpisodeHandler(
        authorization=authorization,
        clock=clock,
        identities=identities,
        unit_of_work_factory=factory,
    )

    with pytest.raises(AdapterFailure) as raised:
        await handler.handle(make_command())

    assert raised.value is failure
    assert unit_of_work.commit_count == commit_attempts
    assert unit_of_work.successful_commit_count == 0
    assert len(unit_of_work.exit_arguments) == 1
    exc_type, exc_value, traceback = unit_of_work.exit_arguments[0]
    assert exc_type is AdapterFailure
    assert exc_value is failure
    assert traceback is not None
    assert calls == expected_calls
