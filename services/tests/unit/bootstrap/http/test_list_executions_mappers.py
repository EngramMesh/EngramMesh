from uuid import UUID

import pytest

from engrammesh.bootstrap.http.mappers import (
    LimitOutOfRangeError,
    to_list_executions_query,
)
from engrammesh.shared.kernel.ids import SubjectId, TenantId

TENANT = TenantId(UUID("53dad495-7915-439a-b03a-379452a1aa86"))
SUBJECT = SubjectId(UUID("3d65c071-ac55-4847-a8f1-e3cb859d3c45"))
ACTOR = SubjectId(UUID("3ba213e4-3367-4e7c-9635-bcbfbad505e6"))


def test_to_list_executions_query_maps_parameters() -> None:
    query = to_list_executions_query(
        path_tenant_id=TENANT,
        actor_id=ACTOR,
        subject_id=SUBJECT,
        workspace_id="workspace-42",
        agent_id=None,
        limit=25,
        cursor="cursor-token",
    )
    assert query.actor_id == ACTOR
    assert query.scope.tenant_id == TENANT
    assert query.scope.subject_id == SUBJECT
    assert query.limit == 25
    assert query.cursor == "cursor-token"


def test_to_list_executions_query_rejects_limit_over_100() -> None:
    with pytest.raises(LimitOutOfRangeError):
        to_list_executions_query(
            path_tenant_id=TENANT,
            actor_id=ACTOR,
            subject_id=SUBJECT,
            workspace_id="workspace-42",
            agent_id=None,
            limit=101,
            cursor=None,
        )
