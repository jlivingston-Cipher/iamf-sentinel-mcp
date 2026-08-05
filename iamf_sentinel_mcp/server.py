"""The MCP server: the four toolchain-free tools + the catalogue resources,
plus `loom_run` behind an explicit opt-in launch flag (Cycle B).

Wrapper discipline (doc 73 §7): tools marshal existing public APIs and return
structured data; they never raise domain exceptions through the tool boundary
and never contain validation/packaging logic of their own. Execution
(`loom_run`) registers only when the server is launched with `--enable-run`;
a missing toolchain is then an actionable call-time error, never a traceback.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from iamf_sentinel_mcp import __version__

import sentinel as _sentinel_pkg
from sentinel import model as smodel
from sentinel.engine import Report, validate as sentinel_validate
from sentinel.findings import REGISTRY, Severity
from sentinel.report import render_json

from loom.compiler import compile_manifest
from loom.diagnostics import CODES as M_CODES, CompileError
from loom.executor import Executor
from loom.explain import render_explain
from loom.manifest import load_manifest

# ---------------------------------------------------------------- helpers

def _diag_list(e: CompileError) -> list[dict[str, str]]:
    return [{"code": d.code, "path": d.path, "message": d.message}
            for d in e.diagnostics]


def _loom_load(manifest_path: str, variables: dict[str, str] | None):
    """load+compile, returning (manifest, plan, None) or (None, None, diags)."""
    try:
        m = load_manifest(manifest_path, variables=variables or None)
        plan = compile_manifest(m)
        return m, plan, None
    except CompileError as e:
        return None, None, _diag_list(e)


# ------------------------------------------------------------------ tools

def iamf_validate(path: str, profile: str = "generic",
                  strict: bool = False) -> dict[str, Any]:
    """Validate an IAMF file (raw .iamf or IAMF-in-MP4) with iamf-sentinel.

    Runs the structural (L1) and semantic (L2) conformance checks — including
    the container trim-carriage checks S-407/S-408/S-409 — and returns the
    full report: a summary (PASS/FAIL/ERROR, finding counts, stream facts)
    and every finding with its S-code, severity, message, and offsets.
    `strict` treats WARN findings as failing. `profile` selects a validation
    profile (default "generic"). L3 rendered-loudness QC needs the decoder
    toolchain and is not exposed by this server version.
    """
    fail_on = Severity.WARN if strict else Severity.FAIL
    report = sentinel_validate(path, profile=profile, fail_on=fail_on)
    return json.loads(render_json(report))


def iamf_inspect(path: str) -> dict[str, Any]:
    """Summarize an IAMF file's structure without judging conformance.

    Returns the container kind, IA sequence header profiles, codec configs
    (codec, samples/frame, sample rate, Opus pre-skip), element and
    presentation counts, audio-frame count, and start/end trim totals as
    parsed from the OBUs — plus, for MP4, whether edts/elst is present.
    Use iamf_validate for conformance findings; this tool is for orientation.
    """
    report: Report = sentinel_validate(path)
    out: dict[str, Any] = {"source": report.source,
                           "container": report.container}
    if report.execution_error:
        out["execution_error"] = report.execution_error
        return out
    mod = report.model
    if mod is None:
        out["note"] = "no parseable IAMF payload"
        return out
    if mod.sequence_header:
        out["sequence_header"] = {
            "ia_code": mod.sequence_header.ia_code,
            "primary_profile": smodel.PROFILE_NAME.get(
                mod.sequence_header.primary_profile,
                mod.sequence_header.primary_profile),
            "additional_profile": smodel.PROFILE_NAME.get(
                mod.sequence_header.additional_profile,
                mod.sequence_header.additional_profile),
        }
    out["codec_configs"] = [
        {"id": cc.codec_config_id, "codec": cc.codec_id,
         "num_samples_per_frame": cc.num_samples_per_frame,
         "sample_rate": cc.sample_rate, "bit_depth": cc.bit_depth,
         "opus_pre_skip": cc.opus_pre_skip}
        for cc in mod.codec_configs.values()
    ]
    out["audio_elements"] = len(mod.audio_elements)
    out["mix_presentations"] = len(mod.mix_presentations)
    out["audio_frames"] = len(mod.audio_frames)
    frames = mod.audio_frames
    if report.mp4 is not None and report.mp4.frame_refs:
        frames = report.mp4.frame_refs
    trim_start = trim_end = 0
    frames_with_trim = 0
    for fr in frames:
        s = getattr(fr, "trim_start", 0) or 0
        e = getattr(fr, "trim_end", 0) or 0
        if s or e:
            frames_with_trim += 1
        trim_start += s
        trim_end += e
    out["trim"] = {"frames_with_trim": frames_with_trim,
                   "total_start": trim_start, "total_end": trim_end}
    if report.mp4 is not None:
        mp4 = report.mp4
        out["mp4"] = {
            "edts_present": any(getattr(t, "edts_present", False)
                                for t in mp4.tracks),
            "elst_entries": sum(len(getattr(t, "elst_entries", []))
                                for t in mp4.tracks),
            "video_present": mp4.video_present,
            "descriptor_bytes": len(mp4.descriptor_obus or b""),
        }
    return out


def loom_compile(manifest_path: str,
                 variables: dict[str, str] | None = None) -> dict[str, Any]:
    """Compile an iamf-loom manifest (YAML/JSON) to its packaging plan.

    Validate-only: nothing is executed and no files are written. Returns
    ok=true with a plan summary — per-target backend/muxer routing with the
    ADR-grounded rationale, and each step's id/kind/tool — or ok=false with
    the M-code diagnostics exactly as `loom compile` would report them.
    `variables` fills `{variable}` placeholders (the CLI's --var).
    """
    m, plan, diags = _loom_load(manifest_path, variables)
    if diags is not None:
        return {"ok": False, "diagnostics": diags}
    by_id = {s.id: s for s in plan.steps}
    targets = []
    for t in plan.targets:
        targets.append({
            "out": t.out, "format": t.format,
            "backend": t.backend, "muxer": t.muxer,
            "profile": t.profile, "rationale": t.rationale,
            "steps": [{"id": sid, "kind": by_id[sid].kind,
                       "tool": by_id[sid].tool}
                      for sid in t.step_ids if sid in by_id],
        })
    return {"ok": True, "title": m.title, "targets": targets}


def loom_explain(manifest_path: str,
                 variables: dict[str, str] | None = None) -> dict[str, Any]:
    """Render `loom explain` for a manifest: the compiled plan as its own
    justification, in plain text.

    The output walks every target: why it routed to its backend/muxer (ADR
    grounding, F-number references), what every step does and why it exists,
    and which values resolve only at execution time. Returns ok=true with the
    text, or ok=false with M-code diagnostics.
    """
    m, plan, diags = _loom_load(manifest_path, variables)
    if diags is not None:
        return {"ok": False, "diagnostics": diags}
    return {"ok": True, "text": render_explain(m, plan)}


# ------------------------------------------------- execution (opt-in only)

def loom_run(manifest_path: str,
             variables: dict[str, str] | None = None,
             out_dir: str | None = None,
             toolchain: str | None = None) -> dict[str, Any]:
    """Compile AND EXECUTE an iamf-loom manifest — writes files, runs the
    encoder toolchain as subprocesses, and gates every output through the
    Sentinel validator (on by default, per the manifest's `policy.validate`).

    Requires the decoder/encoder toolchain; a missing binary is reported as
    an actionable failure naming the expected path. Outputs land in
    `out_dir` (default: the manifest's directory). Returns ok, per-target
    outputs (sha256/bytes/backend/profile), the Sentinel gate verdicts,
    measured loudness, any failures, and the run-ledger path. This tool is
    only registered when the server was launched with --enable-run.
    """
    m, plan, diags = _loom_load(manifest_path, variables)
    if diags is not None:
        return {"ok": False, "diagnostics": diags}
    out = Path(out_dir) if out_dir else Path(m.manifest_dir)
    ex = Executor(plan, m.manifest_dir, out, out / ".loom-work",
                  toolchain=toolchain,
                  validate_policy=m.policy.validate)
    res = ex.run()
    return {
        "ok": res.ok,
        "failures": res.failures,
        "outputs": ex.ledger["outputs"],
        "gate": ex.ledger["gate"],
        "measured_loudness": ex.ledger["measured_loudness"],
        "ledger_path": str(res.ledger_path) if res.ledger_path else None,
    }


def build_server(enable_run: bool = False) -> MCPServer:
    """Construct a fresh, fully-registered server instance (X-76a factory).

    Every call returns an independent MCPServer — tests build isolated
    instances instead of mutating a shared module-level server, which
    retires the doc-75 registration-ordering contract (R-75.2). Execution
    (`loom_run`) registers iff enable_run; the read-only default posture
    (doc 73 §4) is the default argument."""
    server = MCPServer(
        "iamf-sentinel",
        # v2 advertises a server version in the initialize result; v1's
        # FastMCP had no such field, so this is new surface the port buys.
        version=__version__,
        instructions=(
            "IAMF conformance validation (iamf-sentinel) and packaging-plan "
            "compilation (iamf-loom). Validate IAMF files (.iamf or IAMF-in-MP4) "
            "and get structured S-code findings; compile Loom manifests to "
            "deterministic packaging plans and read the plan's own justification "
            "via explain. Read checks://catalog for what each S-code means, "
            "mcodes://catalog for Loom's compile diagnostics, and "
            "fregister://catalog for the failure-mode register behind the "
            "checks. Execution (loom_run) is available only when the server was "
            "launched with --enable-run."
        ),
    )
    server.add_tool(iamf_validate)
    server.add_tool(iamf_inspect)
    server.add_tool(loom_compile)
    server.add_tool(loom_explain)
    if enable_run:
        server.add_tool(loom_run, name="loom_run")
    server.resource("checks://catalog")(checks_catalog)
    server.resource("mcodes://catalog")(mcodes_catalog)
    server.resource("fregister://catalog")(f_register)
    return server


# -------------------------------------------------------------- resources

def checks_catalog() -> str:
    """The S-code check catalogue: every check iamf-sentinel can emit, with
    severity, layer, title, description, and related F-register entries."""
    entries = []
    for cid in sorted(REGISTRY):
        c = REGISTRY[cid]
        entries.append({
            "id": c.id, "severity": c.default_severity.label,
            "layer": c.layer, "title": c.title,
            "description": c.description or "",
            "f_refs": list(c.f_refs),
        })
    return json.dumps({"checks": entries, "count": len(entries)}, indent=2)


def mcodes_catalog() -> str:
    """The M-code catalogue: every compile-time diagnostic iamf-loom can
    report, with its stable summary. Codes marked retired are kept for the
    stable-contract record and are no longer emitted."""
    codes = [{"code": c, "summary": s,
              "retired": "no longer emitted" in s}
             for c, s in sorted(M_CODES.items())]
    return json.dumps({"codes": codes, "count": len(codes)}, indent=2)


_F_REGISTER_BUNDLED = Path(__file__).parent / "data" / "F_TO_CHECK.md"


def _f_register_text() -> str:
    """The live sentinel-oss F_TO_CHECK.md when locatable (monorepo/dev
    layout: repo root above the installed `sentinel` package), else the
    snapshot bundled as package data at staging time.

    Always UTF-8, never the locale encoding (doc 98 class; doc 105): the
    register carries several hundred non-ASCII bytes (402 at the time of
    writing; illustrative, asserted nowhere) and a cp1252 client would
    mojibake them silently rather than fail."""
    live = Path(_sentinel_pkg.__file__).resolve().parent.parent / "F_TO_CHECK.md"
    if live.is_file():
        return live.read_text(encoding="utf-8")
    return _F_REGISTER_BUNDLED.read_text(encoding="utf-8")


def f_register() -> str:
    """The failure-mode register (F_TO_CHECK.md): the WP1/WP3 failure
    catalogue mapped to Sentinel checks — what each F-number means, whether
    a check fires for it, and its disposition. Markdown."""
    return _f_register_text()


def main() -> None:
    ap = argparse.ArgumentParser(prog="iamf-sentinel-mcp")
    ap.add_argument(
        "--enable-run", action="store_true",
        help="register loom_run (executes the toolchain and writes files); "
             "off by default — the server is read-only without this flag")
    args = ap.parse_args()
    build_server(enable_run=args.enable_run).run()   # stdio transport


if __name__ == "__main__":
    main()
