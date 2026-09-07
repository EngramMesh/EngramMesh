"""Contract tests for runtime outbox application types and relay store adapters."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
from datetime import datetime
from typing import get_type_hints

import psycopg
import pytest
import pytest_asyncio
from psycopg.types.json import Jsonb
from runtime_outbox_contract import (
    RUNTIME_OUTBOX_CONTRACTS,
    InMemoryRuntimeOutboxRelayHarness,
    RuntimeOutboxContractAssertion,
    RuntimeOutboxRelayHarness,
)

from engrammesh.modules.runtime.adapters.postgres.database import (
    PostgresRuntimeDatabase,
)
from engrammesh.modules.runtime.adapters.postgres.mappers import event_to_row
from engrammesh.modules.runtime.adapters.postgres.outbox_relay import (
    PostgresRuntimeOutboxRelayStore,
)
from engrammesh.modules.runtime.application.contracts import (
    RelayRuntimeOutboxCommand,
    RelayRuntimeOutboxResult,
)
from engrammesh.modules.runtime.ports import RuntimeOutboxPort
from engrammesh.modules.runtime.runtime_state import CommittedRuntimeState
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import EventId

RELAY_COMMAND_FIELDS = (("batch_size", int),)
RELAY_RESULT_FIELDS = (
    ("fetched", int),
    ("dispatched", int),
    ("published", int),
    ("remaining_unpublished", int),
)


@pytest.mark.parametrize(
    ("contract", "expected_fields"),
    (
        (RelayRuntimeOutboxCommand, RELAY_COMMAND_FIELDS),
        (RelayRuntimeOutboxResult, RELAY_RESULT_FIELDS),
    ),
)
def test_runtime_outbox_contracts_have_exact_field_order_annotations_and_no_defaults(
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
    (RelayRuntimeOutboxCommand, RelayRuntimeOutboxResult),
)
def test_runtime_outbox_contracts_are_frozen_slotted_dataclasses(
    contract: type[object],
) -> None:
    assert is_dataclass(contract)
    assert "__slots__" in contract.__dict__
    assert contract.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_runtime_outbox_contracts_are_immutable() -> None:
    command = RelayRuntimeOutboxCommand(batch_size=10)
    result = RelayRuntimeOutboxResult(
        fetched=1,
        dispatched=1,
        published=1,
        remaining_unpublished=0,
    )

    with pytest.raises(FrozenInstanceError):
        command.batch_size = 20
    with pytest.raises(FrozenInstanceError):
        result.published = 0


def test_runtime_outbox_contract_constructors_have_only_declared_parameters() -> None:
    for contract, expected_fields in (
        (RelayRuntimeOutboxCommand, RELAY_COMMAND_FIELDS),
        (RelayRuntimeOutboxResult, RELAY_RESULT_FIELDS),
    ):
        signature = inspect.signature(contract)
        assert tuple(signature.parameters) == tuple(
            name for name, _ in expected_fields
        )
        assert all(
            parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            for parameter in signature.parameters.values()
        )


async def _make_in_memory_harness() -> RuntimeOutboxRelayHarness:
    return InMemoryRuntimeOutboxRelayHarness()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    RUNTIME_OUTBOX_CONTRACTS,
    ids=[case_name for case_name, _ in RUNTIME_OUTBOX_CONTRACTS],
)
async def test_in_memory_runtime_outbox_relay_contract(
    case_name: str,
    assert_contract: RuntimeOutboxContractAssertion,
) -> None:
    del case_name
    await assert_contract(_make_in_memory_harness)


class PostgresRuntimeOutboxRelayHarness:
    """Harness binding relay contracts to the PostgreSQL runtime outbox table."""

    __slots__ = ("_connection", "_database", "_relay_store")

    def __init__(self, dsn: str, connection: psycopg.Connection) -> None:
        self._connection = connection
        self._database = PostgresRuntimeDatabase(dsn)
        self._relay_store = PostgresRuntimeOutboxRelayStore(self._database)

    async def relay_store(self) -> PostgresRuntimeOutboxRelayStore:
        return self._relay_store

    async def publish_unpublished(self, event: EventEnvelope) -> None:
        async def _publish(
            state: CommittedRuntimeState,
            outbox: RuntimeOutboxPort,
        ) -> CommittedRuntimeState:
            await outbox.publish(event)
            return state

        await self._database.write(_publish)

    async def insert_published(
        self,
        event: EventEnvelope,
        *,
        published_at: datetime,
    ) -> None:
        row = event_to_row(event)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runtime_outbox_events (
                    event_id,
                    event_type,
                    schema_version,
                    tenant_id,
                    aggregate_id,
                    aggregate_version,
                    correlation_id,
                    causation_id,
                    occurred_at,
                    payload,
                    published_at
                )
                VALUES (
                    %(event_id)s,
                    %(event_type)s,
                    %(schema_version)s,
                    %(tenant_id)s,
                    %(aggregate_id)s,
                    %(aggregate_version)s,
                    %(correlation_id)s,
                    %(causation_id)s,
                    %(occurred_at)s,
                    %(payload)s,
                    %(published_at)s
                )
                """,
                {
                    **row,
                    "published_at": published_at,
                    "payload": Jsonb(row["payload"]),
                },
            )
        self._connection.commit()

    async def published_at_for(self, event_id: EventId) -> datetime | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT published_at
                FROM runtime_outbox_events
                WHERE event_id = %s
                """,
                (event_id.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return row[0]

    async def close(self) -> None:
        await self._database.close()


@pytest_asyncio.fixture
async def postgres_runtime_outbox_harness(
    postgres_dsn: str,
    postgres_connection: psycopg.Connection,
) -> AsyncIterator[PostgresRuntimeOutboxRelayHarness]:
    harness = PostgresRuntimeOutboxRelayHarness(postgres_dsn, postgres_connection)
    await harness._database.open()
    try:
        yield harness
    finally:
        await harness.close()


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "assert_contract"),
    RUNTIME_OUTBOX_CONTRACTS,
    ids=[case_name for case_name, _ in RUNTIME_OUTBOX_CONTRACTS],
)
async def test_postgres_runtime_outbox_relay_contract(
    case_name: str,
    assert_contract: RuntimeOutboxContractAssertion,
    postgres_runtime_outbox_harness: PostgresRuntimeOutboxRelayHarness,
) -> None:
    del case_name

    async def make_harness() -> RuntimeOutboxRelayHarness:
        return postgres_runtime_outbox_harness

    await assert_contract(make_harness)
