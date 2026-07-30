import copy
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

REPOSITORY_ROOT = Path(__file__).parents[3]
SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "jsonschema"
    / "memory"
    / "v1"
    / "record-episode-request.schema.json"
)
EPISODE_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "jsonschema"
    / "memory"
    / "v1"
    / "episode-recorded.schema.json"
)

UUIDS = {
    "tenant": "60ac7073-c0f4-41d6-b6c6-052d1d49aaf7",
    "subject": "d87fdc29-d07d-4714-adc4-ef5eb64c6dbe",
    "actor": "5dfc0971-12d9-4743-be3a-385758ac86bb",
    "content": "502700f1-5e63-4770-a259-245925c80c4f",
    "event": "2201fbb4-e20a-44d7-9ca2-e44ffb491d1e",
    "aggregate": "f152cf23-404b-448a-8643-e991729a8f83",
    "correlation": "3558e119-6ba9-46f0-95f6-bc46f156ee29",
    "episode": "840ddfba-f834-486b-b918-bbb87a6bf9db",
}


def _load_schema(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert isinstance(value, dict)
    return value


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        _load_schema(SCHEMA_PATH),
        format_checker=FormatChecker(),
    )


def valid_request_body() -> dict[str, object]:
    return {
        "actor_id": UUIDS["actor"],
        "scope": {
            "tenant_id": UUIDS["tenant"],
            "subject_id": UUIDS["subject"],
            "workspace_id": "workspace-42",
            "agent_id": None,
        },
        "source_type": "user",
        "content_ref": UUIDS["content"],
        "observed_at": "2026-07-27T08:29:58+00:00",
        "content_hash": "sha256:88c7355c",
        "idempotency_key": "episode-42",
        "sensitivity": "confidential",
        "retention_class": "standard",
        "consent_basis": "user_request",
    }


def _episode_event() -> dict[str, object]:
    return {
        "event_id": UUIDS["event"],
        "event_type": "memory.episode-recorded",
        "schema_version": 1,
        "tenant_id": UUIDS["tenant"],
        "aggregate_id": UUIDS["aggregate"],
        "aggregate_version": 3,
        "correlation_id": UUIDS["correlation"],
        "causation_id": None,
        "occurred_at": "2026-07-27T08:30:00Z",
        "payload": {
            "episode_id": UUIDS["episode"],
            "scope": {
                "subject_id": UUIDS["subject"],
                "workspace_id": "workspace-42",
                "agent_id": None,
            },
            "actor_id": UUIDS["actor"],
            "source_type": "user",
            "content_ref": UUIDS["content"],
            "observed_at": "2026-07-27T08:29:58+00:00",
            "ingested_at": "2026-07-27T08:30:00Z",
            "content_hash": "sha256:88c7355c",
            "idempotency_key": "episode-42",
            "sensitivity": "confidential",
            "retention_class": "standard",
            "consent_basis": "user_request",
        },
    }


def test_request_schema_is_valid_draft_2020_12_with_explicit_metadata() -> None:
    schema = _load_schema(SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["version"] == "1.0.0"
    assert schema["$id"] == (
        "https://engrammesh.org/contracts/memory/v1/record-episode-request.schema.json"
    )
    assert schema["title"] == "Memory Record Episode HTTP Request"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False


def test_request_schema_accepts_a_representative_valid_body() -> None:
    _validator().validate(valid_request_body())


@pytest.mark.parametrize(
    "missing_path",
    [
        ("scope",),
        ("scope", "tenant_id"),
        ("scope", "subject_id"),
        ("actor_id",),
        ("source_type",),
        ("content_ref",),
        ("observed_at",),
        ("content_hash",),
        ("idempotency_key",),
        ("sensitivity",),
        ("retention_class",),
        ("consent_basis",),
    ],
)
def test_request_schema_rejects_missing_required_fields(
    missing_path: tuple[str, ...],
) -> None:
    body = copy.deepcopy(valid_request_body())
    target = body
    for component in missing_path[:-1]:
        target = target[component]
    del target[missing_path[-1]]

    with pytest.raises(ValidationError):
        _validator().validate(body)


@pytest.mark.parametrize(
    ("path", "invalid_value"),
    [
        (("scope", "tenant_id"), "not-a-uuid"),
        (("scope", "subject_id"), "not-a-uuid"),
        (("actor_id",), "not-a-uuid"),
        (("content_ref",), "not-a-uuid"),
        (("observed_at",), "not-a-timestamp"),
        (("content_hash",), " "),
        (("idempotency_key",), "\t"),
        (("consent_basis",), "\n"),
        (("scope", "workspace_id"), " "),
    ],
)
def test_request_schema_rejects_invalid_identifiers_timestamps_or_blank_text(
    path: tuple[str, ...],
    invalid_value: object,
) -> None:
    body = copy.deepcopy(valid_request_body())
    target = body
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = invalid_value

    with pytest.raises(ValidationError):
        _validator().validate(body)


def test_request_schema_requires_scope_tenant_id() -> None:
    body = valid_request_body()
    del body["scope"]["tenant_id"]

    with pytest.raises(ValidationError):
        _validator().validate(body)


def test_request_schema_is_independent_from_episode_event_schema() -> None:
    """HTTP scope 含 tenant_id；episode 事件 payload.scope 不得含 tenant_id。"""
    event = _episode_event()
    assert "tenant_id" not in event["payload"]["scope"]
    request = valid_request_body()
    assert "tenant_id" in request["scope"]

    request_schema = _load_schema(SCHEMA_PATH)
    episode_schema = _load_schema(EPISODE_SCHEMA_PATH)

    assert request_schema["$id"] != episode_schema["$id"]
    assert "episode-recorded" not in request_schema["$id"]
    assert request_schema["$defs"]["httpMemoryScope"]["required"] == [
        "tenant_id",
        "subject_id",
    ]
    assert episode_schema["$defs"]["memoryScope"]["required"] == ["subject_id"]
    assert "tenant_id" not in episode_schema["$defs"]["memoryScope"]["properties"]

    event["payload"]["scope"]["tenant_id"] = UUIDS["tenant"]
    with pytest.raises(ValidationError):
        Draft202012Validator(
            episode_schema,
            format_checker=FormatChecker(),
        ).validate(event)
