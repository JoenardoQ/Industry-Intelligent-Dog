from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
spec = importlib.util.spec_from_file_location("intdog_launcher", APP_ROOT / "launch_intdog.py")
launcher = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


class WebLauncherTests(unittest.TestCase):
    def test_first_install_uses_the_local_editable_backend(self):
        command = launcher._editable_install_command(Path("/runtime/python"))
        self.assertIn("--disable-pip-version-check", command)
        self.assertEqual(command[-2], "-e")
        self.assertEqual(Path(command[-1]), launcher.SEARCH_DIR)

    def test_installed_runtime_probe_does_not_depend_on_repository_imports(self):
        from unittest.mock import patch
        completed = __import__("subprocess").CompletedProcess([], 0)
        with patch.object(launcher.subprocess, "run", return_value=completed) as run:
            self.assertTrue(launcher._python_runtime_ready(Path("/runtime/python")))
        args, kwargs = run.call_args
        self.assertEqual(args[0][:2], ["/runtime/python", "-c"])
        self.assertIn("distribution('intdog-domain-intelligence')", args[0][2])
        self.assertEqual(Path(kwargs["cwd"]), launcher.RUNTIME_DIR)

    def test_browser_fallback_covers_chrome_and_edge_install_locations(self):
        candidates = launcher._windows_browser_candidates()
        self.assertEqual(len(candidates), 4)
        self.assertTrue(any("Google\\Chrome" in value for value in candidates))
        self.assertTrue(any("Microsoft\\Edge" in value for value in candidates))
        script = launcher._windows_app_mode_script(
            "http://127.0.0.1:8765", "test-session")
        for candidate in candidates:
            self.assertIn(candidate, script)
        self.assertIn("--app=http://127.0.0.1:8765", script)
        self.assertIn("#session=test-session", script)
        self.assertIn("X-IntDog-Session", script)
        self.assertIn("/api/shutdown", script)

    def test_app_window_owns_an_isolated_disposable_browser_profile(self):
        script = launcher._windows_app_mode_script(
            "http://127.0.0.1:8765", "test-session")
        expected_profile_id = "4943e43bc034c8bf"
        self.assertIn("IntDog\\Sessions", script)
        self.assertIn(expected_profile_id, script)
        self.assertNotIn("IntDog\\ChromeProfile", script)
        self.assertIn("--disable-background-mode", script)
        self.assertIn("Remove-Item -LiteralPath $profile", script)
        self.assertLess(script.index("--user-data-dir"), script.index("--app="))
        self.assertIn("$p.WaitForExit()", script)
        self.assertLess(script.index("$p.WaitForExit()"), script.index("/api/shutdown"))
        self.assertLess(script.index("/api/shutdown"), script.index("Remove-Item"))

    def test_default_and_legacy_launch_share_one_instance_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            lock_type = __import__("runtime.single_instance", fromlist=["SingleInstanceLock"]).SingleInstanceLock
            first = lock_type(Path(temp) / "desktop.lock")
            second = lock_type(Path(temp) / "desktop.lock")
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()


if __name__ == "__main__":
    unittest.main()
