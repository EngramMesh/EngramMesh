import copy
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

REPOSITORY_ROOT = Path(__file__).parents[3]
SCHEMA_ROOT = REPOSITORY_ROOT / "packages" / "contracts" / "jsonschema"
SCHEMA_PATHS = {
    "envelope": SCHEMA_ROOT / "events" / "v1" / "event-envelope.schema.json",
    "episode": SCHEMA_ROOT / "memory" / "v1" / "episode-recorded.schema.json",
    "execution": (
        SCHEMA_ROOT
        / "runtime"
        / "v1"
        / "execution-status-changed.schema.json"
    ),
}

UUIDS = {
    "event": "2201fbb4-e20a-44d7-9ca2-e44ffb491d1e",
    "tenant": "60ac7073-c0f4-41d6-b6c6-052d1d49aaf7",
    "aggregate": "f152cf23-404b-448a-8643-e991729a8f83",
    "correlation": "3558e119-6ba9-46f0-95f6-bc46f156ee29",
    "episode": "840ddfba-f834-486b-b918-bbb87a6bf9db",
    "subject": "d87fdc29-d07d-4714-adc4-ef5eb64c6dbe",
    "actor": "5dfc0971-12d9-4743-be3a-385758ac86bb",
    "content": "502700f1-5e63-4770-a259-245925c80c4f",
    "execution": "0ee41388-bc30-4477-b6fe-e9e16e731f5f",
}


def _load_schema(name: str) -> Mapping[str, object]:
    with SCHEMA_PATHS[name].open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert isinstance(value, dict)
    return value


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_load_schema(name), format_checker=FormatChecker())


def _envelope(event_type: str, payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "event_id": UUIDS["event"],
        "event_type": event_type,
        "schema_version": 1,
        "tenant_id": UUIDS["tenant"],
        "aggregate_id": UUIDS["aggregate"],
        "aggregate_version": 3,
        "correlation_id": UUIDS["correlation"],
        "causation_id": None,
        "occurred_at": "2026-07-27T08:30:00Z",
        "payload": dict(payload),
    }


def _episode_event() -> dict[str, object]:
    return _envelope(
        "memory.episode-recorded",
        {
            "episode_id": UUIDS["episode"],
            "scope": {
                "tenant_id": UUIDS["tenant"],
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
    )


def _execution_event() -> dict[str, object]:
    return _envelope(
        "runtime.execution-status-changed",
        {
            "execution_id": UUIDS["execution"],
            "revision": 7,
            "previous_status": "running",
            "status": "succeeded",
            "updated_at": "2026-07-27T08:30:00Z",
        },
    )


@pytest.mark.parametrize("schema_name", tuple(SCHEMA_PATHS))
def test_schema_is_valid_draft_2020_12_with_explicit_metadata(
    schema_name: str,
) -> None:
    schema = _load_schema(schema_name)

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["version"] == "1.0.0"
    assert schema["$id"]
    assert schema["title"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    ("schema_name", "event"),
    [
        ("envelope", _envelope("architecture.contract-tested", {})),
        ("episode", _episode_event()),
        ("execution", _execution_event()),
    ],
)
def test_schema_accepts_a_representative_valid_event(
    schema_name: str,
    event: Mapping[str, object],
) -> None:
    _validator(schema_name).validate(event)


@pytest.mark.parametrize(
    ("schema_name", "event_factory", "missing_path"),
    [
        ("envelope", lambda: _envelope("architecture.contract-tested", {}), ("tenant_id",)),
        (
            "envelope",
            lambda: _envelope("architecture.contract-tested", {}),
            ("schema_version",),
        ),
        (
            "envelope",
            lambda: _envelope("architecture.contract-tested", {}),
            ("occurred_at",),
        ),
        (
            "envelope",
            lambda: _envelope("architecture.contract-tested", {}),
            ("aggregate_version",),
        ),
        ("episode", _episode_event, ("payload", "scope")),
        ("execution", _execution_event, ("payload", "revision")),
    ],
)
def test_schema_rejects_missing_required_contract_fields(
    schema_name: str,
    event_factory: object,
    missing_path: tuple[str, ...],
) -> None:
    assert callable(event_factory)
    event = copy.deepcopy(event_factory())
    target = event
    for component in missing_path[:-1]:
        target = target[component]
    del target[missing_path[-1]]

    with pytest.raises(ValidationError):
        _validator(schema_name).validate(event)


@pytest.mark.parametrize(
    ("schema_name", "event", "path", "invalid_value"),
    [
        ("envelope", _envelope("architecture.contract-tested", {}), ("event_id",), "not-a-uuid"),
        (
            "envelope",
            _envelope("architecture.contract-tested", {}),
            ("occurred_at",),
            "not-a-timestamp",
        ),
        ("episode", _episode_event(), ("payload", "scope", "tenant_id"), "not-a-uuid"),
        ("execution", _execution_event(), ("payload", "revision"), 0),
    ],
)
def test_schema_rejects_invalid_identifier_timestamp_or_revision(
    schema_name: str,
    event: Mapping[str, object],
    path: tuple[str, ...],
    invalid_value: object,
) -> None:
    candidate = copy.deepcopy(event)
    target = candidate
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = invalid_value

    with pytest.raises(ValidationError):
        _validator(schema_name).validate(candidate)
