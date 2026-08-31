from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from runtime.jobs import (  # noqa: E402
    JOB_LOG_BYTE_CAP,
    JobManager,
    JobStore,
    StreamingSanitizer,
    sanitize_command,
    sanitize_text,
)


class RuntimeJobTests(unittest.TestCase):
    def test_credentials_are_redacted_from_text_command_and_streams(self):
        secret = "credential-value-9347"
        self.assertNotIn(secret, sanitize_text(f"Authorization: Bearer {secret}"))
        self.assertEqual(sanitize_command(["tool", "--token", secret]),
                         ["tool", "--token", "***"])
        sample = f'{{"password":"{secret}"}}\n'
        for split in range(1, len(sample)):
            redactor = StreamingSanitizer()
            rendered = (redactor.feed(sample[:split])
                        + redactor.feed(sample[split:]) + redactor.finalize())
            self.assertNotIn(secret, rendered)

    def test_job_manifest_tracks_stage_progress_artifact_and_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp)
            result = manager.run_sync(
                [sys.executable, "-u", "-c",
                 "print('[阶段 2/4] 验证来源'); print('[完成] /tmp/report.md')"],
                cwd=temp, title="probe", timeout=10,
                metadata={"operation": "report", "parent_run_id": "old-run"},
            )
            self.assertEqual(result.status, "completed")
            row = manager.store.list()[0]
            self.assertEqual(row["stage"], "验证来源")
            self.assertEqual(row["progress"], 0.5)
            self.assertEqual(row["artifact_path"], "/tmp/report.md")
            self.assertEqual(row["parent_run_id"], "old-run")

    def test_cancel_kills_process_and_timeout_is_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp)
            job = manager.start(
                [sys.executable, "-u", "-c", "import time; print('ready',flush=True); time.sleep(30)"],
                cwd=temp, title="cancel", timeout=60,
            )
            time.sleep(0.2)
            self.assertTrue(job.cancel())
            self.assertEqual(job.wait(5).status, "cancelled")
            timed = manager.run_sync(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=temp, title="timeout", timeout=0.1,
            )
            self.assertEqual(timed.status, "failed")

    def test_stale_jobs_recover_and_logs_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(temp)
            store.write({"run_id": "stale", "status": "running",
                         "owner_pid": 999_999_999})
            self.assertEqual(JobManager(temp).recovered, 1)
            row = store.list()[0]
            self.assertEqual(row["status"], "interrupted")
            metadata = store.append_output("bounded", "x" * (JOB_LOG_BYTE_CAP * 2))
            self.assertTrue(metadata["output_truncated"])
            self.assertLessEqual((Path(temp) / "_jobs" / "bounded.log").stat().st_size,
                                 JOB_LOG_BYTE_CAP)

    def test_legacy_manifest_output_migrates_once(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(temp)
            store.write({"run_id": "legacy", "status": "running",
                         "owner_pid": 999_999_999, "output": "visible",
                         "output_tail": ["tail"]})
            self.assertEqual(store.recover_interrupted(), 1)
            manifest = json.loads(
                (Path(temp) / "_jobs" / "legacy.json").read_text("utf-8"))
            self.assertNotIn("output", manifest)
            self.assertTrue(manifest["legacy_output_migrated"])
            visible = store.read_output(manifest)
            self.assertIn("visible", visible)
            self.assertIn("tail", visible)


if __name__ == "__main__":
    unittest.main()
