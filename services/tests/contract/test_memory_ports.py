import inspect
from collections.abc import Mapping
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
from datetime import datetime
from types import TracebackType
from typing import get_protocol_members, get_type_hints

import pytest

from engrammesh.modules.memory import ports
from engrammesh.modules.memory.domain.model import (
    ApprovalStatus,
    Claim,
    ClaimStatus,
    Episode,
    EpistemicKind,
    EvidenceItem,
    EvidencePacket,
    EvidenceRef,
    MemoryScope,
    ProcedureVersion,
    RetentionClass,
    Sensitivity,
    SourceType,
    TemporalStatus,
)
from engrammesh.modules.memory.ports import (
    AppendResult,
    AuthorizationRequest,
    CandidateIndex,
    CandidateSet,
    ClaimProposal,
    ClaimStore,
    ClockPort,
    EntityResolverPort,
    EpisodeStore,
    MemoryAuthorizationPort,
    MemoryExtractorPort,
    MemoryIdentityPort,
    MemoryQuery,
    MemoryRerankerPort,
    MemoryUnitOfWork,
    MemoryUnitOfWorkFactory,
    OutboxEventPublisher,
    OutboxPort,
    OutboxRelayStore,
)
from engrammesh.modules.memory.public import __all__ as public_exports
from engrammesh.shared.kernel.events import EventEnvelope
from engrammesh.shared.kernel.ids import (
    AgentInstanceId,
    ArtifactId,
    EventId,
    MemoryId,
    SubjectId,
    TenantId,
)

PROTOCOLS = (
    EpisodeStore,
    ClaimStore,
    CandidateIndex,
    MemoryAuthorizationPort,
    MemoryExtractorPort,
    EntityResolverPort,
    MemoryRerankerPort,
    MemoryUnitOfWork,
    ClockPort,
    MemoryIdentityPort,
    OutboxPort,
    OutboxRelayStore,
    OutboxEventPublisher,
    MemoryUnitOfWorkFactory,
)

EXPECTED_METHODS = {
    EpisodeStore: ("append", "get", "stream"),
    ClaimStore: ("add_proposal", "current", "history"),
    CandidateIndex: ("search", "upsert", "remove"),
    MemoryAuthorizationPort: ("authorize",),
    MemoryExtractorPort: ("propose",),
    EntityResolverPort: ("propose_matches",),
    MemoryRerankerPort: ("rerank",),
    MemoryUnitOfWork: ("__aenter__", "__aexit__", "commit"),
    ClockPort: ("now",),
    MemoryIdentityPort: ("new_memory_id", "new_event_id"),
    OutboxPort: ("publish",),
    OutboxRelayStore: ("fetch_unpublished", "mark_published", "count_unpublished"),
    OutboxEventPublisher: ("publish",),
    MemoryUnitOfWorkFactory: ("create",),
}

EXPECTED_PROTOCOL_MEMBERS = {
    protocol: frozenset(method_names)
    for protocol, method_names in EXPECTED_METHODS.items()
}
EXPECTED_PROTOCOL_MEMBERS[MemoryUnitOfWork] = frozenset(
    {"__aenter__", "__aexit__", "episodes", "claims", "outbox", "commit"}
)

