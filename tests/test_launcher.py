"""Exercise Windows port cleanup without touching real listeners or processes."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
@pytest.mark.parametrize(
    "scenario,expected_code,stopped",
    [
        ("free", 0, False),
        ("doclayout", 0, True),
        ("decline", 1, False),
        ("confirm", 0, True),
        ("denied", 1, False),
        ("changed", 1, False),
        ("stuck", 1, True),
    ],
)
def test_port_release(scenario, expected_code, stopped):
    helper = Path("doclayout/scripts/clear_gui_port.ps1").resolve()
    command = r"""
    $global:stopped = $false
    $global:lookups = 0
    function Get-NetTCPConnection {
        param($State)
        if ($scenario -ne 'free' -and (-not $global:stopped -or $scenario -eq 'stuck')) {
            [pscustomobject]@{LocalPort=8471; OwningProcess=12345}
            [pscustomobject]@{LocalPort=8471; OwningProcess=12345}
        }
        [pscustomobject]@{LocalPort=9999; OwningProcess=99999}
    }
    function Get-CimInstance {
        param($ClassName, $Filter)
        $global:lookups++
        $created = if ($scenario -eq 'changed') { $global:lookups } else { 1 }
        $line = if ($scenario -in @('decline','confirm')) { 'other app' } else {
            'python -m streamlit run doclayout/scripts/streamlit_app.py --server.port 8471'
        }
        [pscustomobject]@{Name='python.exe'; CommandLine=$line; CreationDate=$created}
    }
    function Read-Host { param($Prompt); if ($scenario -eq 'confirm') {'yes'} else {'no'} }
    function Stop-Process {
        param($Id, [switch]$Force, $ErrorAction)
        if ($Id -ne 12345 -or $global:stopped) { throw 'Wrong or duplicate target' }
        if ($scenario -eq 'denied') { throw 'Access denied' }
        $global:stopped = $true
        Write-Output 'MOCK_STOPPED'
    }
    function Start-Sleep { param($Milliseconds) }
    """
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"$scenario='{scenario}';" + command + f"& '{helper}'",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == expected_code, result.stdout + result.stderr
    assert not result.stderr, result.stderr
    assert ("MOCK_STOPPED" in result.stdout) == stopped
