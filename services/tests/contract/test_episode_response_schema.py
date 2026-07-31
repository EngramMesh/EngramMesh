import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

REPOSITORY_ROOT = Path(__file__).parents[3]
RESPONSE_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "jsonschema"
    / "memory"
    / "v1"
    / "episode-response.schema.json"
)
LIST_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "jsonschema"
    / "memory"
    / "v1"
    / "episode-list-response.schema.json"
)


def _registry() -> Registry:
    response_resource = Resource.from_contents(
        json.loads(RESPONSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    return Registry().with_resource(
        "https://engrammesh.org/contracts/memory/v1/episode-response.schema.json",
        response_resource,
    )


def _list_validator() -> Draft202012Validator:
    schema = json.loads(LIST_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=_registry(),
    )


def sample_episode_response_dict() -> dict[str, object]:
    return {
        "episode_id": "840ddfba-f834-486b-b918-bbb87a6bf9db",
        "scope": {
            "tenant_id": "53dad495-7915-439a-b03a-379452a1aa86",
            "subject_id": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
            "workspace_id": "workspace-42",
            "agent_id": None,
        },
        "actor_id": "3ba213e4-3367-4e7c-9635-bcbfbad505e6",
        "source_type": "user",
        "content_ref": "a2e57fc9-d07d-45dc-a647-76d195985d86",
        "observed_at": "2026-07-27T10:00:00+00:00",
        "ingested_at": "2026-07-27T10:01:00+00:00",
        "content_hash": "sha256:88c7355c",
        "idempotency_key": "episode-42",
        "sensitivity": "confidential",
        "retention_class": "standard",
        "consent_basis": "user_request",
    }


def test_episode_response_matches_schema() -> None:
    schema = json.loads(RESPONSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        sample_episode_response_dict()
    )


def test_episode_list_response_matches_schema() -> None:
    body = {"items": [sample_episode_response_dict()], "next_cursor": None}
    _list_validator().validate(body)
