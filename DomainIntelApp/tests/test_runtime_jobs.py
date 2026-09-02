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

    def test_structured_event_updates_exact_progress_and_checkpoint(self):
        search_root = Path(__file__).resolve().parents[2] / "DomainIntelSearch"
        if str(search_root) not in sys.path:
            sys.path.insert(0, str(search_root))
        from intdog_core.repository import IntelligenceRepository

        with tempfile.TemporaryDirectory() as temp:
            repo = IntelligenceRepository(temp); repo.ensure_industry("AI")
            manager = JobManager(temp, ledger=repo)
            event = {"stage":"source_gate", "progress":35,
                     "message":"信息源门槛通过", "checkpoint":{"campaign_id":"scp-1"}}
            result = manager.run_sync(
                [sys.executable, "-c", f"print('INTDOG_EVENT '+{json.dumps(json.dumps(event))})"],
                cwd=temp, title="event", timeout=10,
                metadata={"folder":"AI", "operation":"bootstrap", "provider":"openai"})
            task = repo.get_task(result.run_id)
            self.assertEqual((task["stage"], task["progress"]), ("source_gate", 35))
            self.assertEqual(task["checkpoint"]["campaign_id"], "scp-1")
            self.assertIn("信息源门槛通过", result.output)
            self.assertNotIn("INTDOG_EVENT", result.output)

    def test_structured_event_survives_one_character_stdout_chunks(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp)
            job = manager.create([sys.executable, "-c", "pass"], cwd=temp,
                                 title="split event")
            event = {"stage":"entity_gate", "progress":95,
                     "message":"实体覆盖门槛通过",
                     "checkpoint":{"stage_states":{"entities":"passed"}}}
            wire = "INTDOG_EVENT " + json.dumps(event, ensure_ascii=False) + "\n"

            for character in wire:
                job._emit(character)

            self.assertEqual(job._manifest["stage"], "entity_gate")
            self.assertEqual(job._manifest["progress"], .95)
            self.assertEqual(job._manifest["checkpoint"]["stage_states"]["entities"],
                             "passed")
            output = manager.store.read_output(job._manifest)
            self.assertIn("实体覆盖门槛通过", output)
            self.assertNotIn("INTDOG_EVENT", output)

    def test_same_industry_jobs_are_fifo_and_queued_job_is_cancellable(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp)
            slow = [sys.executable, "-u", "-c", "import time;print('start',flush=True);time.sleep(.4)"]
            first = manager.start(slow, cwd=temp, title="first", timeout=5,
                                  metadata={"folder":"AI"})
            second = manager.start(slow, cwd=temp, title="second", timeout=5,
                                   metadata={"folder":"AI"})
            other = manager.start(slow, cwd=temp, title="other", timeout=5,
                                  metadata={"folder":"Chips"})
            time.sleep(.12)
            self.assertTrue(first.running)
            self.assertFalse(second.running)
            self.assertTrue(other.running)
            self.assertTrue(second.cancel())
            self.assertEqual(second.wait(1).status, "cancelled")
            self.assertEqual(first.wait(3).status, "completed")
            self.assertEqual(other.wait(3).status, "completed")

    def test_child_error_is_authoritative_over_generic_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp)
            result = manager.run_sync(
                [sys.executable, "-c", "print('[错误] invalid model: model_not_found');raise SystemExit(2)"],
                cwd=temp, title="failure", timeout=10)
            self.assertEqual(result.status, "failed")
            self.assertIn("invalid model", result.error)
            self.assertNotEqual(result.error, "Process exited with 2")

    def test_missing_required_artifact_is_partial_not_completed(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp)
            result = manager.run_sync(
                [sys.executable, "-c", "print('research text only')"],
                cwd=temp, title="report", timeout=10,
                metadata={"operation": "report", "requires_artifact": True},
            )
            self.assertEqual(result.status, "partial")
            self.assertIn("artifact", result.error.lower())

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

    def test_sqlite_ledger_is_authoritative_and_stream_output_stays_redacted(self):
        search_root = Path(__file__).resolve().parents[2] / "DomainIntelSearch"
        if str(search_root) not in sys.path:
            sys.path.insert(0, str(search_root))
        from intdog_core.repository import IntelligenceRepository

        with tempfile.TemporaryDirectory() as temp:
            repo = IntelligenceRepository(temp)
            repo.ensure_industry("AI")
            parent = repo.create_task(
                folder="AI", operation="parent", input={}, origin="app",
                provider="codex")
            manager = JobManager(temp, ledger=repo)
            program = (
                "import sys;"
                "s='credential-'+'ledger-canary-9347';"
                "sys.stdout.write('Authorization: Bea');sys.stdout.flush();"
                "sys.stdout.write('rer '+s+'\\n[阶段 1/2] collect\\n');"
                "sys.stdout.write('[完成] /tmp/daily.md\\n')")
            result = manager.run_sync(
                [sys.executable, "-u", "-c", program], cwd=temp,
                title="ledger", timeout=10,
                metadata={
                    "folder": "AI", "operation": "daily", "origin": "app",
                    "provider": "codex", "model": "gpt-test",
                    "parent_run_id": parent["id"],
                    "time_window": {
                        "start": "2026-09-01T04:00:00+08:00",
                        "end": "2026-09-02T08:00:00+08:00",
                        "timezone": "Asia/Shanghai"},
                })
            task = repo.get_task(result.run_id)
            self.assertEqual(task["status"], "completed")
            self.assertEqual((task["stage"], task["progress"]), ("collect", 50))
            self.assertEqual(task["parent_run_id"], parent["id"])
            self.assertEqual(task["output_path"], "/tmp/daily.md")
            canary = "credential-ledger-canary-9347"
            self.assertNotIn(canary, manager.store.read_output(manager.store.list()[0]))
            self.assertNotIn(canary, repo.db_path.read_bytes().decode("utf-8", "ignore"))

    def test_partial_exit_is_preserved_in_authoritative_ledger(self):
        search_root = Path(__file__).resolve().parents[2] / "DomainIntelSearch"
        if str(search_root) not in sys.path:
            sys.path.insert(0, str(search_root))
        from intdog_core.repository import IntelligenceRepository

        with tempfile.TemporaryDirectory() as temp:
            repo = IntelligenceRepository(temp)
            repo.ensure_industry("AI")
            manager = JobManager(temp, ledger=repo)
            result = manager.run_sync(
                [sys.executable, "-c", "raise SystemExit(4)"], cwd=temp,
                title="partial", timeout=10,
                metadata={"folder": "AI", "operation": "daily",
                          "origin": "app", "provider": "codex"})
            self.assertEqual(result.status, "partial")
            self.assertEqual(repo.get_task(result.run_id)["status"], "partial")

    def test_one_use_credential_pipe_is_not_argv_env_log_or_state(self):
        secret = "background-pipe-canary-4d62f930"
        bundle = {"provider": "openai", "model": "gpt-test", "apiKey": secret,
                  "apiBase": "https://api.openai.com/v1", "authType": "bearer"}
        program = (
            "import json,os,struct,sys;"
            "h=sys.stdin.buffer.read(4);n=struct.unpack('>I',h)[0];"
            "v=json.loads(sys.stdin.buffer.read(n));"
            "s=v['apiKey'];assert s.startswith('background-pipe-canary-');"
            "assert s not in json.dumps(sys.argv);"
            "assert s not in json.dumps(dict(os.environ));"
            "print('credential frame consumed')")
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(
                temp, credential_supplier=lambda provider, operation: (
                    dict(bundle) if (provider, operation) == ("openai", "report") else {}))
            result = manager.run_sync(
                [sys.executable, "-c", program], cwd=temp,
                title="credential pipe", timeout=10,
                metadata={"provider": "openai", "operation": "report"})
            self.assertEqual(result.status, "completed")
            persisted = b"".join(
                path.read_bytes() for path in Path(temp).rglob("*") if path.is_file())
            self.assertNotIn(secret.encode(), persisted)

    def test_public_and_mismatched_provider_jobs_receive_an_empty_credential_frame(self):
        secret = "provider-scope-canary-841f"
        calls = []

        def supplier(provider, operation):
            calls.append((provider, operation))
            if (provider, operation) == ("openai", "report"):
                return {"provider": "openai", "apiKey": secret}
            return {}

        program = (
            "import json,struct,sys;"
            "h=sys.stdin.buffer.read(4);n=struct.unpack('>I',h)[0];"
            "assert json.loads(sys.stdin.buffer.read(n))=={}")
        with tempfile.TemporaryDirectory() as temp:
            manager = JobManager(temp, credential_supplier=supplier)
            public = manager.run_sync(
                [sys.executable, "-c", program], cwd=temp, title="public", timeout=10,
                metadata={"provider": "public_sources", "operation": "daily"})
            mismatch = manager.run_sync(
                [sys.executable, "-c", program], cwd=temp, title="mismatch", timeout=10,
                metadata={"provider": "deepseek", "operation": "report"})
            self.assertEqual((public.status, mismatch.status), ("completed", "completed"))
            self.assertEqual(calls, [("public_sources", "daily"), ("deepseek", "report")])

    def test_runtime_credential_supplier_requires_provider_and_operation_scope(self):
        search_root = Path(__file__).resolve().parents[2] / "DomainIntelSearch"
        if str(search_root) not in sys.path:
            sys.path.insert(0, str(search_root))
        from src.services.runtime_credentials import (
            clear_runtime_credential, credential_bundle, install_runtime_credential)

        install_runtime_credential({"provider": "openai", "apiKey": "scope-canary"})
        try:
            self.assertEqual(credential_bundle("openai", ""), {})
            self.assertEqual(credential_bundle("public_sources", "daily"), {})
            self.assertEqual(credential_bundle("deepseek", "report"), {})
            scoped = credential_bundle("openai", "weekly")
            self.assertEqual(scoped["operation"], "weekly")
            self.assertEqual(scoped["provider"], "openai")
        finally:
            clear_runtime_credential()


if __name__ == "__main__":
    unittest.main()
