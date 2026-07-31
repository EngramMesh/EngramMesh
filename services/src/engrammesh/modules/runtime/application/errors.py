from typing import final


@final
class ExecutionAuthorizationDenied(PermissionError):
    def __init__(self) -> None:
        super().__init__()


@final
class OrchestrationUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__()
