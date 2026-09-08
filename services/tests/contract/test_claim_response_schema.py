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
    / "claim-response.schema.json"
)
LIST_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "packages"
    / "contracts"
    / "jsonschema"
    / "memory"
    / "v1"
    / "claim-list-response.schema.json"
)


def _registry() -> Registry:
    response_resource = Resource.from_contents(
        json.loads(RESPONSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    return Registry().with_resource(
        "https://engrammesh.org/contracts/memory/v1/claim-response.schema.json",
        response_resource,
    )


def _list_validator() -> Draft202012Validator:
    schema = json.loads(LIST_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=_registry(),
    )


def sample_claim_response_dict() -> dict[str, object]:
    return {
        "claim_id": "840ddfba-f834-486b-b918-bbb87a6bf9db",
        "scope": {
            "tenant_id": "53dad495-7915-439a-b03a-379452a1aa86",
            "subject_id": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
            "workspace_id": "workspace-42",
            "agent_id": None,
        },
        "episode_id": "940ddfba-f834-486b-b918-bbb87a6bf9db",
        "subject": "3d65c071-ac55-4847-a8f1-e3cb859d3c45",
        "predicate": "observed_content_hash",
        "object_value": "sha256:abc",
        "polarity": True,
        "epistemic_kind": "extracted",
        "confidence": 1.0,
        "valid_from": "2026-09-08T10:00:00+00:00",
        "valid_to": None,
        "recorded_from": "2026-09-08T10:00:00+00:00",
        "recorded_to": None,
        "status": "proposed",
        "extractor_version": "deterministic-v1",
        "evidence": [
            {
                "episode_id": "940ddfba-f834-486b-b918-bbb87a6bf9db",
                "source_span": "metadata",
                "extractor_version": "deterministic-v1",
                "model_ref": None,
                "prompt_version": None,
            }
        ],
    }


def test_claim_response_matches_schema() -> None:
    schema = json.loads(RESPONSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        sample_claim_response_dict()
    )


def test_claim_list_response_matches_schema() -> None:
    body = {"items": [sample_claim_response_dict()], "next_cursor": None}
    _list_validator().validate(body)
