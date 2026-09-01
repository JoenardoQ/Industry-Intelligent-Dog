"""P0 coverage for the authoritative SQLite task ledger (SP3 Task 1)."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from intdog_core.repository import IntelligenceRepository, SCHEMA_VERSION


STATES = {
    "queued", "running", "cancelling", "paused", "completed", "partial",
    "failed", "cancelled", "interrupted",
}


def _repo(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("AI", "Artificial Intelligence")
    repo.ensure_industry("Chips", "Semiconductors")
    return repo


def _task(repo, **overrides):
    values = {
        "folder": "AI", "operation": "daily", "input": {"query": "AI"},
        "origin": "app", "provider": "codex", "model": "gpt-test",
    }
    values.update(overrides)
    return repo.create_task(**values)


def test_schema20_is_repeatable_and_preserves_legacy_runs(tmp_path):
    repo = _repo(tmp_path)
    legacy_id = repo.start_run("AI", "legacy-report")
    repo.migrate()
    repo.migrate()
    with repo.connection() as con:
        versions = [row[0] for row in con.execute(
            "SELECT version FROM schema_migrations ORDER BY version")]
        legacy = con.execute("SELECT kind,status FROM runs WHERE id=?",
                             (legacy_id,)).fetchone()
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert SCHEMA_VERSION == 21
    assert versions == list(range(1, 22))
    assert dict(legacy) == {"kind": "legacy-report", "status": "running"}
    assert {"task_runs", "task_state_events", "background_authorizations"} <= tables


def test_task_fields_heartbeat_checkpoints_and_idempotent_completion(tmp_path):
    repo = _repo(tmp_path)
    parent = _task(repo, operation="research")
    task = _task(
        repo, parent_run_id=parent["id"], provider="openai", model="gpt-5",
        time_window={"start": "2026-09-01T04:00:00+08:00",
                     "end": "2026-09-02T08:30:00+08:00",
                     "timezone": "Asia/Shanghai"},
        output_path="AI/periodic/daily/2026-09-02.md")
    assert set(repo.task_states()) == STATES
    assert task["status"] == "queued"
    assert task["parent_run_id"] == parent["id"]
    assert task["provider"] == "openai" and task["model"] == "gpt-5"
    assert task["time_window"]["timezone"] == "Asia/Shanghai"

    assert repo.claim_expired(task["id"], "app:one", 30) is True
    repo.heartbeat(task["id"], owner="app:one", stage="collect", progress=37,
                   checkpoint={"cursor": "page-2", "qualified": 19})
    running = repo.get_task(task["id"])
    assert (running["status"], running["stage"], running["progress"]) == (
        "running", "collect", 37)
    assert running["checkpoint"] == {"cursor": "page-2", "qualified": 19}
    completed = repo.transition(
        task["id"], expected={"running"}, target="completed", owner="app:one")
    repeated = repo.transition(
        task["id"], expected={"running"}, target="completed")
    assert completed["status"] == repeated["status"] == "completed"
    assert len([event for event in repo.list_task_events(task["id"])
                if event["to_status"] == "completed"]) == 1
    with pytest.raises(ValueError, match="transition"):
        repo.transition(task["id"], expected={"completed"}, target="running")


def test_all_nine_states_and_recovery_transitions_are_explicit(tmp_path):
    repo = _repo(tmp_path)
    assert set(repo.task_states()) == STATES
    direct = {
        "paused", "cancelled",
    }
    for target in direct:
        task = _task(repo, operation=f"queued-to-{target}")
        assert repo.transition(
            task["id"], expected={"queued"}, target=target)["status"] == target
    for target in {
            "cancelling", "paused", "completed", "partial", "failed",
            "cancelled", "interrupted"}:
        task = _task(repo, operation=f"running-to-{target}")
        assert repo.claim_expired(task["id"], f"owner:{target}", 30)
        assert repo.transition(
            task["id"], expected={"running"}, target=target,
            owner=f"owner:{target}")["status"] == target
    for source in {"paused", "partial", "failed", "interrupted"}:
        task = _task(repo, operation=f"recover-{source}")
        if source == "paused":
            repo.transition(task["id"], expected={"queued"}, target=source)
        else:
            repo.claim_expired(task["id"], f"owner:{source}", 30)
            repo.transition(task["id"], expected={"running"}, target=source,
                            owner=f"owner:{source}")
        assert repo.transition(
            task["id"], expected={source}, target="queued")["status"] == "queued"


def test_expired_lease_takeover_is_cas_guarded_and_preserves_checkpoint(tmp_path):
    repo = _repo(tmp_path)
    task = _task(repo)
    assert repo.claim_expired(task["id"], "worker:one", 60)
    repo.heartbeat(task["id"], owner="worker:one", stage="collect", progress=20,
                   checkpoint={"bucket": "2026-01"})
    assert repo.claim_expired(task["id"], "worker:two", 60) is False
    with repo.transaction() as con:
        con.execute("""UPDATE task_runs SET lease_expires_at='2000-01-01T00:00:00+00:00'
            WHERE id=?""", (task["id"],))
    assert repo.claim_expired(task["id"], "worker:two", 60) is True
    taken = repo.get_task(task["id"])
    assert taken["lease_owner"] == "worker:two"
    assert taken["checkpoint"] == {"bucket": "2026-01"}
    assert any(event["action"] == "lease_takeover"
               for event in repo.list_task_events(task["id"]))


def test_stale_worker_cannot_checkpoint_publish_output_or_finish_after_takeover(tmp_path):
    repo = _repo(tmp_path)
    task = _task(repo)
    assert repo.claim_expired(task["id"], "worker:old", 30)
    with repo.transaction() as con:
        con.execute("""UPDATE task_runs SET lease_expires_at='2000-01-01T00:00:00+00:00'
            WHERE id=?""", (task["id"],))
    assert repo.claim_expired(task["id"], "worker:new", 30)

    with pytest.raises(RuntimeError, match="lease"):
        repo.heartbeat(task["id"], owner="worker:old", stage="stale",
                       progress=99, checkpoint={"cursor": "wrong"})
    with pytest.raises(RuntimeError, match="lease"):
        repo.update_task_output(task["id"], "/tmp/stale.md", owner="worker:old")
    with pytest.raises(RuntimeError, match="lease"):
        repo.transition(task["id"], expected={"running"}, target="completed",
                        owner="worker:old")

    repo.heartbeat(task["id"], owner="worker:new", stage="verified",
                   progress=40, checkpoint={"cursor": "kept"})
    repo.update_task_output(task["id"], "/tmp/current.md", owner="worker:new")
    completed = repo.transition(
        task["id"], expected={"running"}, target="completed", owner="worker:new")
    assert completed["checkpoint"] == {"cursor": "kept"}
    assert completed["output_path"] == "/tmp/current.md"


def test_startup_recovery_interrupts_only_expired_running_or_cancelling_tasks(tmp_path):
    repo = _repo(tmp_path)
    expired = _task(repo, operation="expired")
    live = _task(repo, operation="live")
    queued = _task(repo, operation="queued")
    assert repo.claim_expired(expired["id"], "worker:expired", 30)
    assert repo.claim_expired(live["id"], "worker:live", 30)
    repo.transition(expired["id"], expected={"running"}, target="cancelling")
    with repo.transaction() as con:
        con.execute("""UPDATE task_runs SET lease_expires_at='2000-01-01T00:00:00+00:00'
            WHERE id=?""", (expired["id"],))

    recovered = repo.recover_expired_tasks(actor="startup:test")
    assert recovered == [expired["id"]]
    assert repo.get_task(expired["id"])["status"] == "interrupted"
    assert repo.get_task(live["id"])["status"] == "running"
    assert repo.get_task(queued["id"])["status"] == "queued"


def test_stalled_cancel_can_recover_only_the_requested_expired_task(tmp_path):
    repo = _repo(tmp_path)
    first = _task(repo, operation="first")
    second = _task(repo, operation="second")
    for task, owner in ((first, "worker:first"), (second, "worker:second")):
        assert repo.claim_expired(task["id"], owner, 30)
    with repo.transaction() as con:
        con.execute("""UPDATE task_runs SET lease_expires_at='2000-01-01T00:00:00+00:00'
            WHERE id IN (?,?)""", (first["id"], second["id"]))

    assert repo.recover_expired_tasks(
        actor="local-user", run_id=first["id"]) == [first["id"]]
    assert repo.get_task(first["id"])["status"] == "interrupted"
    assert repo.get_task(second["id"])["status"] == "running"


def test_schema_migration_takes_immediate_lock_before_version_checks(tmp_path):
    traces: list[str] = []

    class TracedRepository(IntelligenceRepository):
        def connect(self):
            con = super().connect()
            con.set_trace_callback(traces.append)
            return con

    TracedRepository(tmp_path)
    normalized = [" ".join(statement.upper().split()) for statement in traces]
    lock_index = next(index for index, statement in enumerate(normalized)
                      if statement == "BEGIN IMMEDIATE")
    version_index = next(index for index, statement in enumerate(normalized)
                         if "SELECT 1 FROM SCHEMA_MIGRATIONS" in statement)
    assert lock_index < version_index


def test_concurrent_first_start_migration_is_idempotent(tmp_path):
    failures: list[BaseException] = []
    barrier = threading.Barrier(6)

    def migrate():
        try:
            barrier.wait()
            IntelligenceRepository(tmp_path)
        except BaseException as exc:  # pragma: no branch - failure is the oracle
            failures.append(exc)

    workers = [threading.Thread(target=migrate) for _ in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert failures == []
    repo = IntelligenceRepository(tmp_path)
    with repo.connection() as con:
        assert con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 21


def test_background_authorization_is_scoped_and_revocation_is_atomic(tmp_path):
    repo = _repo(tmp_path)
    denied = _task(repo, origin="background_worker", provider="openai")
    assert denied["status"] == "paused"
    assert denied["error"]["category"] == "background_authorization_required"
    assert repo.claim_expired(denied["id"], "worker:denied", 30) is False

    repo.grant_background_authorization(
        "AI", provider="openai", operation="daily", actor="local-user")
    queued = _task(repo, origin="background_worker", provider="openai",
                   credential_handle_ref="credref:queued")
    running = _task(repo, origin="background_worker", provider="openai",
                    credential_handle_ref="credref:running")
    dispatched = _task(repo, origin="background_worker", provider="openai",
                       credential_handle_ref="credref:sent")
    wrong_industry = _task(repo, folder="Chips", origin="background_worker",
                           provider="openai")
    wrong_operation = _task(repo, operation="weekly", origin="background_worker",
                            provider="openai")
    assert wrong_industry["status"] == wrong_operation["status"] == "paused"
    assert repo.claim_expired(running["id"], "worker:one", 30)
    assert repo.claim_expired(dispatched["id"], "worker:two", 30)
    repo.mark_request_dispatched(dispatched["id"], owner="worker:two")

    result = repo.revoke_background_authorization(
        "AI", provider="openai", operation="daily", actor="local-user",
        reason="user disabled background access")
    assert set(result["affected_run_ids"]) == {queued["id"], running["id"]}
    assert repo.get_task(queued["id"])["status"] == "cancelled"
    assert repo.get_task(running["id"])["status"] == "cancelling"
    assert repo.get_task(dispatched["id"])["status"] == "running"
    assert all(repo.get_task(item["id"])["credential_handle_ref"] is None
               for item in (queued, running, dispatched))
    after = _task(repo, origin="background_worker", provider="openai")
    assert after["status"] == "paused"


def test_secret_shaped_input_is_redacted_and_transition_failure_rolls_back(tmp_path):
    repo = _repo(tmp_path)
    canary = "credential-ledger-canary-9347"
    task = _task(repo, input={"api_key": canary,
                              "nested": {"authorization": f"Bearer {canary}"}})
    assert task["input"] == {"api_key": "***",
                             "nested": {"authorization": "***"}}
    assert canary not in repo.db_path.read_bytes().decode("utf-8", errors="ignore")
    repo.claim_expired(task["id"], "app:one", 30)
    with repo.transaction() as con:
        con.execute("""CREATE TRIGGER abort_failed_task_event
            BEFORE INSERT ON task_state_events
            WHEN NEW.to_status='failed'
            BEGIN SELECT RAISE(ABORT, 'injected transition failure'); END""")
    before = repo.get_task(task["id"])
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        repo.transition(task["id"], expected={"running"}, target="failed",
                        error={"category": "injected"}, owner="app:one")
    after = repo.get_task(task["id"])
    assert after["status"] == before["status"] == "running"
    assert after["error"] == before["error"]
