"""iamf-sentinel-mcp server tests.

Direct-call tests pin tool behaviour (E-74.3/74.4/74.6); one in-memory MCP
session test exercises the real protocol path (R-74.2 fallback: it skips if
the SDK's memory harness moves). Needs sentinel-oss, loom, and this package's
root on PYTHONPATH. The validate/inspect pins use the wp1 clean sample and
skip (house pattern) when it is not staged.
"""

from __future__ import annotations

import asyncio
import struct
import wave
from pathlib import Path

import pytest

from conftest import needs_oss_src

from iamf_sentinel_mcp.server import (
    build_server, checks_catalog, f_register, iamf_inspect, iamf_validate,
    loom_compile, loom_explain, loom_run, mcodes_catalog,
)

import json

WP1_SAMPLE = Path("/tmp/sentinel_build/wp1/wp1-samples/stereo_iamftools.iamf")

needs_wp1 = pytest.mark.skipif(not WP1_SAMPLE.is_file(),
                               reason="wp1 sample tree not staged")


# ------------------------------------------------------------ fixtures

def _write_wav(path: Path, channels: int = 2, frames: int = 4800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(48000)
        silence = struct.pack("<h", 0) * channels
        w.writeframes(silence * frames)


MANIFEST = """\
loom: 0
title: mcp cycle-a stereo
sources:
  main: { path: wavs/main.wav, kind: bed, layout: stereo }
elements:
  bed: { from: main }
presentations:
  - id: main
    annotations: { en-us: "Stereo Mix" }
    elements: [ { ref: bed } ]
targets:
  - { format: iamf, out: dist/stereo.iamf }
"""


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "manifest.yaml").write_text(MANIFEST, encoding="utf-8")
    _write_wav(tmp_path / "wavs" / "main.wav")
    return tmp_path


# ------------------------------------------------------- validate/inspect

@needs_wp1
def test_validate_clean_sample_passes():
    doc = iamf_validate(str(WP1_SAMPLE))
    assert doc["summary"]["result"] == "PASS"          # E-74.3
    assert doc["summary"]["counts"]["FAIL"] == 0
    assert doc["exit_code"] == 0
    assert isinstance(doc["findings"], list)


@needs_wp1
def test_validate_strict_is_at_least_as_severe():
    lax = iamf_validate(str(WP1_SAMPLE))
    strict = iamf_validate(str(WP1_SAMPLE), strict=True)
    assert strict["exit_code"] >= lax["exit_code"]


def test_validate_missing_file_is_structured_not_raised():
    doc = iamf_validate("/nonexistent/nope.iamf")       # E-74.3
    assert doc["summary"]["result"] == "ERROR"
    assert "execution_error" in doc["summary"]
    assert doc["exit_code"] == 2


@needs_wp1
def test_inspect_reports_structure():
    out = iamf_inspect(str(WP1_SAMPLE))
    assert out["container"] == "raw"          # engine's label for raw .iamf
    assert out["sequence_header"]["ia_code"] == "iamf"
    assert out["audio_elements"] >= 1
    assert out["mix_presentations"] >= 1
    assert out["audio_frames"] > 0
    assert set(out["trim"]) == {"frames_with_trim", "total_start", "total_end"}
    codecs = {cc["codec"] for cc in out["codec_configs"]}
    assert codecs                                        # non-empty


def test_inspect_missing_file_is_structured():
    out = iamf_inspect("/nonexistent/nope.iamf")
    assert "execution_error" in out


# ---------------------------------------------------------------- loom

def test_compile_ok_and_shape(project: Path):
    res = loom_compile(str(project / "manifest.yaml"))
    assert res["ok"] is True                             # E-74.4
    (t,) = res["targets"]
    assert t["format"] == "iamf" and t["backend"] == "iamftools"
    assert t["muxer"] is None
    assert "ADR-1" in t["rationale"]
    assert t["steps"] and all({"id", "kind", "tool"} <= set(s) for s in t["steps"])


def test_explain_ok_and_content(project: Path):
    res = loom_explain(str(project / "manifest.yaml"))
    assert res["ok"] is True
    assert "TARGET" in res["text"] and "why this route:" in res["text"]


def test_compile_missing_manifest_returns_m101():
    res = loom_compile("/nonexistent/manifest.yaml")     # E-74.4
    assert res["ok"] is False
    assert any(d["code"] == "M-101" for d in res["diagnostics"])