DATACLASS_SHAPES = {
    MemoryScope: (
        ("tenant_id", TenantId, MISSING),
        ("subject_id", SubjectId, MISSING),
        ("workspace_id", str | None, None),
        ("agent_id", AgentInstanceId | None, None),
    ),
    Episode: (
        ("id", MemoryId, MISSING),
        ("scope", MemoryScope, MISSING),
        ("actor_id", SubjectId, MISSING),
        ("source_type", SourceType, MISSING),
        ("content_ref", ArtifactId, MISSING),
        ("observed_at", datetime, MISSING),
        ("ingested_at", datetime, MISSING),
        ("content_hash", str, MISSING),
        ("idempotency_key", str, MISSING),
        ("sensitivity", Sensitivity, MISSING),
        ("retention_class", RetentionClass, MISSING),
        ("consent_basis", str, MISSING),
    ),
    EvidenceRef: (
        ("episode_id", MemoryId, MISSING),
        ("source_span", str, MISSING),
        ("extractor_version", str, MISSING),
        ("model_ref", str | None, None),
        ("prompt_version", str | None, None),
    ),
    Claim: (
        ("id", MemoryId, MISSING),
        ("scope", MemoryScope, MISSING),
        ("subject", str, MISSING),
        ("predicate", str, MISSING),
        ("object_value", str, MISSING),
        ("polarity", bool, MISSING),
        ("epistemic_kind", EpistemicKind, MISSING),
        ("confidence", float, MISSING),
        ("valid_from", datetime, MISSING),
        ("valid_to", datetime | None, MISSING),
        ("recorded_from", datetime, MISSING),
        ("recorded_to", datetime | None, MISSING),
        ("status", ClaimStatus, MISSING),
        ("evidence", tuple[EvidenceRef, ...], MISSING),
    ),
    ProcedureVersion: (
        ("id", MemoryId, MISSING),
        ("version", int, MISSING),
        ("content_ref", ArtifactId, MISSING),
        ("input_schema", Mapping[str, object], MISSING),
        ("preconditions", tuple[str, ...], MISSING),
        ("evaluation_score", float | None, MISSING),
        ("approval_status", ApprovalStatus, MISSING),
        ("derived_from", tuple[MemoryId, ...], MISSING),
        ("created_by", SubjectId, MISSING),
    ),
    EvidenceItem: (
        ("claim", Claim, MISSING),
        ("temporal_status", TemporalStatus, MISSING),
        ("lexical_score", float, 0.0),
        ("semantic_score", float, 0.0),
        ("temporal_score", float, 0.0),
        ("graph_score", float, 0.0),
        ("rerank_score", float, 0.0),
    ),
    EvidencePacket: (
        ("query_id", str, MISSING),
        ("scope", MemoryScope, MISSING),
        ("items", tuple[EvidenceItem, ...], MISSING),
        ("generated_at", datetime, MISSING),
    ),
    MemoryQuery: (
        ("query_id", str, MISSING),
        ("scope", MemoryScope, MISSING),
        ("text", str, MISSING),
        ("valid_at", datetime | None, None),
        ("recorded_at", datetime | None, None),
        ("limit", int, 10),
    ),
    AppendResult: (
        ("episode_id", MemoryId, MISSING),
        ("created", bool, MISSING),
    ),
    ClaimProposal: (("claim", Claim, MISSING),),
    CandidateSet: (
        ("scope", MemoryScope, MISSING),
        ("items", tuple[EvidenceItem, ...], MISSING),
    ),
    AuthorizationRequest: (
        ("actor_id", SubjectId, MISSING),
        ("scope", MemoryScope, MISSING),
        ("action", str, MISSING),
        ("sensitivity", Sensitivity, MISSING),
    ),
}

