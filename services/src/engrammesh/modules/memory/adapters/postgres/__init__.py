"""PostgreSQL persistence adapter for cognitive memory."""

from engrammesh.modules.memory.adapters.postgres.connection import (
    PostgresMemoryDatabase,
)
from engrammesh.modules.memory.adapters.postgres.inbox_store import (
    PostgresInboxStore,
)
from engrammesh.modules.memory.adapters.postgres.migrations import (
    MIGRATIONS_DIR,
    apply_migrations,
)
from engrammesh.modules.memory.adapters.postgres.outbox_relay import (
    PostgresOutboxRelayStore,
)
from engrammesh.modules.memory.adapters.postgres.unit_of_work import (
    PostgresMemoryUnitOfWork,
    PostgresMemoryUnitOfWorkFactory,
)

__all__ = [
    "MIGRATIONS_DIR",
    "PostgresInboxStore",
    "PostgresMemoryDatabase",
    "PostgresMemoryUnitOfWork",
    "PostgresMemoryUnitOfWorkFactory",
    "PostgresOutboxRelayStore",
    "apply_migrations",
]
