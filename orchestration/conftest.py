"""Suite-wide guard for live-Temporal tests (specs/012 FR-022, R16).

A test that reaches `Client.connect` must carry `@pytest.mark.temporal` (or a
module `pytestmark`). An unmarked one fails here instead of being skipped by a
`_connect_or_skip` helper when Temporal is down. Tested by
tests/test_temporal_marker_guard.py.
"""
import pytest
from temporalio.client import Client

pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def _temporal_marker_guard(request, monkeypatch):
    original = Client.connect  # bound classmethod

    def guarded(*args, **kwargs):
        if request.node.get_closest_marker("temporal") is None:
            pytest.fail(
                f"{request.node.nodeid} connects to live Temporal "
                "but is not marked @pytest.mark.temporal"
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(Client, "connect", guarded)
