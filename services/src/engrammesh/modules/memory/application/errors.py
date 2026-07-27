"""Application errors for cognitive-memory use cases."""

from typing import final


@final
class EpisodeAuthorizationDenied(PermissionError):
    """Raised when an actor cannot record an episode."""

    def __init__(self) -> None:
        super().__init__()
