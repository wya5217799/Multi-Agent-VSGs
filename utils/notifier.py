"""Windows balloon-tip notification wrapper.

Sends non-blocking system-tray balloon notifications via PowerShell.
Falls back to console print if PowerShell is unavailable or fails.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import warnings

# Windows-only flag; safe to use 0 on non-Windows (never reaches Popen there)
_CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def notify(title: str, body: str, duration_ms: int = 5000) -> None:
    """Send a Windows balloon notification (non-blocking).

    Falls back to stderr print if PowerShell invocation fails or
    the platform is not Windows.
    """
    if sys.platform != "win32":
        _console_fallback(title, body)
        return
    try:
        _send_balloon(title, body, duration_ms)
    except Exception as exc:
        warnings.warn(f"[notifier] Balloon failed: {exc}", stacklevel=2)
        _console_fallback(title, body)


def _console_fallback(title: str, body: str) -> None:
    print(f"[NOTIFY] {title} | {body}", file=sys.stderr, flush=True)


def _sanitize(s: str) -> str:
    """Escape single-quotes and strip newlines for PowerShell string interpolation."""
    return s.replace("'", "''").replace("\n", " ").replace("\r", "")


def _send_balloon(title: str, body: str, duration_ms: int) -> None:
    duration_ms = max(100, int(duration_ms))  # guard against non-int or negative values
    t = _sanitize(title)
    b = _sanitize(body)
    # NotifyIcon balloon: no extra PowerShell modules required on any Windows 10/11 system
    script = textwrap.dedent(f"""
        Add-Type -AssemblyName System.Windows.Forms
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Information
        $n.Visible = $true
        $n.ShowBalloonTip({duration_ms}, '{t}', '{b}', [System.Windows.Forms.ToolTipIcon]::Info)
        Start-Sleep -Milliseconds {duration_ms + 1000}
        $n.Visible = $false
        $n.Dispose()
    """).strip()
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", script],
        creationflags=_CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
