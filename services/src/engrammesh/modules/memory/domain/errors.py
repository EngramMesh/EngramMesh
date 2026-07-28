"""Domain errors for cognitive-memory invariants."""

from typing import final


@final
class EpisodeIdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for a different Episode."""

    def __init__(self) -> None:
        super().__init__()