def test_explain_bad_manifest_diagnostics(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("loom: 0\ntitle: no sources\n", encoding="utf-8")
    res = loom_explain(str(bad))
    assert res["ok"] is False and res["diagnostics"]


# ------------------------------------------------------------ resources

def test_checks_catalog_matches_registry():
    from sentinel.findings import REGISTRY
    doc = json.loads(checks_catalog())
    assert doc["count"] == len(REGISTRY)                 # E-74.6
    ids = {c["id"] for c in doc["checks"]}
    assert {"S-407", "S-408", "S-409"} <= ids            # doc-59 trim checks present
    assert all(c["severity"] in {"FAIL", "WARN", "INFO"} for c in doc["checks"])


# ------------------------------------------- protocol path (in-memory)

def _connect():
    """The SDK's in-memory client, or a skip if it moves (R-74.2).

    mcp v2 replaced `mcp.shared.memory.create_connected_server_and_client_
    session(server._mcp_server)` with `mcp.Client(server)`, which takes the
    MCPServer directly — no private attribute reach-through."""
    try:
        from mcp import Client
    except ImportError:                              # pragma: no cover
        pytest.skip("SDK in-memory client moved (R-74.2)")
    return Client


def test_mcp_session_lists_and_calls():
    """Exercise the real MCP wire path: list tools, call one."""
    connect = _connect()

    async def scenario():
        async with connect(build_server()) as session:
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"iamf_validate", "iamf_inspect",
                    "loom_compile", "loom_explain"} <= names
            res = await session.call_tool(
                "loom_compile", {"manifest_path": "/nonexistent/x.yaml"})
            payload = json.loads(res.content[0].text)
            assert payload["ok"] is False

    asyncio.run(scenario())


# ===================================================== Cycle B (doc 75)
# The doc-75 ORDERING CONTRACT (R-75.2) is RETIRED (X-76a): build_server()
# returns an independent instance per call, so enabled-state tests construct
# their own server instead of mutating a shared module-level one.


def _session_tool_names(server) -> set[str]:
    connect = _connect()

    async def scenario():
        async with connect(server) as session:
            tools = await session.list_tools()
            return {t.name for t in tools.tools}

    return asyncio.run(scenario())


def test_loom_run_absent_by_default():
    """E-75.3(a): without --enable-run, the execution tool is not offered."""
    names = _session_tool_names(build_server())
    assert "loom_run" not in names
    assert {"iamf_validate", "iamf_inspect",
            "loom_compile", "loom_explain"} <= names


def test_loom_run_compile_error_shape_matches_compile():
    """E-75.3(d)/E-75.4: same {ok, diagnostics} shape as loom_compile."""
    res = loom_run("/nonexistent/manifest.yaml")
    assert res["ok"] is False
    assert any(d["code"] == "M-101" for d in res["diagnostics"])


def test_loom_run_missing_toolchain_is_actionable(project: Path, tmp_path: Path):
    """E-75.3(c): a bogus toolchain root fails with the missing binary's
    expected path in the failure text — structured, never a traceback."""
    out = tmp_path / "out"
    res = loom_run(str(project / "manifest.yaml"),
                   out_dir=str(out), toolchain="/nonexistent-toolchain")
    assert res["ok"] is False
    assert res["failures"], "expected step failures"
    # Doc 99's rule: plans keep their `$`-tokens and are platform-invariant;
    # ledgers and MESSAGES resolve, so they carry the platform's path flavour.
    # This message renders `\nonexistent-toolchain\src\...` on Windows, so
    # matching a POSIX literal went red on both Windows legs of ci #1
    # (doc 105 §11.5). Normalize separators first — the claim under test is
    # that the failure NAMES the root it was handed, not how an OS spells a
    # separator. Doc 99 fixed this exact class in loom's own suite; this repo
    # was written before that lesson and never swept.
    failures = [f.replace("\\", "/") for f in res["failures"]]
    assert any("/nonexistent-toolchain" in f for f in failures)
    assert res["ledger_path"] and Path(res["ledger_path"]).is_file()


def test_enable_then_present_and_callable(project: Path):
    """E-75.3(b): an enable_run server lists loom_run and it is callable
    over the wire — and building it leaves a fresh default server
    untouched (the X-76a isolation property that retires R-75.2)."""
    enabled = build_server(enable_run=True)
    names = _session_tool_names(enabled)
    assert "loom_run" in names
    assert "loom_run" not in _session_tool_names(build_server())  # isolated
    connect = _connect()

    async def scenario():
        async with connect(enabled) as session:
            res = await session.call_tool(
                "loom_run", {"manifest_path": "/nonexistent/x.yaml"})
            return json.loads(res.content[0].text)

    payload = asyncio.run(scenario())
    assert payload["ok"] is False
    assert any(d["code"] == "M-101" for d in payload["diagnostics"])


