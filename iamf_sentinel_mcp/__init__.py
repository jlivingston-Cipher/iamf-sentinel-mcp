"""iamf-sentinel-mcp — MCP server exposing the iamf-sentinel validator and the
iamf-loom packager to MCP clients (agents).

A thin wrapper (doc 73): every tool marshals an existing public API. The
default posture is read-only (validate/inspect/compile/explain + the
checks/mcodes/fregister catalogue resources); `loom_run` — toolchain
execution, file writes, the Sentinel gate — registers only when the server
is launched with `--enable-run` (Cycle B, doc 75).
"""

__version__ = "0.2.0"