EMPTY = inspect.Signature.empty
PARAMETER = inspect.Parameter.POSITIONAL_OR_KEYWORD
KEYWORD_ONLY = inspect.Parameter.KEYWORD_ONLY
PROTOCOL_SIGNATURES = {
    EpisodeStore.append: (
        (("self", EMPTY, EMPTY), ("episode", Episode, EMPTY)),
        AppendResult,
    ),
    EpisodeStore.get: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("episode_id", MemoryId, EMPTY),
        ),
        Episode | None,
    ),
    EpisodeStore.stream: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("cursor", str | None, None),
        ),
        tuple[Episode, ...],
    ),
    ClaimStore.add_proposal: (
        (("self", EMPTY, EMPTY), ("proposal", ClaimProposal, EMPTY)),
        None,
    ),
    ClaimStore.current: (
        (("self", EMPTY, EMPTY), ("query", MemoryQuery, EMPTY)),
        tuple[Claim, ...],
    ),
    ClaimStore.history: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("claim_id", MemoryId, EMPTY),
        ),
        tuple[Claim, ...],
    ),
    CandidateIndex.search: (
        (("self", EMPTY, EMPTY), ("query", MemoryQuery, EMPTY)),
        CandidateSet,
    ),
    CandidateIndex.upsert: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("items", tuple[EvidenceItem, ...], EMPTY),
        ),
        None,
    ),
    CandidateIndex.remove: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("memory_ids", tuple[MemoryId, ...], EMPTY),
        ),
        None,
    ),
    MemoryAuthorizationPort.authorize: (
        (("self", EMPTY, EMPTY), ("request", AuthorizationRequest, EMPTY)),
        bool,
    ),
    MemoryExtractorPort.propose: (
        (("self", EMPTY, EMPTY), ("episode", Episode, EMPTY)),
        tuple[ClaimProposal, ...],
    ),
    EntityResolverPort.propose_matches: (
        (
            ("self", EMPTY, EMPTY),
            ("scope", MemoryScope, EMPTY),
            ("claim", Claim, EMPTY),
        ),
        tuple[MemoryId, ...],
    ),
    MemoryRerankerPort.rerank: (
        (
            ("self", EMPTY, EMPTY),
            ("query", MemoryQuery, EMPTY),
            ("candidates", CandidateSet, EMPTY),
        ),
        EvidencePacket,
    ),
    MemoryUnitOfWork.__aenter__: (
        (("self", EMPTY, EMPTY),),
        MemoryUnitOfWork,
    ),
    MemoryUnitOfWork.__aexit__: (
        (
            ("self", EMPTY, EMPTY),
            ("exc_type", type[BaseException] | None, EMPTY),
            ("exc_value", BaseException | None, EMPTY),
            ("traceback", TracebackType | None, EMPTY),
        ),
        None,
    ),
    MemoryUnitOfWork.commit: (
        (("self", EMPTY, EMPTY),),
        None,
    ),
    ClockPort.now: (
        (("self", EMPTY, EMPTY),),
        datetime,
    ),
    MemoryIdentityPort.new_memory_id: (
        (("self", EMPTY, EMPTY),),
        MemoryId,
    ),
    MemoryIdentityPort.new_event_id: (
        (("self", EMPTY, EMPTY),),
        EventId,
    ),
    OutboxPort.publish: (
        (("self", EMPTY, EMPTY), ("event", EventEnvelope, EMPTY)),
        None,
    ),
    OutboxRelayStore.fetch_unpublished: (
        (("self", EMPTY, EMPTY), ("limit", int, EMPTY)),
        tuple[EventEnvelope, ...],
    ),
    OutboxRelayStore.mark_published: (
        (
            ("self", EMPTY, EMPTY),
            ("event_ids", tuple[EventId, ...], EMPTY),
            ("published_at", datetime, EMPTY),
        ),
        None,
    ),
    OutboxRelayStore.count_unpublished: (
        (("self", EMPTY, EMPTY),),
        int,
    ),
    OutboxEventPublisher.publish: (
        (("self", EMPTY, EMPTY), ("event", EventEnvelope, EMPTY)),
        None,
    ),
    MemoryUnitOfWorkFactory.create: (
        (("self", EMPTY, EMPTY),),
        MemoryUnitOfWork,
    ),
}


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_ports_are_runtime_checkable_protocols(protocol: type[object]) -> None:
    assert protocol._is_protocol  # type: ignore[attr-defined]
    assert protocol._is_runtime_protocol  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("protocol", "method_name"),
    [
        (protocol, method_name)
        for protocol, method_names in EXPECTED_METHODS.items()
        if protocol is not MemoryUnitOfWorkFactory
        for method_name in method_names
    ],
)
def test_all_port_methods_are_coroutine_functions(
    protocol: type[object],
    method_name: str,
) -> None:
    assert inspect.iscoroutinefunction(getattr(protocol, method_name))


def test_unit_of_work_factory_create_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(MemoryUnitOfWorkFactory.create)


