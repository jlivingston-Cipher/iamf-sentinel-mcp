"""Packaging invariants.

Named regression (doc 101), carried into stage (v) before its first upload
rather than after. `iamf-sentinel-pro 0.3.1` shipped to PyPI with
`pyproject.toml` bumped and `sentinel_pro/__init__.py` left at the previous
value, so the distribution and the module disagreed about their own version on
a published release — and PyPI never allows a version to be re-uploaded. The
bump had been checked against the README and not against the module beside it.
This test makes the pair a gate rather than a habit.

`sentinel_pro.__version__` happened to be consumed nowhere, so that slip was
survivable. This package's version is not obviously load-bearing either — but
"not obviously" is what doc 101 said about pro, one repo before the same
string turned out to be load-bearing in the other two (every Sentinel report
carries `sentinel_version`; the Loom batch cache key carries `loom_version`).
"""

from __future__ import annotations

import pytest

import iamf_sentinel_mcp


def test_declared_version_matches_module_version():
    from importlib.metadata import PackageNotFoundError, version
    try:
        declared = version("iamf-sentinel-mcp")
    except PackageNotFoundError:            # pragma: no cover
        pytest.skip("iamf-sentinel-mcp is not installed; nothing to compare")
    assert iamf_sentinel_mcp.__version__ == declared, (
        "iamf_sentinel_mcp.__version__ is %r but the installed distribution "
        "is %r — bump both, or neither"
        % (iamf_sentinel_mcp.__version__, declared)
    )


def test_server_advertises_its_version_to_clients():
    """The version reaches the wire, not just the module (doc 105).

    mcp v2's initialize result carries `serverInfo.version`; a client that
    reports which build it is talking to reads this field. Left unset it is
    the empty string, which is what the v1 server advertised because FastMCP
    had no such field at all.
    """
    from iamf_sentinel_mcp.server import build_server
    import iamf_sentinel_mcp
    assert build_server().version == iamf_sentinel_mcp.__version__
