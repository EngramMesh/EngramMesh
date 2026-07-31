"""Domain errors for cognitive-memory invariants."""

from typing import final


@final
class EpisodeIdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for a different Episode."""

    def __init__(self) -> None:
        super().__init__()


@final
class InvalidEpisodeCursor(ValueError):
    """Raised when an episode list cursor cannot be decoded."""

    def __init__(self) -> None:
        super().__init__()