@pytest.mark.parametrize(
    ("contract", "expected_fields"),
    DATACLASS_SHAPES.items(),
)
def test_dataclass_fields_have_exact_names_order_and_defaults(
    contract: type[object],
    expected_fields: tuple[tuple[str, object, object], ...],
) -> None:
    actual_fields = fields(contract)
    type_hints = get_type_hints(contract)

    assert tuple(field.name for field in actual_fields) == tuple(
        name for name, _, _ in expected_fields
    )
    for field, (_, expected_annotation, expected_default) in zip(
        actual_fields,
        expected_fields,
        strict=True,
    ):
        assert type_hints[field.name] == expected_annotation
        if expected_default is MISSING:
            assert field.default is MISSING
        else:
            assert type(field.default) is type(expected_default)
            assert field.default == expected_default
        assert field.default_factory is MISSING


@pytest.mark.parametrize(
    ("method", "expected"),
    PROTOCOL_SIGNATURES.items(),
)
def test_protocol_methods_have_exact_signatures(
    method: object,
    expected: tuple[
        tuple[tuple[str, object, object], ...],
        object,
    ],
) -> None:
    expected_parameters, expected_return = expected
    signature = inspect.signature(method, eval_str=True)

    assert tuple(
        (
            parameter.name,
            parameter.annotation,
            parameter.default,
            parameter.kind,
        )
        for parameter in signature.parameters.values()
    ) == tuple(
        (
            name,
            annotation,
            default,
            KEYWORD_ONLY if name != "self" and method in (
                OutboxRelayStore.fetch_unpublished,
                OutboxRelayStore.mark_published,
            )
            else PARAMETER,
        )
        for name, annotation, default in expected_parameters
    )
    assert signature.return_annotation == expected_return


@pytest.mark.parametrize(
    ("protocol", "expected_members"),
    EXPECTED_PROTOCOL_MEMBERS.items(),
)
def test_protocols_have_exact_members(
    protocol: type[object],
    expected_members: frozenset[str],
) -> None:
    assert get_protocol_members(protocol) == expected_members


def test_storage_and_search_methods_are_explicitly_scoped() -> None:
    scoped_parameter_expectations = {
        EpisodeStore.append: ("episode", Episode),
        EpisodeStore.get: ("scope", MemoryScope),
        EpisodeStore.stream: ("scope", MemoryScope),
        ClaimStore.add_proposal: ("proposal", ClaimProposal),
        ClaimStore.current: ("query", MemoryQuery),
        ClaimStore.history: ("scope", MemoryScope),
        CandidateIndex.search: ("query", MemoryQuery),
        CandidateIndex.upsert: ("scope", MemoryScope),
        CandidateIndex.remove: ("scope", MemoryScope),
    }

    for method, (parameter_name, expected_type) in (
        scoped_parameter_expectations.items()
    ):
        hints = get_type_hints(method)
        assert hints[parameter_name] is expected_type

    assert get_type_hints(EpisodeStore.append)["episode"] is Episode
    assert get_type_hints(ClaimStore.add_proposal)["proposal"] is ClaimProposal
    assert get_type_hints(ClaimProposal)["claim"] is Claim
    assert get_type_hints(MemoryQuery)["scope"] is MemoryScope


def test_unit_of_work_exposes_typed_repository_properties() -> None:
    assert isinstance(MemoryUnitOfWork.episodes, property)
    assert isinstance(MemoryUnitOfWork.claims, property)
    assert isinstance(MemoryUnitOfWork.outbox, property)
    assert get_type_hints(MemoryUnitOfWork.episodes.fget)["return"] is EpisodeStore
    assert get_type_hints(MemoryUnitOfWork.claims.fget)["return"] is ClaimStore
    assert get_type_hints(MemoryUnitOfWork.outbox.fget)["return"] is OutboxPort
    declared_properties = {
        name
        for name, member in vars(MemoryUnitOfWork).items()
        if isinstance(member, property)
    }
    assert declared_properties == {"episodes", "claims", "outbox"}
    for property_name, expected_return in (
        ("episodes", EpisodeStore),
        ("claims", ClaimStore),
        ("outbox", OutboxPort),
    ):
        getter = getattr(MemoryUnitOfWork, property_name).fget
        signature = inspect.signature(getter, eval_str=True)
        assert tuple(signature.parameters) == ("self",)
        assert signature.parameters["self"].annotation is EMPTY
        assert signature.parameters["self"].default is EMPTY
        assert signature.parameters["self"].kind is PARAMETER
        assert signature.return_annotation is expected_return