# ------------------------------------------------- Cycle B resources

def test_mcodes_catalog_matches_loom_registry():
    from loom.diagnostics import CODES
    doc = json.loads(mcodes_catalog())
    assert doc["count"] == len(CODES)
    by_code = {c["code"]: c for c in doc["codes"]}
    assert set(by_code) == set(CODES)
    assert all(by_code[c]["summary"] == s for c, s in CODES.items())
    assert by_code["M-405"]["retired"] is True     # retired-in-place, kept
    assert by_code["M-101"]["retired"] is False


def test_f_register_serves_live_content():
    text = f_register()
    assert "F31" in text and "F32" in text
    assert "Sentinel check" in text or "Sentinel status" in text


def test_f_register_bundled_snapshot_not_drifted():
    """E-75.4 tripwire: the wheel's bundled snapshot must match the live
    register whenever both are present (monorepo layout)."""
    import sentinel as _s
    live = Path(_s.__file__).resolve().parent.parent / "F_TO_CHECK.md"
    if not live.is_file():
        pytest.skip("live F_TO_CHECK.md not locatable (wheel install)")
    from iamf_sentinel_mcp.server import _F_REGISTER_BUNDLED
    assert _F_REGISTER_BUNDLED.read_bytes() == live.read_bytes(), (
        "bundled F_TO_CHECK.md snapshot has drifted from sentinel-oss — "
        "re-copy at staging time")


# =============================================== doc-76 additions (units)

def _fixture_mp4(tmp_path: Path) -> Path:
    """A synthetic IAMF-in-MP4 built from the iamf-sentinel clean-room fixtures
    (no sample staging needed).

    The source checkout is resolved by `conftest._find_oss_source()` and put on
    `sys.path` there; the callers carry `@needs_oss_src` so an absent checkout
    skips rather than fails (doc 105 — this hard-coded the internal directory
    name `sentinel-oss` until stage (v) publication prep)."""
    from fixtures.build import build, channel_spec
    from fixtures.mp4wrap import wrap_mp4
    p = tmp_path / "wrapped.mp4"
    p.write_bytes(wrap_mp4(build(channel_spec("stereo"))))
    return p


@needs_oss_src
def test_inspect_mp4_carries_container_block(tmp_path: Path):
    out = iamf_inspect(str(_fixture_mp4(tmp_path)))
    assert out["container"] == "mp4"
    mp4 = out["mp4"]
    assert set(mp4) == {"edts_present", "elst_entries", "video_present",
                        "descriptor_bytes"}
    assert mp4["descriptor_bytes"] > 0
    assert out["trim"]["frames_with_trim"] == 0        # clean fixture: no trim
    assert out["codec_configs"][0]["codec"] == "ipcm"


@needs_oss_src
def test_validate_mp4_path(tmp_path: Path):
    out = iamf_validate(str(_fixture_mp4(tmp_path)))
    assert out["summary"]["container"] == "mp4"
    assert out["exit_code"] in (0, 1)                  # parsed, judged — not ERROR


def test_f_register_bundled_fallback(monkeypatch, tmp_path: Path):
    """When no live F_TO_CHECK.md is locatable, the staged package snapshot
    serves (the drift tripwire elsewhere keeps the two in sync)."""
    import iamf_sentinel_mcp.server as srv
    fake_pkg = tmp_path / "site-packages/sentinel/__init__.py"
    fake_pkg.parent.mkdir(parents=True)
    fake_pkg.write_text("", encoding="utf-8")
    monkeypatch.setattr(srv._sentinel_pkg, "__file__", str(fake_pkg))
    text = srv._f_register_text()
    assert text == srv._F_REGISTER_BUNDLED.read_text(encoding="utf-8")


def test_main_registers_loom_run_only_with_flag(monkeypatch):
    import iamf_sentinel_mcp.server as srv
    calls = []

    class _FakeServer:
        def run(self):
            calls.append("ran")

    def fake_build(enable_run=False):
        calls.append(f"build(enable_run={enable_run})")
        return _FakeServer()

    monkeypatch.setattr(srv, "build_server", fake_build)
    monkeypatch.setattr("sys.argv", ["iamf-sentinel-mcp"])
    srv.main()
    assert calls == ["build(enable_run=False)", "ran"]  # read-only default posture
    calls.clear()
    monkeypatch.setattr("sys.argv", ["iamf-sentinel-mcp", "--enable-run"])
    srv.main()
    assert calls == ["build(enable_run=True)", "ran"]
