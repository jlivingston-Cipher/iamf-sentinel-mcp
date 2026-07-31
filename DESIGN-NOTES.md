# Design notes — reading the provenance references in this codebase

This project was developed against an internal, numbered design docset: every work
cycle produced a numbered document recording what was decided, what was measured, and
the evidence behind both. Code comments cite those records rather than restating them
(`doc 73`, `E-75.3`, `R-74.2`, …). The docset itself is not published, but the
notation is simple and the index below preserves the context each citation carries.

The validator's copy of this file (`iamf-sentinel/DESIGN-NOTES.md`) carries the full
shared notation; the short version plus this server's own labels:

## Notation

| Form | Meaning |
|---|---|
| `doc NN` | A numbered internal design/evidence document; see the index below. |
| `E-74.N`, `E-75.N` | Pre-registered expectations for this server's two build cycles (doc 74 = Cycle A, doc 75 = Cycle B): written before implementation, then confirmed. The test docstrings cite the expectation each test pins. |
| `R-74.N`, `R-75.N` | The numbered requirements/risks of those cycles (e.g. `R-74.2`: the SDK's in-memory session harness may move — tests skip rather than error; `R-75.2`: the enable-run ordering contract). |
| `ADR-N` | Architecture Decision Records of the underlying projects. |
| `F-…`, `S-…`, `M-…` | The failure register (bundled here as `data/F_TO_CHECK.md`, served by `fregister://catalog`), Sentinel check IDs (`checks://catalog`), and Loom diagnostic codes (`mcodes://catalog`). The three catalogue resources are the shipped, self-describing form of these registries. |
| `WP1`, `WP3` | The validation work packages whose sample corpora some tests use (they skip with staging instructions when absent). |

## Index of cited documents

| Doc | What it established |
|---|---|
| 02 / 04 / 05 / 07 | Ecosystem and format fact bases (landscape; Dolby Atmos; MPEG-H/DTS/Audio Vivid; platform IAMF support). |
| 13 | The iamf-loom PRD. |
| 19 | Sentinel L3 rendered QC (not exposed by this server; the boundary is noted where relevant). |
| 56 / 57 / 60 / 61 / 63 / 64 / 66 | Findings history carried by the bundled failure register (F5 refutation; F31 root cause; F32 adjudication; ADR-2 context replacement; verification cycles; the BS.1770-4 revision audit; F33 opened). |
| 69 / 70 / 71 | F33 and F34 fixes in the underlying projects; F32 filed upstream (gpac/gpac#3826). |
| 73 | The decision brief to ship this MCP server: adopt, separate repo, read-only by default. |
| 74 | Cycle A: the four read-only tools + `checks://catalog`, the in-memory wire-path test. |
| 75 | Cycle B: `loom_run` registered only behind `--enable-run` (the read-only default posture), `mcodes://catalog`, `fregister://catalog` with its live-else-bundled resolution and drift tripwire. |
