"""Domain errors for durable execution invariants."""

from typing import final


@final
class ExecutionIdempotencyConflict(ValueError):
    def __init__(self) -> None:
        super().__init__()


@final
class ExecutionNotFound(LookupError):
    def __init__(self) -> None:
        super().__init__()


@final
class InvalidExecutionTransition(ValueError):
    def __init__(self) -> None:
        super().__init__()
