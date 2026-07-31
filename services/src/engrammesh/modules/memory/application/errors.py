"""Application errors for cognitive-memory use cases."""

from typing import final


@final
class EpisodeAuthorizationDenied(PermissionError):
    """Raised when an actor cannot record an episode."""

    def __init__(self) -> None:
        super().__init__()


@final
class EpisodeReadAuthorizationDenied(PermissionError):
    def __init__(self) -> None:
        super().__init__()


@final
class EpisodeNotFound(LookupError):
    def __init__(self) -> None:
        super().__init__()
