"""The live-Temporal marker guard in orchestration/conftest.py (FR-022, R16).

A test that reaches `Client.connect` without `@pytest.mark.temporal` must fail,
not skip. Both inner tests turn a connect error into a skip, the way the real
`_connect_or_skip` helpers do, so only the guard can make the unmarked one fail.
"""
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "conftest.py"

INNER = '''
import asyncio

import pytest
from temporalio.client import Client


def _connect_or_skip():
    try:
        asyncio.run(Client.connect("localhost:1"))
    except Exception as exc:
        pytest.skip(f"no Temporal: {exc}")


def test_unmarked():
    _connect_or_skip()


@pytest.mark.temporal
def test_marked():
    _connect_or_skip()
'''


def test_unmarked_connect_fails_and_marked_connect_skips(pytester):
    pytester.makeconftest(GUARD.read_text())
    pytester.makeini("[pytest]\nmarkers =\n    temporal: needs a live Temporal server\n")
    pytester.makepyfile(test_inner=INNER)

    # A subprocess, so the guard wrapping this outer test's Client.connect is
    # not the "original" the inner guard captures.
    result = pytester.runpytest_subprocess("-rfs")

    result.assert_outcomes(failed=1, skipped=1)
    result.stdout.fnmatch_lines([
        "*test_inner.py::test_unmarked connects to live Temporal "
        "but is not marked @pytest.mark.temporal*",
    ])
