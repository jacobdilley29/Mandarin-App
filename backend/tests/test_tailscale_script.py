"""Finding the Tailscale CLI (spec §7 — phone access is over the tailnet).

The app binds to loopback, so Tailscale Serve is the only way in from a phone.
That makes `scripts/tailscale-serve.sh` the front door, and it used to look for
the CLI on PATH alone — which fails on the Mac App Store build, where the CLI
lives inside the app bundle and is never put on PATH. The script then reports
"not installed" about an app sitting in /Applications.

These run the real script against stub executables, so they work on a machine
with no Tailscale at all — this sandbox, and CI.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "tailscale-serve.sh"

STUB = """#!/usr/bin/env bash
echo "$0 $*" >> "$TS_STUB_LOG"
case "$1" in
  status)
    [[ "${2:-}" == "--json" ]] && echo '{"Self":{"DNSName":"macbook.tail1234.ts.net."}}'
    exit 0 ;;
  serve) exit 0 ;;
esac
exit 0
"""


def _stub(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STUB, encoding="utf-8")
    path.chmod(0o755)
    return path


def _run(tmp_path: Path, *args: str, on_path: bool = False, in_bundle: bool = False):
    """Run the script with a PATH containing only what we put there."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    # Real tools the script needs (bash builtins aren't enough: grep, cut, sed…).
    for tool in ("bash", "grep", "cut", "sed", "head", "tr", "curl", "printf"):
        src = subprocess.run(["which", tool], capture_output=True, text=True).stdout.strip()
        if src and not (bin_dir / tool).exists():
            (bin_dir / tool).symlink_to(src)

    log = tmp_path / "calls.log"
    if on_path:
        _stub(bin_dir / "tailscale")
    if in_bundle:
        _stub(tmp_path / "Applications/Tailscale.app/Contents/MacOS/Tailscale")

    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": str(bin_dir),
            "HOME": str(tmp_path),
            "TS_STUB_LOG": str(log),
        },
    ), log


# ---------------------------------------------------------------------------
# Finding it
# ---------------------------------------------------------------------------
def test_the_cli_on_path_is_used(tmp_path):
    result, log = _run(tmp_path, "--status", on_path=True)

    assert result.returncode == 0, result.stderr
    assert "serve status" in log.read_text(encoding="utf-8")


def test_the_app_bundle_is_found_when_path_has_nothing(tmp_path):
    """The Mac App Store case — the whole reason this resolver exists."""
    result, log = _run(tmp_path, "--status", in_bundle=True)

    assert result.returncode == 0, result.stderr
    assert "Tailscale.app" in log.read_text(encoding="utf-8")


def test_with_no_tailscale_anywhere_the_error_is_useful(tmp_path):
    result, _ = _run(tmp_path, "--status")

    assert result.returncode != 0
    assert "tailscale.com/download" in result.stderr
    assert "App Store" in result.stderr, "say why an installed app can be missing from PATH"


# ---------------------------------------------------------------------------
# Every path uses the resolved binary, not a bare `tailscale`
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("arg", ["--status", "--off"])
def test_each_subcommand_goes_through_the_resolved_binary(tmp_path, arg):
    """Two of the four call sites never hit the guard — they'd keep the bug."""
    result, log = _run(tmp_path, arg, in_bundle=True)

    assert result.returncode == 0, result.stderr
    assert "Tailscale.app" in log.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The serve path
# ---------------------------------------------------------------------------
SILENT_STUB = """#!/usr/bin/env bash
echo "$0 $*" >> "$TS_STUB_LOG"
case "$1" in
  status) [[ "${2:-}" == "--json" ]] && echo '{"Self":{}}'; exit 0 ;;
esac
exit 0
"""


def test_serving_prints_the_url(tmp_path):
    result, log = _run(tmp_path, "3002", in_bundle=True)

    assert result.returncode == 0, result.stderr
    assert "serve --bg 3002" in log.read_text(encoding="utf-8")
    assert "macbook.tail1234.ts.net" in result.stdout


def test_serving_survives_a_status_output_with_no_hostname(tmp_path):
    """The one that bit: `set -euo pipefail` plus a grep that matches nothing.

    The command substitution failed, so the script exited immediately after
    starting to serve — having printed no URL, no install hint and no way to
    stop it. Serving worked; the user was simply never told the address.
    """
    bundle = tmp_path / "Applications/Tailscale.app/Contents/MacOS/Tailscale"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(SILENT_STUB, encoding="utf-8")
    bundle.chmod(0o755)

    result, _ = _run(tmp_path, "3002")

    assert result.returncode == 0, "the script must not die just because it found no hostname"
    assert "Add to Home Screen" in result.stdout
    assert "--off" in result.stdout, "it still has to say how to stop"
