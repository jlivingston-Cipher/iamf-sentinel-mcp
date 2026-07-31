"""Shared test support for iamf-sentinel-mcp (doc 105, stage (v)).

Same shape as `iamf-sentinel-pro`'s conftest (doc 97, item 24), for the same
reason: two of this suite's tests build real IAMF bytes with the core's
fixture builders, and `fixtures/build.py` / `fixtures/mp4wrap.py` ship in the
`iamf-sentinel` **source** tree, not in the installed wheel — the wheel carries
`sentinel/`, not `fixtures/`.

Before doc 105 this module hard-coded `parents[2] / "sentinel-oss"`, the
internal monorepo directory name. That path exists only inside the private
tree, so a standalone clone of the public repo did not skip those two tests —
it **failed** them at call time with `ModuleNotFoundError: fixtures`. Item 24
found exactly this in both published repos; stage (v) carried it too, and
this file is the fix landing *before* the repo is public rather than after.

Resolution order is `$IAMF_SENTINEL_SRC`, then a sibling `sentinel-oss/`
(internal tree layout), then a sibling `iamf-sentinel/` (public side-by-side
clones). Absent all three, the dependent tests skip cleanly with a reason that
tells the reader what to do about it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _find_oss_source() -> Path | None:
    """Locate an `iamf-sentinel` SOURCE checkout that carries `fixtures/`."""
    candidates: list[Path] = []
    env = os.environ.get("IAMF_SENTINEL_SRC")
    if env:
        candidates.append(Path(env))
    candidates += [
        _REPO_ROOT.parent / "sentinel-oss",     # internal tree layout
        _REPO_ROOT.parent / "iamf-sentinel",    # public side-by-side clones
    ]
    for c in candidates:
        if (c / "fixtures" / "build.py").is_file():
            return c.resolve()
    return None


OSS_SRC: Path | None = _find_oss_source()

NO_OSS_SRC_REASON = (
    "iamf-sentinel source checkout not found — clone it beside this repo or "
    "set $IAMF_SENTINEL_SRC (the fixture builders live in the core's source "
    "tree, not in the installed wheel)"
)

#: Tests that need the core's clean-room fixture builders.
needs_oss_src = pytest.mark.skipif(OSS_SRC is None, reason=NO_OSS_SRC_REASON)

for _p in ([str(_REPO_ROOT)] + ([str(OSS_SRC)] if OSS_SRC else [])):
    if _p not in sys.path:
        sys.path.insert(0, _p)
