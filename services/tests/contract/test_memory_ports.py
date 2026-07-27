import inspect
from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
from datetime import datetime
from types import TracebackType
from typing import get_type_hints

import pytest

from engrammesh.modules.memory import ports
from engrammesh.modules.memory.domain.model import (
    Claim,
    Episode,
    EvidenceItem,
    EvidencePacket,
    EvidenceRef,
    MemoryScope,
    ProcedureVersion,
)
from engrammesh.modules.memory.ports import (
    AppendResult,
    AuthorizationRequest,
    CandidateIndex,
    CandidateSet,
    ClaimProposal,
    ClaimStore,
    EntityResolverPort,
    EpisodeStore,
    MemoryAuthorizationPort,
    MemoryExtractorPort,
    MemoryQuery,
    MemoryRerankerPort,
    MemoryUnitOfWork,
)
from engrammesh.modules.memory.public import __all__ as public_exports
from engrammesh.shared.kernel.ids import (
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
}

DATACLASS_SHAPES = {
    MemoryScope: (
        ("tenant_id", MISSING),
        ("subject_id", MISSING),
        ("workspace_id", None),
        ("agent_id", None),
    ),
    Episode: (
        ("id", MISSING),
        ("scope", MISSING),
        ("actor_id", MISSING),
        ("source_type", MISSING),
        ("content_ref", MISSING),
        ("observed_at", MISSING),
        ("ingested_at", MISSING),
        ("content_hash", MISSING),
        ("idempotency_key", MISSING),
        ("sensitivity", MISSING),
        ("retention_class", MISSING),
        ("consent_basis", MISSING),
    ),
    EvidenceRef: (
        ("episode_id", MISSING),
        ("source_span", MISSING),
        ("extractor_version", MISSING),
        ("model_ref", None),
        ("prompt_version", None),
    ),
    Claim: (
        ("id", MISSING),
        ("scope", MISSING),
        ("subject", MISSING),
        ("predicate", MISSING),
        ("object_value", MISSING),
        ("polarity", MISSING),
        ("epistemic_kind", MISSING),
        ("confidence", MISSING),
        ("valid_from", MISSING),
        ("valid_to", MISSING),
        ("recorded_from", MISSING),
        ("recorded_to", MISSING),
        ("status", MISSING),
        ("evidence", MISSING),
    ),
    ProcedureVersion: (
        ("id", MISSING),
        ("version", MISSING),
        ("content_ref", MISSING),
        ("input_schema", MISSING),
        ("preconditions", MISSING),
        ("evaluation_score", MISSING),
        ("approval_status", MISSING),
        ("derived_from", MISSING),
        ("created_by", MISSING),
    ),
    EvidenceItem: (
        ("claim", MISSING),
        ("temporal_status", MISSING),
        ("lexical_score", 0.0),
        ("semantic_score", 0.0),
        ("temporal_score", 0.0),
        ("graph_score", 0.0),
        ("rerank_score", 0.0),
    ),
    EvidencePacket: (
        ("query_id", MISSING),
        ("items", MISSING),
        ("generated_at", MISSING),
    ),
    MemoryQuery: (
        ("scope", MISSING),
        ("text", MISSING),
        ("valid_at", None),
        ("recorded_at", None),
        ("limit", 10),
    ),
    AppendResult: (
        ("episode_id", MISSING),
        ("created", MISSING),
    ),
    ClaimProposal: (("claim", MISSING),),
    CandidateSet: (("items", MISSING),),
    AuthorizationRequest: (
        ("actor_id", MISSING),
        ("scope", MISSING),
        ("action", MISSING),
        ("sensitivity", MISSING),
    ),
}

EMPTY = inspect.Signature.empty
PARAMETER = inspect.Parameter.POSITIONAL_OR_KEYWORD
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
        for method_name in method_names
    ],
)
def test_all_port_methods_are_coroutine_functions(
    protocol: type[object],
    method_name: str,
) -> None:
    assert inspect.iscoroutinefunction(getattr(protocol, method_name))


@pytest.mark.parametrize(
    ("contract", "expected_fields"),
    DATACLASS_SHAPES.items(),
)
def test_dataclass_fields_have_exact_names_order_and_defaults(
    contract: type[object],
    expected_fields: tuple[tuple[str, object], ...],
) -> None:
    actual_fields = fields(contract)

    assert tuple(field.name for field in actual_fields) == tuple(
        name for name, _ in expected_fields
    )
    for field, (_, expected_default) in zip(
        actual_fields,
        expected_fields,
        strict=True,
    ):
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
        (name, annotation, default, PARAMETER)
        for name, annotation, default in expected_parameters
    )
    assert signature.return_annotation == expected_return


@pytest.mark.parametrize(
    ("protocol", "expected_members"),
    [
        (protocol, frozenset(method_names))
        for protocol, method_names in EXPECTED_METHODS.items()
    ],
)
def test_protocols_have_no_extra_public_methods(
    protocol: type[object],
    expected_members: frozenset[str],
) -> None:
    public_methods = {
        name
        for name, member in vars(protocol).items()
        if inspect.isfunction(member)
        and (not name.startswith("_") or name in {"__aenter__", "__aexit__"})
    }

    assert public_methods == expected_members


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
    assert get_type_hints(MemoryUnitOfWork.episodes.fget)["return"] is EpisodeStore
    assert get_type_hints(MemoryUnitOfWork.claims.fget)["return"] is ClaimStore
    declared_properties = {
        name
        for name, member in vars(MemoryUnitOfWork).items()
        if isinstance(member, property)
    }
    assert declared_properties == {"episodes", "claims"}
    for property_name, expected_return in (
        ("episodes", EpisodeStore),
        ("claims", ClaimStore),
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


def test_query_validates_scope_text_time_and_limit() -> None:
    scope = MemoryScope(
        tenant_id=TenantId.new(),
        subject_id=SubjectId.new(),
    )

    with pytest.raises(ValueError, match="text"):
        MemoryQuery(scope=scope, text=" ")
    with pytest.raises(ValueError, match="valid_at"):
        MemoryQuery(
            scope=scope,
            text="tea",
            valid_at=datetime(2026, 7, 27, 10, 0),  # noqa: DTZ001
        )
    with pytest.raises(ValueError, match="limit"):
        MemoryQuery(scope=scope, text="tea", limit=0)


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

    assert set(public_exports) == domain_exports | dto_exports
    assert not {protocol.__name__ for protocol in PROTOCOLS} & set(public_exports)
    assert "AppendResult" not in public_exports


def test_ports_module_does_not_define_a_memory_manager() -> None:
    assert not hasattr(ports, "MemoryManager")


def test_authorization_request_uses_actor_subject() -> None:
    assert get_type_hints(AuthorizationRequest)["actor_id"] is SubjectId
