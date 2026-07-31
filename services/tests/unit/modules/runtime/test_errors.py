import pytest

from engrammesh.modules.runtime.domain.errors import (
    ExecutionIdempotencyConflict,
    ExecutionNotFound,
    InvalidExecutionTransition,
)


@pytest.mark.parametrize(
    "error_type",
    [
        ExecutionIdempotencyConflict,
        ExecutionNotFound,
        InvalidExecutionTransition,
    ],
)
def test_runtime_domain_errors_are_zero_payload(error_type: type[Exception]) -> None:
    with pytest.raises(error_type):
        raise error_type()
