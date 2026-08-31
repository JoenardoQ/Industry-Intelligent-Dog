from __future__ import annotations

import re
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "create_shortcut.ps1"
WINDOWS_LAUNCHER = Path(__file__).resolve().parents[1] / "windows_launcher.ps1"


class ShortcutScriptTests(unittest.TestCase):
    def test_wsl_home_shortcut_uses_the_windows_lifecycle_launcher(self):
        script = SCRIPT.read_text(encoding="utf-8")
        branch_match = re.search(
            r"(?ms)^if[ \t]*\(\$IsWslHome\)[ \t]*\{[ \t]*\r?\n"
            r"(.*?)^}[ \t]*elseif[ \t]*\(\$NativeReady\)[ \t]*\{",
            script,
        )
        self.assertIsNotNone(branch_match)
        wsl_home_branch = branch_match.group(1)
        expected_assignments = {
            "WindowsLauncher": 'Join-Path $AppDir "windows_launcher.ps1"',
            "Shortcut.TargetPath": '"$env:WINDIR\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"',
            "Shortcut.Arguments": (
                '"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
                '-File `"$WindowsLauncher`""'
            ),
        }
        for variable, expected_rhs in expected_assignments.items():
            assignments = re.findall(
                rf"(?m)^[ \t]*\${re.escape(variable)}[ \t]*=[ \t]*(.*?)[ \t]*$",
                wsl_home_branch,
            )
            self.assertEqual(assignments, [expected_rhs], variable)
        self.assertNotIn("run_intdog.sh", wsl_home_branch)
        self.assertIn("windows_launcher.ps1", wsl_home_branch)
        self.assertNotIn('/mnt/d/IntDog', script)

    def test_windows_launcher_does_not_treat_missing_native_exit_code_as_failure(self):
        script = WINDOWS_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("$PrepareSucceeded = $?", script)
        self.assertIn("if (-not $PrepareSucceeded)", script)
        self.assertNotIn("if ($Prepare.ExitCode -ne 0)", script)
        self.assertIn('$LogDir = Join-Path $env:LOCALAPPDATA "IntDog"', script)
        self.assertIn('$LogPath = Join-Path $LogDir "launcher.log"', script)


if __name__ == "__main__":
    unittest.main()
