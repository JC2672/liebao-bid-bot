"""OS-native helpers. Windows-only, matching the project's "my machine only"
scope (see docs/ARCHITECTURE.md).

A browser's own folder picker (the File System Access API) deliberately never
exposes a real absolute filesystem path - by design, for security. Since the
backend runs on the same machine as the browser here, it can shell out to a
real native folder-picker dialog instead and hand back the actual path.
"""
from __future__ import annotations

import subprocess

_PICK_FOLDER_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "{description}"
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.SelectedPath
}}
"""


def pick_folder(description: str = "Select a folder") -> str | None:
    """Blocks (briefly) while a native folder-picker dialog is shown. Returns
    the chosen absolute path, or None if the user cancelled."""
    safe_description = description.replace('"', "'")
    script = _PICK_FOLDER_SCRIPT.format(description=safe_description)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
        capture_output=True, text=True, timeout=120,
    )
    path = result.stdout.strip()
    return path or None
