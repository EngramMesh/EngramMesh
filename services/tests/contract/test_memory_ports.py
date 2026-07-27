import inspect
from dataclasses import FrozenInstanceError, is_dataclass
from datetime import datetime
from typing import get_type_hints

import pytest

from engrammesh.modules.memory import ports
from engrammesh.modules.memory.domain.model import (
    Claim,
    Episode,
    EvidencePacket,
    MemoryScope,
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
from engrammesh.shared.kernel.ids import MemoryId, SubjectId, TenantId

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
