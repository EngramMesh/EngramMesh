"""Shared pytest configuration for the services test suite."""

from __future__ import annotations

import pathlib
import sys

import pytest

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

pytest_plugins = ["integration.postgres.conftest"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("postgres") is not None:
            item.add_marker(pytest.mark.xdist_group(name="postgres_serial"))
