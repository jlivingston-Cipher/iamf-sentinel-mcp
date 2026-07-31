"""Named regression: `fregister://catalog` must decode as UTF-8 everywhere.

Doc 98 found that the products wrote and read text in the *locale* encoding —
ten sites in `iamf-loom`, one in `iamf-sentinel` — and fixed them. The
`iamf-sentinel-mcp` tree was outside item 24's scope and kept two of them:
`_f_register_text()` called `Path.read_text()` with no `encoding=` on both the
live-register and bundled-snapshot branches.

`F_TO_CHECK.md` carries 356 non-ASCII bytes (§ ± × Δ Σ – — → − ≈ ≠ ≤ ✅ ⛔ …).
Under a cp1252 client — the Windows default, and Windows is a first-class MCP
client platform — the no-encoding read does **not** raise. It silently
mojibakes: `→` is served to the model as `â†'`. Nothing in the suite caught
that, because the drift tripwire compares `read_bytes()` and the content test
asserts only ASCII substrings, both of which survive full mojibake. Doc 98's
lesson restated: a symmetric bug is invisible to a symmetric test.

Why a subprocess: `Path.read_text()` resolves the default encoding in CPython's
C layer, so monkeypatching `locale.getencoding` does **not** change what it
does — a monkeypatch-based version of this test passes identically with and
without the fix, i.e. it tests nothing (verified, doc 105 §4). The only
faithful reproduction on Linux is a real interpreter under a real ASCII locale
with PEP 538/540 coercion disabled, which is what this does. Under the defect
the child dies with UnicodeDecodeError; under the fix it round-trips the
non-ASCII characters exactly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# A character that exists in the register and is not representable in ASCII.
PROBE = "→"          # RIGHTWARDS ARROW, the F-register's trace glyph

_CHILD = r"""
import sys
from iamf_sentinel_mcp.server import f_register
text = f_register()
sys.stdout.buffer.write(text.encode("utf-8"))
"""


def _ascii_locale_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        LC_ALL="C", LANG="C",
        PYTHONCOERCECLOCALE="0",     # PEP 538 off: do not coerce C -> C.UTF-8
        PYTHONUTF8="0",              # PEP 540 off: no UTF-8 mode fallback
        PYTHONIOENCODING="utf-8",    # keep the *pipe* clean; the defect is file I/O
    )
    return env


def test_f_register_decodes_as_utf8_under_an_ascii_locale():
    """The register survives a non-UTF-8 default encoding (doc 98 class)."""
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=_ascii_locale_env(),
        capture_output=True, check=False,
    )
    assert proc.returncode == 0, (
        "f_register() failed under an ASCII default encoding — the register "
        "is being read in the locale encoding instead of UTF-8:\n"
        + proc.stderr.decode("utf-8", "replace")[-1500:]
    )
    text = proc.stdout.decode("utf-8")
    assert PROBE in text, (
        "the register decoded without error but lost its non-ASCII content — "
        "this is the silent-mojibake half of the defect"
    )


def test_f_register_matches_its_source_exactly():
    """Whichever branch served it, the text matches the source's text.

    This is the mojibake detector that works in-process: mojibake changes the
    character sequence, so the comparison stops matching even though every
    ASCII assertion still passes.

    TEXT to TEXT, deliberately. The first version of this test compared
    `_f_register_text().encode("utf-8")` to `source.read_bytes()` — and
    `read_text()` applies universal-newline translation while `read_bytes()`
    does not, so on any checkout that stores CRLF the two could never be
    equal. It went red on all three Windows legs of the first hosted run
    (doc 105 §11.5). That is doc 97's newline class, written by me into the
    guard for doc 98's encoding class, in the same file. Newline policy is not
    what this test is about; mojibake is, and mojibake changes CHARACTERS, so
    the text comparison detects it and the byte comparison only added a
    platform dependency.
    """
    from iamf_sentinel_mcp.server import _F_REGISTER_BUNDLED, _f_register_text
    import iamf_sentinel_mcp.server as srv

    live = (Path(srv._sentinel_pkg.__file__).resolve().parent.parent
            / "F_TO_CHECK.md")
    source = live if live.is_file() else _F_REGISTER_BUNDLED
    assert _f_register_text() == source.read_text(encoding="utf-8")


@pytest.mark.parametrize("path_attr", ["_F_REGISTER_BUNDLED"])
def test_bundled_register_is_valid_utf8(path_attr: str):
    """The shipped package data is UTF-8 in the first place."""
    from iamf_sentinel_mcp import server as srv
    getattr(srv, path_attr).read_bytes().decode("utf-8")   # raises if not
