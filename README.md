# iamf-sentinel-mcp

An [MCP](https://modelcontextprotocol.io) server exposing
**[iamf-sentinel](https://github.com/jlivingston-Cipher/iamf-sentinel)** (IAMF conformance validator) and
**[iamf-loom](https://github.com/jlivingston-Cipher/iamf-loom)** (IAMF packager) to MCP clients — Claude Desktop,
Claude Code, and any other agent runtime that speaks the protocol.

IAMF is the Alliance for Open Media's Immersive Audio Model and Formats
(v1.1.0). This server lets an agent validate IAMF files against the spec's
conformance rules and compile packaging manifests into inspectable,
deterministic plans — without executing anything (execution is a separate,
per-launch opt-in — see below).

Code comments throughout cite an internal numbered design docset (`doc NN`), ADRs, and pre-registered expectation labels — **[DESIGN-NOTES.md](DESIGN-NOTES.md)** explains the notation and indexes every cited document.

## Tools

| Tool | What it does | Needs toolchain |
|---|---|---|
| `iamf_validate` | Full conformance report on a `.iamf` / IAMF-in-MP4 file: S-code findings with severities, summary, stream facts. `strict` promotes WARN to failing. | no |
| `iamf_inspect` | Structure orientation: profiles, codec configs (incl. Opus pre-skip), element/presentation/frame counts, OBU trim totals, MP4 edts/elst presence. | no |
| `loom_compile` | Compile a Loom manifest (YAML/JSON) to its packaging plan — validate-only. Per-target backend/muxer routing with rationale, or M-code diagnostics. | no |
| `loom_explain` | `loom explain` as text: the compiled plan as its own justification. | no |
| `loom_run` | Compile **and execute** a manifest: encode, mux, measure, and gate every output through the Sentinel validator. Returns per-target outputs (sha256), gate verdicts, measured loudness, and the run-ledger path. **Only registered when the server is launched with `--enable-run`.** | **yes** |

## Resources

- `checks://catalog` — every S-code check the validator can emit: severity,
  layer, title, description, related F-register entries.
- `mcodes://catalog` — every M-code compile diagnostic the packager can
  report, with its stable summary (retired codes kept for the record).
- `fregister://catalog` — the failure-mode register (F_TO_CHECK.md): the
  WP1/WP3 failure catalogue mapped to Sentinel checks, as markdown.

## Run

```bash
pip install iamf-sentinel-mcp
iamf-sentinel-mcp                # stdio transport, read-only (default)
iamf-sentinel-mcp --enable-run   # additionally registers loom_run (executes)
```

Claude Desktop / Code config:

```json
{ "mcpServers": { "iamf-sentinel-mcp": { "command": "iamf-sentinel-mcp" } } }
```

## Scope and posture

- **Read-only by default.** Without `--enable-run`, tools parse and compile;
  nothing is executed, no files are written, no network is touched.
- **Execution is opt-in, per launch.** `--enable-run` registers `loom_run`,
  which runs the encoder toolchain as subprocesses and writes files; the
  Sentinel gate inside `loom run` stays on by default. A missing toolchain
  is an actionable error naming the expected binary path. Sentinel L3
  rendered-loudness QC remains unexposed.
- The server is a thin wrapper over the products' public APIs; conformance
  logic lives in the products, behind their own test gates.

Apache-2.0 (see `LICENSE` / `NOTICE`), like everything else in the
iamf-sentinel / iamf-loom stack. Support posture: see the core repo's
[`SUPPORT.md`](https://github.com/jlivingston-Cipher/iamf-sentinel/blob/main/SUPPORT.md).
