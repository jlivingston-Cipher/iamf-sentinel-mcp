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


# --- doc 178: the MCP registry ownership gate -------------------------------
#
# The official registry verifies that WE own the PyPI distribution by looking
# for the literal string `mcp-name: <server name>` in the package's published
# description (the README, as it lands in the wheel's METADATA). Nothing else
# in the build asserts that string, and a README edit that drops it would not
# break any test — it would silently make the published release unverifiable,
# and the registry entry would then be pinned to a version we can no longer
# re-cut, because PyPI never lets a version be re-uploaded.
#
# Doc 177's lesson, applied: a guard that has only ever been run on the fixed
# shape has no measured discriminating power. Both tests below were run
# against a wheel rebuilt from the reverted README/server.json and both FAILED
# there before either was believed here.

MCP_SERVER_NAME = "io.github.jlivingston-Cipher/iamf-sentinel-mcp"


def test_registry_ownership_marker_reaches_the_published_description():
    """`mcp-name: …` must survive into what PyPI actually serves.

    Prefers the INSTALLED distribution's METADATA — the artifact the registry
    reads — and only falls back to the source README when the distribution is
    not installed at all (the two-checkout layout). It never prefers the source
    file over the built one: that substitution is the exact failure the gate
    exists to catch.
    """
    import pathlib
    from importlib.metadata import PackageNotFoundError, metadata

    expected = f"mcp-name: {MCP_SERVER_NAME}"
    try:
        md = metadata("iamf-sentinel-mcp")
    except PackageNotFoundError:
        md = None

    if md is not None:
        text = md.get_payload() or md.get("Description") or ""
        source = "installed distribution METADATA"
    else:
        readme = pathlib.Path(__file__).resolve().parents[1] / "README.md"
        if not readme.is_file():                          # pragma: no cover
            pytest.skip("neither an installed distribution nor a source README")
        text = readme.read_text(encoding="utf-8")
        source = "README.md (source checkout)"

    assert expected in text, (
        "%r is absent from the %s — the MCP registry cannot verify ownership "
        "of this distribution, so `mcp-publisher publish` would be rejected"
        % (expected, source)
    )


def test_server_json_agrees_with_the_marker_and_the_distribution():
    """One name, four places: server.json, the README marker, the dist, the module."""
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    readme = root / "README.md"
    server_json = root / "server.json"
    if not readme.is_file():                              # pragma: no cover
        pytest.skip("not a source checkout; server.json is not shipped in the wheel")
    assert server_json.is_file(), (
        "README.md is beside these tests but server.json is not — the registry "
        "listing's own manifest has been deleted from the repository root"
    )

    sj = json.loads(server_json.read_text(encoding="utf-8"))
    assert sj["name"] == MCP_SERVER_NAME
    assert len(sj["description"]) <= 100, "the registry schema caps description at 100"

    readme = (root / "README.md").read_text(encoding="utf-8")
    assert readme.count(f"mcp-name: {sj['name']}") == 1, (
        "server.json names %r; the README marker must name it exactly once" % sj["name"]
    )

    pypi = [p for p in sj["packages"] if p["registryType"] == "pypi"]
    assert len(pypi) == 1
    assert pypi[0]["identifier"] == "iamf-sentinel-mcp"
    assert pypi[0]["version"] == sj["version"] == iamf_sentinel_mcp.__version__, (
        "server.json %r / package %r / module %r must agree — the registry pins the "
        "listing to a version that must exist on PyPI"
        % (sj["version"], pypi[0]["version"], iamf_sentinel_mcp.__version__)
    )
