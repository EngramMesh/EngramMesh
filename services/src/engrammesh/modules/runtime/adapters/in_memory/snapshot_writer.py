"""In-memory runtime snapshot writer for Temporal activity integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from engrammesh.modules.runtime.domain.model import ExecutionSnapshot
from engrammesh.shared.kernel.ids import ExecutionId


@final
@dataclass
class InMemoryRuntimeSnapshotWriter:
    """Collect execution snapshots with revision-monotonic upsert semantics."""

    snapshots: dict[ExecutionId, ExecutionSnapshot] = field(default_factory=dict)

    async def upsert_snapshot(self, snapshot: ExecutionSnapshot) -> None:
        existing = self.snapshots.get(snapshot.execution_id)
        if existing is not None and existing.revision >= snapshot.revision:
            return
        self.snapshots[snapshot.execution_id] = snapshot