@pytest.mark.parametrize(
    "dto",
    (
        MemoryQuery,
        AppendResult,
        ClaimProposal,
        CandidateSet,
        AuthorizationRequest,
    ),
)
def test_port_dtos_are_frozen_slotted_dataclasses(dto: type[object]) -> None:
    assert is_dataclass(dto)
    assert "__slots__" in dto.__dict__


def test_query_validates_correlation_scope_text_time_and_limit() -> None:
    scope = MemoryScope(
        tenant_id=TenantId.new(),
        subject_id=SubjectId.new(),
    )

    with pytest.raises(ValueError, match="query_id"):
        MemoryQuery(query_id=" ", scope=scope, text="tea")
    with pytest.raises(ValueError, match="text"):
        MemoryQuery(query_id="query-1", scope=scope, text=" ")
    with pytest.raises(ValueError, match="valid_at"):
        MemoryQuery(
            query_id="query-1",
            scope=scope,
            text="tea",
            valid_at=datetime(2026, 7, 27, 10, 0),  # noqa: DTZ001
        )
    with pytest.raises(ValueError, match="limit"):
        MemoryQuery(query_id="query-1", scope=scope, text="tea", limit=0)


def test_port_dtos_are_immutable() -> None:
    result = AppendResult(episode_id=MemoryId.new(), created=True)

    with pytest.raises(FrozenInstanceError):
        result.created = False


def test_application_ports_have_exact_request_shapes() -> None:
    assert get_type_hints(MemoryAuthorizationPort.authorize)[
        "request"
    ] is AuthorizationRequest
    assert get_type_hints(MemoryExtractorPort.propose)["episode"] is Episode
    assert get_type_hints(EntityResolverPort.propose_matches)["scope"] is MemoryScope
    assert get_type_hints(EntityResolverPort.propose_matches)["claim"] is Claim
    assert get_type_hints(MemoryRerankerPort.rerank)["query"] is MemoryQuery
    assert get_type_hints(MemoryRerankerPort.rerank)[
        "candidates"
    ] is CandidateSet
    assert get_type_hints(MemoryRerankerPort.rerank)["return"] is EvidencePacket


def test_reranker_contract_carries_query_correlation_and_scope_end_to_end() -> None:
    query_hints = get_type_hints(MemoryQuery)
    candidate_hints = get_type_hints(CandidateSet)
    packet_hints = get_type_hints(EvidencePacket)

    assert query_hints["query_id"] is str
    assert query_hints["scope"] is MemoryScope
    assert candidate_hints["scope"] is MemoryScope
    assert packet_hints["query_id"] is str
    assert packet_hints["scope"] is MemoryScope


def test_public_surface_exports_only_supported_contracts() -> None:
    domain_exports = {
        "MemoryScope",
        "SourceType",
        "Sensitivity",
        "RetentionClass",
        "Episode",
        "EpistemicKind",
        "ClaimStatus",
        "TemporalStatus",
        "EvidenceRef",
        "Claim",
        "ApprovalStatus",
        "ProcedureVersion",
        "EvidenceItem",
        "EvidencePacket",
    }
    dto_exports = {
        "MemoryQuery",
        "AuthorizationRequest",
        "CandidateSet",
        "ClaimProposal",
    }
    application_exports = {
        "EpisodeAuthorizationDenied",
        "EpisodeIdempotencyConflict",
        "RecordEpisodeCommand",
        "RecordEpisodeResult",
    }

    assert set(public_exports) == domain_exports | dto_exports | application_exports
    assert not {protocol.__name__ for protocol in PROTOCOLS} & set(public_exports)
    assert "AppendResult" not in public_exports


def test_ports_module_does_not_define_a_memory_manager() -> None:
    assert not hasattr(ports, "MemoryManager")


def test_authorization_request_uses_actor_subject() -> None:
    assert get_type_hints(AuthorizationRequest)["actor_id"] is SubjectId
