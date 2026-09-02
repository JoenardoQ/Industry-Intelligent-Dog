"""Transactional SQLite repository for the IntDog knowledge core."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import (canonical_url, json_text, json_value, normalized_name,
                     stable_id, utc_now)
from .source_trust import publisher_profile
from .chain_repository import ChainRepositoryMixin
from .analysis_repository import AnalysisRepositoryMixin
from .workbench_repository import WorkbenchRepositoryMixin
from .evidence_repository import EvidenceRepositoryMixin
from .source_repository import SourceRepositoryMixin
from .observability_repository import ObservabilityRepositoryMixin
from .task_repository import TaskRepositoryMixin
from .settings_repository import SettingsRepositoryMixin
from .conversation_repository import ConversationRepositoryMixin


SCHEMA_VERSION = 23


def _execute_script(con: sqlite3.Connection, script: str) -> None:
    """Execute a SQLite script without ``executescript``'s implicit COMMIT."""
    statement = ""
    for line in str(script).splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                con.execute(statement)
            statement = ""
    if statement.strip():
        raise sqlite3.OperationalError("incomplete migration statement")


class IntelligenceRepository(
        ConversationRepositoryMixin, SettingsRepositoryMixin, TaskRepositoryMixin, ObservabilityRepositoryMixin, SourceRepositoryMixin, EvidenceRepositoryMixin, WorkbenchRepositoryMixin,
        AnalysisRepositoryMixin, ChainRepositoryMixin):
    """One repository per DomainIntelData root.

    Connections are deliberately short lived.  WAL plus a busy timeout keeps
    the desktop app and collector safe without a resident database server.
    """

    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_root / "intdog.sqlite3"
        for attempt in range(8):
            try:
                self.migrate()
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == 7:
                    raise
                time.sleep(min(0.05 * (2 ** attempt), 0.5))

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        return con

    @contextmanager
    def connection(self):
        """Commit/rollback and always close a short-lived connection."""
        con = self.connect()
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def transaction(self):
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def migrate(self) -> None:
        with self.connection() as con:
            con.execute("PRAGMA journal_mode=WAL")
        # App and the independently scheduled Worker may start together.  The
        # immediate lock is acquired before the first version read, so only one
        # runtime can decide which migration is pending.
        with self.transaction() as con:
            _execute_script(con, """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS industries (
                    id TEXT PRIMARY KEY, folder TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, canonical_url TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, publisher_country TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS industry_sources (
                    industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    category TEXT NOT NULL, monitoring_status TEXT NOT NULL DEFAULT 'active',
                    added_manually INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}', deleted_at TEXT,
                    PRIMARY KEY(industry_id, source_id, category));
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, canonical_url TEXT NOT NULL UNIQUE,
                    content_hash TEXT, title TEXT NOT NULL, abstract TEXT,
                    source_id TEXT REFERENCES sources(id), published_at TEXT,
                    retrieved_at TEXT NOT NULL, language TEXT, origin TEXT,
                    raw_json TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS industry_documents (
                    industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    category TEXT NOT NULL, observed_date TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'unreviewed',
                    credibility TEXT NOT NULL DEFAULT 'collected', ranking_score REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}', deleted_at TEXT,
                    PRIMARY KEY(industry_id, document_id, category, observed_date));
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, canonical_name TEXT NOT NULL,
                    name_en TEXT, country TEXT, external_ids_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, UNIQUE(kind, canonical_name, country));
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    alias TEXT NOT NULL, language TEXT, valid_from TEXT, valid_to TEXT,
                    PRIMARY KEY(entity_id, alias));
                CREATE TABLE IF NOT EXISTS industry_entities (
                    industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                    role TEXT, chain_name TEXT, status TEXT NOT NULL DEFAULT 'candidate',
                    confidence REAL, metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(industry_id, entity_id, role, chain_name));
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY, src_entity_id TEXT NOT NULL REFERENCES entities(id),
                    predicate TEXT NOT NULL, dst_entity_id TEXT NOT NULL REFERENCES entities(id),
                    industry_id TEXT REFERENCES industries(id), valid_from TEXT, valid_to TEXT,
                    confidence REAL, metadata_json TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY, industry_id TEXT NOT NULL REFERENCES industries(id),
                    subject_id TEXT REFERENCES entities(id), predicate TEXT NOT NULL,
                    object_json TEXT NOT NULL, qualifiers_json TEXT NOT NULL DEFAULT '{}',
                    valid_from TEXT, valid_to TEXT, status TEXT NOT NULL DEFAULT 'candidate',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY, claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                    document_id TEXT REFERENCES documents(id), relation TEXT NOT NULL,
                    excerpt TEXT, publisher_cluster TEXT, extraction_method TEXT,
                    confidence REAL, created_at TEXT NOT NULL,
                    UNIQUE(claim_id, document_id, relation));
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, industry_id TEXT REFERENCES industries(id),
                    kind TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL DEFAULT '{}', metrics_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT, error_message TEXT, started_at TEXT NOT NULL,
                    finished_at TEXT, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, object_type TEXT NOT NULL,
                    object_id TEXT, details_json TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS legacy_imports (
                    path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, imported_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_documents_published ON documents(published_at);
                CREATE INDEX IF NOT EXISTS idx_industry_documents_date
                    ON industry_documents(industry_id, observed_date, category, deleted_at);
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
                CREATE INDEX IF NOT EXISTS idx_industry_entities
                    ON industry_entities(industry_id, chain_name, role);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, updated_at);
            """)
            con.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?,?)",
                        (1, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
                _execute_script(con, """
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                        title, abstract, content='documents', content_rowid='rowid');
                    CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                        INSERT INTO documents_fts(rowid,title,abstract)
                        VALUES(new.rowid,new.title,new.abstract);
                    END;
                    CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                        INSERT INTO documents_fts(documents_fts,rowid,title,abstract)
                        VALUES('delete',old.rowid,old.title,old.abstract);
                    END;
                    CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                        INSERT INTO documents_fts(documents_fts,rowid,title,abstract)
                        VALUES('delete',old.rowid,old.title,old.abstract);
                        INSERT INTO documents_fts(rowid,title,abstract)
                        VALUES(new.rowid,new.title,new.abstract);
                    END;
                    INSERT INTO documents_fts(documents_fts) VALUES('rebuild');
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (2, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=3").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        title TEXT NOT NULL, event_type TEXT NOT NULL,
                        description TEXT, occurred_at TEXT, observed_at TEXT NOT NULL,
                        importance INTEGER NOT NULL DEFAULT 3,
                        status TEXT NOT NULL DEFAULT 'candidate',
                        metadata_json TEXT NOT NULL DEFAULT '{}');
                    CREATE TABLE IF NOT EXISTS event_documents (
                        event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        relation TEXT NOT NULL DEFAULT 'reports',
                        PRIMARY KEY(event_id,document_id,relation));
                    CREATE INDEX IF NOT EXISTS idx_events_time
                        ON events(industry_id,occurred_at,event_type);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (3, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=4").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS locks (
                        lock_key TEXT PRIMARY KEY, owner TEXT NOT NULL,
                        acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (4, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=5").fetchone():
                con.execute("ALTER TABLE claims ADD COLUMN superseded_at TEXT")
                con.execute("""CREATE INDEX IF NOT EXISTS idx_claims_current
                    ON claims(industry_id,predicate,superseded_at)""")
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (5, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=6").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS compatibility_views (
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        view_key TEXT NOT NULL, dirty INTEGER NOT NULL DEFAULT 1,
                        last_error TEXT, updated_at TEXT NOT NULL,
                        PRIMARY KEY(industry_id, view_key));
                    CREATE INDEX IF NOT EXISTS idx_compatibility_views_dirty
                        ON compatibility_views(dirty, updated_at);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (6, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=7").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS publishers (
                        id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL,
                        country TEXT, owner_cluster TEXT NOT NULL,
                        verification_status TEXT NOT NULL DEFAULT 'unverified',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS publisher_domains (
                        domain TEXT PRIMARY KEY,
                        publisher_id TEXT NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
                        verified INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'observed');
                    CREATE TABLE IF NOT EXISTS source_publishers (
                        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                        publisher_id TEXT NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
                        relation TEXT NOT NULL DEFAULT 'publishes', confidence REAL,
                        PRIMARY KEY(source_id,publisher_id,relation));
                    CREATE TABLE IF NOT EXISTS value_chain_nodes (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        parent_id TEXT REFERENCES value_chain_nodes(id),
                        name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
                        description TEXT, status TEXT NOT NULL DEFAULT 'candidate',
                        coverage_status TEXT NOT NULL DEFAULT 'empty', evidence_count INTEGER NOT NULL DEFAULT 0,
                        metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL, UNIQUE(industry_id,name));
                    CREATE TABLE IF NOT EXISTS entity_identifiers (
                        entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                        scheme TEXT NOT NULL, value TEXT NOT NULL,
                        PRIMARY KEY(scheme,value));
                    CREATE TABLE IF NOT EXISTS entity_names (
                        entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL, country TEXT NOT NULL DEFAULT '',
                        normalized_name TEXT NOT NULL, name_type TEXT NOT NULL DEFAULT 'alias',
                        UNIQUE(kind,country,normalized_name));
                    CREATE TABLE IF NOT EXISTS entity_chain_roles (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                        chain_node_id TEXT NOT NULL REFERENCES value_chain_nodes(id) ON DELETE CASCADE,
                        role TEXT NOT NULL, valid_from TEXT, valid_to TEXT,
                        status TEXT NOT NULL DEFAULT 'candidate', confidence REAL,
                        evidence_count INTEGER NOT NULL DEFAULT 0,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        UNIQUE(industry_id,entity_id,chain_node_id,role,valid_from));
                    CREATE INDEX IF NOT EXISTS idx_chain_nodes_industry
                        ON value_chain_nodes(industry_id,position);
                    CREATE INDEX IF NOT EXISTS idx_entity_chain_roles
                        ON entity_chain_roles(industry_id,chain_node_id,valid_to);
                    CREATE INDEX IF NOT EXISTS idx_publishers_cluster
                        ON publishers(owner_cluster,verification_status);
                """)
                for row in con.execute(
                        "SELECT id,kind,canonical_name,name_en,country,external_ids_json FROM entities"):
                    country = row["country"] or ""
                    for name, name_type in ((row["canonical_name"], "canonical"),
                                            (row["name_en"], "english")):
                        normalized = normalized_name(name)
                        if normalized:
                            con.execute("""INSERT OR IGNORE INTO entity_names
                                (entity_id,kind,country,normalized_name,name_type)
                                VALUES(?,?,?,?,?)""",
                                (row["id"], row["kind"], country, normalized, name_type))
                    for scheme, value in json_value(row["external_ids_json"], {}).items():
                        if str(value).strip():
                            con.execute("""INSERT OR IGNORE INTO entity_identifiers
                                (entity_id,scheme,value) VALUES(?,?,?)""",
                                (row["id"], str(scheme).casefold(), str(value).strip()))
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (7, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=8").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS analysis_artifacts (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL, input_hash TEXT NOT NULL,
                        algorithm_version TEXT NOT NULL, status TEXT NOT NULL,
                        content_json TEXT NOT NULL, metrics_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_latest
                        ON analysis_artifacts(industry_id,kind,created_at DESC);
                    CREATE TABLE IF NOT EXISTS research_agenda_items (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        dimension TEXT NOT NULL, target_key TEXT NOT NULL,
                        title TEXT NOT NULL, priority INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'open', rationale TEXT NOT NULL,
                        query_json TEXT NOT NULL DEFAULT '[]',
                        acceptance_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(industry_id,dimension,target_key));
                    CREATE INDEX IF NOT EXISTS idx_research_agenda_open
                        ON research_agenda_items(industry_id,status,priority DESC);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (8, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=9").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS value_chain_edges (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        src_node_id TEXT NOT NULL REFERENCES value_chain_nodes(id) ON DELETE CASCADE,
                        dst_node_id TEXT NOT NULL REFERENCES value_chain_nodes(id) ON DELETE CASCADE,
                        relation TEXT NOT NULL, valid_from TEXT, valid_to TEXT,
                        confidence REAL, evidence_count INTEGER NOT NULL DEFAULT 0,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(industry_id,src_node_id,dst_node_id,relation,valid_from));
                    CREATE INDEX IF NOT EXISTS idx_chain_edges_active
                        ON value_chain_edges(industry_id,src_node_id,dst_node_id,valid_to);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (9, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=10").fetchone():
                edge_columns = {row["name"] for row in
                                con.execute("PRAGMA table_info(value_chain_edges)")}
                if "status" not in edge_columns:
                    con.execute("""ALTER TABLE value_chain_edges ADD COLUMN status
                        TEXT NOT NULL DEFAULT 'candidate'""")
                if "effect" not in edge_columns:
                    con.execute("""ALTER TABLE value_chain_edges ADD COLUMN effect
                        TEXT NOT NULL DEFAULT 'uncertain'""")
                if "lag_days" not in edge_columns:
                    con.execute("ALTER TABLE value_chain_edges ADD COLUMN lag_days INTEGER")
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS chain_edge_evidence (
                        id TEXT PRIMARY KEY,
                        edge_id TEXT NOT NULL REFERENCES value_chain_edges(id) ON DELETE CASCADE,
                        document_id TEXT REFERENCES documents(id),
                        claim_id TEXT REFERENCES claims(id), relation TEXT NOT NULL,
                        url TEXT, excerpt TEXT, publisher_cluster TEXT,
                        confidence REAL, created_at TEXT NOT NULL,
                        UNIQUE(edge_id,document_id,claim_id,url,relation));
                    CREATE INDEX IF NOT EXISTS idx_chain_edge_evidence
                        ON chain_edge_evidence(edge_id,relation);
                    CREATE TABLE IF NOT EXISTS research_agenda_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agenda_id TEXT NOT NULL REFERENCES research_agenda_items(id) ON DELETE CASCADE,
                        from_status TEXT, to_status TEXT NOT NULL, actor TEXT NOT NULL,
                        note TEXT, occurred_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS research_tasks (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        agenda_id TEXT NOT NULL REFERENCES research_agenda_items(id) ON DELETE CASCADE,
                        status TEXT NOT NULL DEFAULT 'ready', budget INTEGER NOT NULL,
                        task_json TEXT NOT NULL, result_artifact_id TEXT,
                        run_id TEXT, acceptance_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_research_tasks_agenda
                        ON research_tasks(industry_id,agenda_id,status,created_at DESC);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (10, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=11").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS stories (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        canonical_title TEXT NOT NULL, story_family TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'candidate',
                        clustering_version TEXT NOT NULL,
                        first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS story_documents (
                        story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        relation TEXT NOT NULL DEFAULT 'reports',
                        publisher_cluster TEXT, added_at TEXT NOT NULL,
                        PRIMARY KEY(story_id,document_id));
                    CREATE TABLE IF NOT EXISTS story_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
                        action TEXT NOT NULL, actor TEXT NOT NULL,
                        details_json TEXT NOT NULL DEFAULT '{}', occurred_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS source_health (
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                        adapter TEXT NOT NULL, status TEXT NOT NULL,
                        last_checked_at TEXT NOT NULL, last_success_at TEXT,
                        last_good_at TEXT, retry_after TEXT,
                        consecutive_failures INTEGER NOT NULL DEFAULT 0,
                        error_code TEXT, error_message TEXT,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        PRIMARY KEY(industry_id,source_id));
                    CREATE INDEX IF NOT EXISTS idx_stories_industry_time
                        ON stories(industry_id,last_seen_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_story_documents_document
                        ON story_documents(document_id,story_id);
                    CREATE INDEX IF NOT EXISTS idx_source_health_status
                        ON source_health(industry_id,status,last_checked_at);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (11, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=12").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS automation_schedules (
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        action TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
                        local_time TEXT NOT NULL DEFAULT '08:00', weekday INTEGER NOT NULL DEFAULT 0,
                        monthday INTEGER NOT NULL DEFAULT 1,
                        timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
                        catch_up INTEGER NOT NULL DEFAULT 1,
                        last_period_key TEXT, next_run_at TEXT, last_attempt_at TEXT,
                        last_success_at TEXT, last_error TEXT, lease_owner TEXT,
                        lease_expires_at TEXT, updated_at TEXT NOT NULL,
                        PRIMARY KEY(industry_id,action));
                    CREATE INDEX IF NOT EXISTS idx_automation_due
                        ON automation_schedules(enabled,next_run_at);
                    CREATE TABLE IF NOT EXISTS coverage_cells (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        dimensions_json TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 50,
                        status TEXT NOT NULL DEFAULT 'gap', rationale TEXT NOT NULL DEFAULT '',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        source_yield INTEGER NOT NULL DEFAULT 0,
                        entity_yield INTEGER NOT NULL DEFAULT 0,
                        last_attempt_at TEXT, updated_at TEXT NOT NULL, created_at TEXT NOT NULL,
                        UNIQUE(industry_id,dimensions_json));
                    CREATE TABLE IF NOT EXISTS coverage_attempts (
                        id TEXT PRIMARY KEY,
                        cell_id TEXT NOT NULL REFERENCES coverage_cells(id) ON DELETE CASCADE,
                        query TEXT NOT NULL, rationale TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'planned',
                        source_yield INTEGER NOT NULL DEFAULT 0,
                        entity_yield INTEGER NOT NULL DEFAULT 0,
                        evidence_json TEXT NOT NULL DEFAULT '[]',
                        stopping_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(cell_id,query));
                    CREATE INDEX IF NOT EXISTS idx_coverage_frontier
                        ON coverage_cells(industry_id,status,priority DESC);
                    CREATE INDEX IF NOT EXISTS idx_coverage_attempts
                        ON coverage_attempts(cell_id,created_at DESC);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (12, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=13").fetchone():
                for statement in (
                    "ALTER TABLE automation_schedules ADD COLUMN pipeline_mode TEXT NOT NULL DEFAULT 'generate'",
                    "ALTER TABLE automation_schedules ADD COLUMN provider TEXT NOT NULL DEFAULT 'codex'",
                    "ALTER TABLE automation_schedules ADD COLUMN attempted_period_key TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE automation_schedules ADD COLUMN retry_after TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN last_job_run_id TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN last_artifact_path TEXT",
                ):
                    try:
                        con.execute(statement)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).casefold():
                            raise
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS story_editorial_constraints (
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
                        decision TEXT NOT NULL DEFAULT 'locked', actor TEXT NOT NULL,
                        rationale TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(industry_id,document_id));
                    CREATE INDEX IF NOT EXISTS idx_story_constraints_story
                        ON story_editorial_constraints(industry_id,story_id);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (13, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=14").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS agent_results (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        task_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                        original_file TEXT NOT NULL, content_hash TEXT NOT NULL,
                        summary TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
                        record_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        UNIQUE(industry_id,content_hash));
                    CREATE TABLE IF NOT EXISTS agent_assertions (
                        id TEXT PRIMARY KEY,
                        result_id TEXT NOT NULL REFERENCES agent_results(id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL, assertion_text TEXT NOT NULL,
                        assertion_type TEXT NOT NULL DEFAULT 'unspecified',
                        status TEXT NOT NULL DEFAULT 'draft_review_required',
                        claim_id TEXT REFERENCES claims(id),
                        verification_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(result_id,ordinal));
                    CREATE TABLE IF NOT EXISTS agent_citations (
                        id TEXT PRIMARY KEY,
                        assertion_id TEXT NOT NULL REFERENCES agent_assertions(id) ON DELETE CASCADE,
                        url TEXT NOT NULL, canonical_url TEXT NOT NULL,
                        reachability TEXT NOT NULL DEFAULT 'unchecked',
                        source_id TEXT REFERENCES sources(id),
                        document_id TEXT REFERENCES documents(id), verified_at TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(assertion_id,canonical_url));
                    CREATE TABLE IF NOT EXISTS agent_result_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        result_id TEXT NOT NULL REFERENCES agent_results(id) ON DELETE CASCADE,
                        assertion_id TEXT NOT NULL REFERENCES agent_assertions(id) ON DELETE CASCADE,
                        from_status TEXT NOT NULL, action TEXT NOT NULL,
                        actor TEXT NOT NULL, explanation TEXT NOT NULL DEFAULT '',
                        occurred_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_agent_results_industry
                        ON agent_results(industry_id,created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_agent_assertions_result
                        ON agent_assertions(result_id,ordinal);
                    CREATE INDEX IF NOT EXISTS idx_agent_reviews_result
                        ON agent_result_reviews(result_id,occurred_at);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (14, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=15").fetchone():
                for statement in (
                    "ALTER TABLE agent_citations ADD COLUMN snapshot_id TEXT REFERENCES document_snapshots(id)",
                    "ALTER TABLE evidence ADD COLUMN snapshot_id TEXT REFERENCES document_snapshots(id)",
                ):
                    try:
                        con.execute(statement)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).casefold():
                            raise
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS document_snapshots (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        source_id TEXT REFERENCES sources(id),
                        content_hash TEXT NOT NULL, content_text TEXT NOT NULL,
                        title TEXT NOT NULL DEFAULT '', published_at TEXT,
                        locator_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'observed',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(document_id,content_hash));
                    CREATE TABLE IF NOT EXISTS claim_evidence_snapshots (
                        claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                        snapshot_id TEXT NOT NULL REFERENCES document_snapshots(id) ON DELETE CASCADE,
                        relation TEXT NOT NULL, excerpt TEXT NOT NULL DEFAULT '',
                        publisher_cluster TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                        PRIMARY KEY(claim_id,snapshot_id,relation));
                    CREATE INDEX IF NOT EXISTS idx_document_snapshots_document
                        ON document_snapshots(document_id,created_at DESC);
                """)
                legacy_rows = con.execute("""SELECT d.id AS document_id,d.source_id,
                    d.content_hash AS original_content_hash,
                    d.title,d.abstract,d.published_at,d.retrieved_at,
                    e.id AS evidence_id,e.claim_id,e.relation,e.excerpt,
                    e.publisher_cluster,c.status AS claim_status
                    FROM documents d LEFT JOIN evidence e ON e.document_id=d.id
                    LEFT JOIN claims c ON c.id=e.claim_id
                    WHERE e.id IS NOT NULL OR EXISTS(
                        SELECT 1 FROM agent_citations ac WHERE ac.document_id=d.id)
                    ORDER BY d.id,e.id""").fetchall()
                for legacy in legacy_rows:
                    content = str(legacy["excerpt"] or legacy["abstract"] or
                                  legacy["title"] or legacy["document_id"])
                    content_hash = hashlib.sha256(
                        content.encode("utf-8")).hexdigest()
                    snapshot_id = stable_id(
                        "dsp", legacy["document_id"], content_hash)
                    status = "legacy_unresolved"
                    applied_at = legacy["retrieved_at"] or utc_now()
                    con.execute("""INSERT INTO document_snapshots
                        (id,document_id,source_id,content_hash,content_text,title,
                         published_at,locator_json,status,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(document_id,content_hash) DO UPDATE SET
                        status=document_snapshots.status""",
                        (snapshot_id, legacy["document_id"], legacy["source_id"],
                         content_hash, content, legacy["title"] or "",
                         legacy["published_at"], json_text({
                             "type": "legacy_unresolved",
                             "reason": "pre-v15 raw content and locator are unavailable",
                             "original_content_hash": legacy["original_content_hash"]}),
                         status, applied_at, applied_at))
                    if legacy["evidence_id"]:
                        con.execute("UPDATE evidence SET snapshot_id=? WHERE id=?",
                                    (snapshot_id, legacy["evidence_id"]))
                        con.execute("""INSERT INTO claim_evidence_snapshots
                            (claim_id,snapshot_id,relation,excerpt,publisher_cluster,created_at)
                            VALUES(?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
                            (legacy["claim_id"], snapshot_id, legacy["relation"],
                             legacy["excerpt"] or "",
                             legacy["publisher_cluster"] or "", applied_at))
                    con.execute("""INSERT INTO audit_log
                        (occurred_at,actor,action,object_type,object_id,details_json)
                        VALUES(?, 'schema-migration',
                        'schema15_backfill_needs_reverification','evidence',?,?)""",
                        (applied_at, legacy["evidence_id"] or legacy["document_id"],
                         json_text({"document_id": legacy["document_id"],
                            "snapshot_id": snapshot_id,
                            "reason": "legacy raw content/locator unavailable"})))
                citation_rows = con.execute("""SELECT ac.id,ac.document_id,
                    aa.claim_id,aa.status AS assertion_status
                    FROM agent_citations ac
                    JOIN agent_assertions aa ON aa.id=ac.assertion_id
                    WHERE ac.snapshot_id IS NULL AND ac.document_id IS NOT NULL
                    ORDER BY ac.id""").fetchall()
                for citation in citation_rows:
                    candidates = []
                    if (citation["claim_id"] and
                            citation["assertion_status"] == "accepted"):
                        candidates = [row[0] for row in con.execute("""SELECT DISTINCT
                            e.snapshot_id FROM evidence e
                            JOIN claims c ON c.id=e.claim_id
                            WHERE e.claim_id=? AND e.document_id=?
                            AND e.snapshot_id IS NOT NULL
                            AND c.status IN ('accepted','verified','corroborated')
                            ORDER BY e.snapshot_id""",
                            (citation["claim_id"], citation["document_id"]))]
                    if len(candidates) == 1:
                        con.execute("UPDATE agent_citations SET snapshot_id=? WHERE id=?",
                                    (candidates[0], citation["id"]))
                        continue
                    reason = ("citation has no accepted assertion/claim relationship"
                              if not citation["claim_id"] or
                              citation["assertion_status"] != "accepted"
                              else "claim/document evidence snapshot mapping is ambiguous")
                    con.execute("""INSERT INTO audit_log
                        (occurred_at,actor,action,object_type,object_id,details_json)
                        VALUES(?, 'schema-migration',
                        'schema15_backfill_needs_reverification',
                        'agent_citation',?,?)""",
                        (utc_now(), citation["id"], json_text({
                            "document_id": citation["document_id"],
                            "claim_id": citation["claim_id"],
                            "candidate_snapshot_ids": candidates,
                            "reason": reason})))
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (15, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=16").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS source_campaigns (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        targets_json TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'planned'
                            CHECK(status IN ('planned','running','paused','converged','failed')),
                        rounds INTEGER NOT NULL DEFAULT 0 CHECK(rounds >= 0),
                        budget INTEGER NOT NULL CHECK(budget > 0),
                        stopping_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS source_queries (
                        id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL REFERENCES source_campaigns(id) ON DELETE CASCADE,
                        round_no INTEGER NOT NULL CHECK(round_no > 0),
                        language TEXT NOT NULL, family TEXT NOT NULL,
                        dimensions_json TEXT NOT NULL, query TEXT NOT NULL,
                        outcome_json TEXT NOT NULL, created_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS source_candidates (
                        id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL REFERENCES source_campaigns(id) ON DELETE CASCADE,
                        canonical_url TEXT NOT NULL,
                        source_id TEXT REFERENCES sources(id),
                        publisher_id TEXT NOT NULL REFERENCES publishers(id),
                        name TEXT NOT NULL, category TEXT NOT NULL,
                        ownership_json TEXT NOT NULL DEFAULT '{}',
                        attributes_json TEXT NOT NULL DEFAULT '{}',
                        score REAL NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'candidate'
                            CHECK(status IN ('candidate','manual_review','active','reserve','rejected')),
                        selection_reason TEXT NOT NULL DEFAULT '',
                        status_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(campaign_id,canonical_url));
                    CREATE TABLE IF NOT EXISTS source_candidate_queries (
                        candidate_id TEXT NOT NULL REFERENCES source_candidates(id) ON DELETE CASCADE,
                        query_id TEXT NOT NULL REFERENCES source_queries(id) ON DELETE CASCADE,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(candidate_id,query_id));
                    CREATE TABLE IF NOT EXISTS source_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        candidate_id TEXT NOT NULL REFERENCES source_candidates(id) ON DELETE CASCADE,
                        from_status TEXT NOT NULL, to_status TEXT NOT NULL,
                        decision TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL, occurred_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_source_campaigns_industry
                        ON source_campaigns(industry_id,status,updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_source_queries_campaign
                        ON source_queries(campaign_id,round_no,created_at);
                    CREATE INDEX IF NOT EXISTS idx_source_candidates_campaign
                        ON source_candidates(campaign_id,status,score DESC);
                    CREATE INDEX IF NOT EXISTS idx_source_candidates_publisher
                        ON source_candidates(publisher_id,status);
                    CREATE INDEX IF NOT EXISTS idx_source_reviews_candidate
                        ON source_reviews(candidate_id,occurred_at,id);
                    CREATE TRIGGER IF NOT EXISTS source_reviews_no_update
                    BEFORE UPDATE ON source_reviews BEGIN
                        SELECT RAISE(ABORT, 'source_reviews is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS source_reviews_no_delete
                    BEFORE DELETE ON source_reviews BEGIN
                        SELECT RAISE(ABORT, 'source_reviews is append-only');
                    END;
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (16, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=17").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS story_observations (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
                        intelligence_date TEXT NOT NULL, observed_at TEXT NOT NULL,
                        rank INTEGER NOT NULL CHECK(rank > 0), score REAL NOT NULL,
                        independent_publishers INTEGER NOT NULL CHECK(independent_publishers >= 0),
                        publisher_clusters_json TEXT NOT NULL,
                        evidence_strength REAL NOT NULL CHECK(evidence_strength >= 0),
                        classification TEXT NOT NULL, algorithm_version TEXT NOT NULL,
                        raw_json TEXT NOT NULL, created_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS quality_observations (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        observed_date TEXT NOT NULL, observed_at TEXT NOT NULL,
                        metric TEXT NOT NULL, numerator REAL NOT NULL,
                        denominator REAL NOT NULL CHECK(denominator >= 0),
                        algorithm_version TEXT NOT NULL,
                        dimensions_json TEXT NOT NULL, raw_json TEXT NOT NULL,
                        created_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_story_observations_timeline
                        ON story_observations(industry_id,story_id,intelligence_date,
                                              algorithm_version,observed_at);
                    CREATE INDEX IF NOT EXISTS idx_quality_observations_window
                        ON quality_observations(industry_id,metric,algorithm_version,
                                                observed_date);
                    CREATE TRIGGER IF NOT EXISTS story_observations_no_update
                    BEFORE UPDATE ON story_observations BEGIN
                        SELECT RAISE(ABORT, 'story_observations is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS story_observations_no_delete
                    BEFORE DELETE ON story_observations
                    WHEN EXISTS(SELECT 1 FROM industries WHERE id=OLD.industry_id) BEGIN
                        SELECT RAISE(ABORT, 'story_observations is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS quality_observations_no_update
                    BEFORE UPDATE ON quality_observations BEGIN
                        SELECT RAISE(ABORT, 'quality_observations is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS quality_observations_no_delete
                    BEFORE DELETE ON quality_observations
                    WHEN EXISTS(SELECT 1 FROM industries WHERE id=OLD.industry_id) BEGIN
                        SELECT RAISE(ABORT, 'quality_observations is append-only');
                    END;
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (17, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=18").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS source_campaign_rounds (
                        id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL REFERENCES source_campaigns(id) ON DELETE CASCADE,
                        round_no INTEGER NOT NULL CHECK(round_no > 0),
                        status TEXT NOT NULL CHECK(status IN
                            ('running','paused','completed','failed')),
                        lease_token TEXT NOT NULL, plan_json TEXT NOT NULL DEFAULT '[]',
                        frontier_json TEXT NOT NULL DEFAULT '[]',
                        outcome_json TEXT NOT NULL DEFAULT '{}',
                        log_json TEXT NOT NULL DEFAULT '[]',
                        started_at TEXT NOT NULL, finished_at TEXT, updated_at TEXT NOT NULL,
                        UNIQUE(campaign_id,round_no));
                    CREATE INDEX IF NOT EXISTS idx_source_campaign_rounds
                        ON source_campaign_rounds(campaign_id,round_no DESC);
                    CREATE TABLE IF NOT EXISTS coverage_rounds (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        round_no INTEGER NOT NULL CHECK(round_no > 0),
                        status TEXT NOT NULL CHECK(status IN
                            ('planned','running','paused','completed','converged','failed')),
                        lease_token TEXT NOT NULL DEFAULT '',
                        frontier_json TEXT NOT NULL DEFAULT '[]',
                        outcome_json TEXT NOT NULL DEFAULT '{}',
                        log_json TEXT NOT NULL DEFAULT '[]',
                        stopping_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(industry_id,round_no));
                    CREATE TABLE IF NOT EXISTS coverage_round_queries (
                        id TEXT PRIMARY KEY,
                        round_id TEXT NOT NULL REFERENCES coverage_rounds(id) ON DELETE CASCADE,
                        cell_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('entity','relation')),
                        language TEXT NOT NULL, family TEXT NOT NULL DEFAULT '',
                        dimensions_json TEXT NOT NULL, query TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'planned',
                        outcome_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(round_id,kind,cell_id,query));
                    CREATE TABLE IF NOT EXISTS entity_candidates (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        round_id TEXT NOT NULL REFERENCES coverage_rounds(id) ON DELETE CASCADE,
                        query_id TEXT REFERENCES coverage_round_queries(id),
                        cell_id TEXT NOT NULL, canonical_key TEXT NOT NULL,
                        payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate'
                            CHECK(status IN ('candidate','manual_review','accepted','rejected')),
                        status_reason TEXT NOT NULL DEFAULT '', entity_id TEXT REFERENCES entities(id),
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(industry_id,canonical_key,cell_id));
                    CREATE TABLE IF NOT EXISTS relation_candidates (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        round_id TEXT NOT NULL REFERENCES coverage_rounds(id) ON DELETE CASCADE,
                        query_id TEXT REFERENCES coverage_round_queries(id),
                        cell_id TEXT NOT NULL, canonical_key TEXT NOT NULL,
                        payload_json TEXT NOT NULL, document_id TEXT REFERENCES documents(id),
                        assertion_id TEXT REFERENCES agent_assertions(id),
                        status TEXT NOT NULL DEFAULT 'candidate'
                            CHECK(status IN ('candidate','manual_review','accepted','rejected')),
                        status_reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        UNIQUE(industry_id,canonical_key,cell_id));
                    CREATE TABLE IF NOT EXISTS coverage_candidate_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        candidate_kind TEXT NOT NULL CHECK(candidate_kind IN ('entity','relation')),
                        candidate_id TEXT NOT NULL, from_status TEXT NOT NULL,
                        to_status TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL, occurred_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_coverage_rounds_industry
                        ON coverage_rounds(industry_id,round_no DESC);
                    CREATE INDEX IF NOT EXISTS idx_coverage_queries_round
                        ON coverage_round_queries(round_id,status,kind);
                    CREATE INDEX IF NOT EXISTS idx_entity_candidates_review
                        ON entity_candidates(industry_id,status,updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_relation_candidates_review
                        ON relation_candidates(industry_id,status,updated_at DESC);
                    CREATE TRIGGER IF NOT EXISTS coverage_candidate_reviews_no_update
                    BEFORE UPDATE ON coverage_candidate_reviews BEGIN
                        SELECT RAISE(ABORT, 'coverage_candidate_reviews is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS coverage_candidate_reviews_no_delete
                    BEFORE DELETE ON coverage_candidate_reviews BEGIN
                        SELECT RAISE(ABORT, 'coverage_candidate_reviews is append-only');
                    END;
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (18, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=19").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS story_daily_snapshots (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
                        source_observation_id TEXT NOT NULL REFERENCES story_observations(id),
                        intelligence_date TEXT NOT NULL, observed_at TEXT NOT NULL,
                        rank INTEGER NOT NULL CHECK(rank > 0), score REAL NOT NULL,
                        independent_publishers INTEGER NOT NULL CHECK(independent_publishers >= 0),
                        publisher_clusters_json TEXT NOT NULL,
                        evidence_strength REAL NOT NULL CHECK(evidence_strength >= 0),
                        classification TEXT NOT NULL, algorithm_version TEXT NOT NULL,
                        raw_json TEXT NOT NULL, created_at TEXT NOT NULL,
                        UNIQUE(industry_id,story_id,intelligence_date,algorithm_version));
                    CREATE INDEX IF NOT EXISTS idx_story_daily_snapshot_timeline
                        ON story_daily_snapshots(industry_id,story_id,intelligence_date,
                                                 algorithm_version);
                    CREATE TRIGGER IF NOT EXISTS story_daily_snapshots_no_update
                    BEFORE UPDATE ON story_daily_snapshots BEGIN
                        SELECT RAISE(ABORT, 'story_daily_snapshots is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS story_daily_snapshots_no_delete
                    BEFORE DELETE ON story_daily_snapshots
                    WHEN EXISTS(SELECT 1 FROM industries WHERE id=OLD.industry_id) BEGIN
                        SELECT RAISE(ABORT, 'story_daily_snapshots is append-only');
                    END;
                """)
                con.execute("""INSERT OR IGNORE INTO story_daily_snapshots
                    (id,industry_id,story_id,source_observation_id,intelligence_date,
                     observed_at,rank,score,independent_publishers,publisher_clusters_json,
                     evidence_strength,classification,algorithm_version,raw_json,created_at)
                    SELECT 'sday_' || id,industry_id,story_id,id,intelligence_date,
                    observed_at,rank,score,independent_publishers,publisher_clusters_json,
                    evidence_strength,classification,algorithm_version,raw_json,created_at
                    FROM story_observations
                    WHERE id IN (SELECT MIN(id) FROM story_observations
                        GROUP BY industry_id,story_id,intelligence_date,algorithm_version)""")
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (19, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=20").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS task_runs (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        operation TEXT NOT NULL,
                        origin TEXT NOT NULL CHECK(origin IN
                            ('app','manual','system_schedule','background_worker')),
                        status TEXT NOT NULL CHECK(status IN
                            ('queued','running','cancelling','paused','completed','partial',
                             'failed','cancelled','interrupted')),
                        input_json TEXT NOT NULL DEFAULT '{}',
                        provider TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
                        parent_run_id TEXT REFERENCES task_runs(id) ON DELETE SET NULL,
                        window_start TEXT, window_end TEXT, window_timezone TEXT,
                        output_path TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT 'queued',
                        progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                        checkpoint_json TEXT NOT NULL DEFAULT '{}',
                        error_json TEXT NOT NULL DEFAULT '{}',
                        lease_owner TEXT, lease_expires_at TEXT,
                        lease_ttl_seconds INTEGER NOT NULL DEFAULT 60,
                        heartbeat_at TEXT, request_dispatched_at TEXT,
                        credential_handle_ref TEXT,
                        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                        updated_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS task_state_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
                        from_status TEXT,
                        to_status TEXT NOT NULL CHECK(to_status IN
                            ('queued','running','cancelling','paused','completed','partial',
                             'failed','cancelled','interrupted')),
                        action TEXT NOT NULL, actor TEXT NOT NULL,
                        details_json TEXT NOT NULL DEFAULT '{}', occurred_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS background_authorizations (
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        provider TEXT NOT NULL, operation TEXT NOT NULL,
                        allowed INTEGER NOT NULL DEFAULT 0 CHECK(allowed IN (0,1)),
                        granted_by TEXT NOT NULL DEFAULT '', granted_at TEXT NOT NULL DEFAULT '',
                        revoked_by TEXT, revoked_at TEXT, updated_at TEXT NOT NULL,
                        PRIMARY KEY(industry_id,provider,operation));
                    CREATE INDEX IF NOT EXISTS idx_task_runs_industry_status
                        ON task_runs(industry_id,status,updated_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_task_runs_lease
                        ON task_runs(status,lease_expires_at);
                    CREATE INDEX IF NOT EXISTS idx_task_events_run
                        ON task_state_events(run_id,id);
                    CREATE TRIGGER IF NOT EXISTS task_state_events_no_update
                    BEFORE UPDATE ON task_state_events BEGIN
                        SELECT RAISE(ABORT, 'task_state_events is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS task_state_events_no_delete
                    BEFORE DELETE ON task_state_events
                    WHEN EXISTS(SELECT 1 FROM task_runs WHERE id=OLD.run_id) BEGIN
                        SELECT RAISE(ABORT, 'task_state_events is append-only');
                    END;
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (20, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=21").fetchone():
                for statement in (
                    "ALTER TABLE automation_schedules ADD COLUMN last_period_identity TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN attempted_period_identity TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN runtime_status TEXT NOT NULL DEFAULT 'idle'",
                    "ALTER TABLE automation_schedules ADD COLUMN pause_reason TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE automation_schedules ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 5",
                    "ALTER TABLE automation_schedules ADD COLUMN last_origin TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE automation_schedules ADD COLUMN last_window_start TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN last_window_end TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN last_window_timezone TEXT",
                    "ALTER TABLE automation_schedules ADD COLUMN last_success_boundary TEXT",
                ):
                    try:
                        con.execute(statement)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).casefold():
                            raise
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS worker_wakeups (
                        id TEXT PRIMARY KEY, owner TEXT NOT NULL, origin TEXT NOT NULL,
                        started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                        summary_json TEXT NOT NULL DEFAULT '{}', error_json TEXT NOT NULL DEFAULT '{}');
                    CREATE INDEX IF NOT EXISTS idx_worker_wakeups_started
                        ON worker_wakeups(started_at DESC);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (21, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=22").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS workflow_settings (
                        scope_key TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        settings_json TEXT NOT NULL DEFAULT '{}',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(scope_key,operation));
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (22, utc_now()))
            if not con.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=23").fetchone():
                _execute_script(con, """
                    CREATE TABLE IF NOT EXISTS agent_conversations (
                        id TEXT PRIMARY KEY,
                        industry_id TEXT NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
                        provider TEXT NOT NULL,
                        external_session_id TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        archived_at TEXT);
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_conversation_active
                        ON agent_conversations(industry_id,provider)
                        WHERE archived_at IS NULL;
                    CREATE TABLE IF NOT EXISTS conversation_messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL REFERENCES agent_conversations(id)
                            ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_conversation_messages
                        ON conversation_messages(conversation_id,created_at,id);
                    CREATE TABLE IF NOT EXISTS action_proposals (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL REFERENCES agent_conversations(id)
                            ON DELETE CASCADE,
                        revision INTEGER NOT NULL DEFAULT 1,
                        action TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
                        status TEXT NOT NULL CHECK(status IN
                            ('pending','confirmed','rejected','expired','executed','failed')),
                        expires_at TEXT NOT NULL, confirmed_at TEXT,
                        task_run_id TEXT REFERENCES task_runs(id) ON DELETE SET NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS idx_action_proposals_conversation
                        ON action_proposals(conversation_id,status,created_at);
                """)
                con.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",
                            (23, utc_now()))


    def ensure_industry(self, folder: str, name: str = "") -> str:
        iid = stable_id("ind", folder)
        now = utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO industries(id,folder,name,created_at,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(folder) DO UPDATE SET
                name=CASE WHEN excluded.name!='' THEN excluded.name ELSE industries.name END,
                status='active',updated_at=excluded.updated_at
                WHERE industries.name!=excluded.name OR industries.status!='active'""",
                        (iid, folder, name or folder, now, now))
        return iid

    def industry_id(self, folder: str) -> str:
        """Return an existing industry id without mutating repository state."""
        with self.connection() as con:
            row = con.execute("SELECT id FROM industries WHERE folder=?", (folder,)).fetchone()
        if not row:
            raise FileNotFoundError(f"行业不存在：{folder}")
        return row["id"]

    @staticmethod
    def _mark_compat_dirty(con: sqlite3.Connection, industry_id: str,
                           view_key: str) -> None:
        con.execute("""INSERT INTO compatibility_views
            (industry_id,view_key,dirty,last_error,updated_at) VALUES(?,?,1,NULL,?)
            ON CONFLICT(industry_id,view_key) DO UPDATE SET
            dirty=1,last_error=NULL,updated_at=excluded.updated_at""",
                    (industry_id, view_key, utc_now()))

    def mark_compat_clean(self, folder: str, view_key: str) -> None:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            con.execute("""INSERT INTO compatibility_views
                (industry_id,view_key,dirty,last_error,updated_at) VALUES(?,?,0,NULL,?)
                ON CONFLICT(industry_id,view_key) DO UPDATE SET
                dirty=0,last_error=NULL,updated_at=excluded.updated_at""",
                        (iid, view_key, utc_now()))

    def mark_compat_error(self, folder: str, view_key: str, error: Exception) -> None:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            con.execute("""UPDATE compatibility_views SET dirty=1,last_error=?,updated_at=?
                WHERE industry_id=? AND view_key=?""",
                        (f"{type(error).__name__}: {error}", utc_now(), iid, view_key))

    def dirty_compat_views(self, folders: list[str] | None = None) -> list[dict]:
        sql = """SELECT i.folder,v.view_key,v.last_error,v.updated_at
            FROM compatibility_views v JOIN industries i ON i.id=v.industry_id
            WHERE v.dirty=1"""
        args: list[object] = []
        if folders:
            marks = ",".join("?" for _ in folders)
            sql += f" AND i.folder IN ({marks})"; args.extend(folders)
        sql += " ORDER BY v.updated_at"
        with self.connection() as con:
            return [dict(row) for row in con.execute(sql, args)]

    def list_industries(self) -> list[dict]:
        with self.connection() as con:
            return [dict(row) for row in con.execute(
                "SELECT * FROM industries WHERE status='active' ORDER BY folder")]

    def rename_industry(self, old_folder: str, new_folder: str, name: str = "") -> None:
        now = utc_now()
        with self.transaction() as con:
            cur = con.execute("""UPDATE industries SET folder=?,name=CASE WHEN ?!='' THEN ?
                ELSE name END,updated_at=? WHERE folder=? AND status='active'""",
                (new_folder, name, name, now, old_folder))
            if cur.rowcount != 1:
                raise FileNotFoundError(f"行业不存在：{old_folder}")

    def archive_industry(self, folder: str) -> None:
        with self.transaction() as con:
            cur = con.execute("UPDATE industries SET status='archived',updated_at=? WHERE folder=?",
                              (utc_now(), folder))
            if cur.rowcount != 1:
                raise FileNotFoundError(f"行业不存在：{folder}")

    def delete_source(self, folder: str, category: str, url: str) -> bool:
        iid = self.industry_id(folder)
        sid = stable_id("src", canonical_url(url))
        with self.transaction() as con:
            cur = con.execute("""UPDATE industry_sources SET deleted_at=?
                WHERE industry_id=? AND source_id=? AND category=? AND deleted_at IS NULL""",
                (utc_now(), iid, sid, category))
            if cur.rowcount:
                self._mark_compat_dirty(con, iid, "sources")
        return cur.rowcount > 0

    def _upsert_source_in_transaction(self, con: sqlite3.Connection, iid: str,
                                      category: str, item: dict, *,
                                      monitoring_status: str) -> str:
        url = canonical_url(item.get("url", ""))
        if not url:
            raise ValueError("来源需要有效的 http/https URL")
        sid = stable_id("src", url)
        publisher = publisher_profile({**item, "url": url})
        publisher_id = stable_id("pub", publisher["owner_cluster"])
        now = utc_now()
        stored_item = {**item, "monitoring_status": monitoring_status}
        con.execute("""INSERT INTO sources
            (id,canonical_url,name,publisher_country,metadata_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(canonical_url) DO UPDATE SET
            name=excluded.name,publisher_country=excluded.publisher_country,
            metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
            (sid, url, item.get("name") or url, item.get("publisher_country", ""),
             json_text(stored_item), now, now))
        con.execute("""INSERT INTO publishers
            (id,canonical_name,country,owner_cluster,verification_status,
             metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
            canonical_name=excluded.canonical_name,
            country=CASE WHEN excluded.country!='' THEN excluded.country ELSE publishers.country END,
            verification_status=CASE WHEN excluded.verification_status='verified'
                THEN 'verified' ELSE publishers.verification_status END,
            metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
            (publisher_id, publisher["name"], item.get("publisher_country", ""),
             publisher["owner_cluster"], publisher["verification_status"],
             json_text(publisher), now, now))
        if publisher["domain"]:
            con.execute("""INSERT INTO publisher_domains(domain,publisher_id,verified,source)
                VALUES(?,?,?,?) ON CONFLICT(domain) DO UPDATE SET
                publisher_id=excluded.publisher_id,
                verified=MAX(publisher_domains.verified,excluded.verified)""",
                (publisher["domain"], publisher_id,
                 int(publisher["verification_status"] == "verified"), "registry"))
        con.execute("""INSERT OR REPLACE INTO source_publishers
            (source_id,publisher_id,relation,confidence) VALUES(?,?,?,?)""",
            (sid, publisher_id, "publishes",
             1.0 if publisher["verification_status"] == "verified" else 0.6))
        con.execute("""INSERT INTO industry_sources
            (industry_id,source_id,category,monitoring_status,added_manually,metadata_json)
            VALUES(?,?,?,?,?,?) ON CONFLICT(industry_id,source_id,category) DO UPDATE SET
            monitoring_status=excluded.monitoring_status,
            added_manually=MAX(industry_sources.added_manually,excluded.added_manually),
            metadata_json=excluded.metadata_json,deleted_at=NULL""",
            (iid, sid, category, monitoring_status,
             int(bool(item.get("added_manually"))), json_text(stored_item)))
        self._mark_compat_dirty(con, iid, "sources")
        return sid

    def upsert_source(self, folder: str, category: str, item: dict) -> str:
        from src.source_review import assess_source_candidate

        iid = self.industry_id(folder)
        requested = str(item.get("monitoring_status") or "recommended_manual").casefold()
        monitoring_status = requested
        if item.get("added_manually"):
            monitoring_status = "recommended_manual"
        elif requested == "active":
            assessment = assess_source_candidate(item, category=category)
            monitoring_status = (
                "active" if assessment["decision"] == "active"
                else "recommended_manual")
        elif requested in {"manual", "manual_review"}:
            monitoring_status = "recommended_manual"
        elif requested not in {"recommended_manual", "reserve", "quarantined", "rejected"}:
            monitoring_status = "recommended_manual"
        with self.transaction() as con:
            return self._upsert_source_in_transaction(
                con, iid, category, item, monitoring_status=monitoring_status)

    def list_sources(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT s.*,x.category,x.monitoring_status,
                x.added_manually,x.metadata_json AS link_json,
                h.adapter,h.status AS health_status,h.last_checked_at,
                h.last_success_at,h.last_good_at,h.retry_after,
                h.consecutive_failures,h.error_code,h.error_message
                FROM industry_sources x
                JOIN sources s ON s.id=x.source_id
                LEFT JOIN source_health h ON h.industry_id=x.industry_id
                    AND h.source_id=x.source_id
                WHERE x.industry_id=? AND x.deleted_at IS NULL
                ORDER BY x.category,s.name""", (iid,)).fetchall()
        out = []
        for row in rows:
            item = json_value(row["metadata_json"], {})
            item.update(json_value(row["link_json"], {}))
            item.update({"id": row["id"], "url": row["canonical_url"],
                         "name": row["name"], "category": row["category"]})
            item["monitoring_status"] = row["monitoring_status"]
            item["added_manually"] = bool(row["added_manually"])
            item["health"] = {
                "adapter": row["adapter"],
                "status": row["health_status"] or "unconfigured",
                "last_checked_at": row["last_checked_at"],
                "last_success_at": row["last_success_at"],
                "last_good_at": row["last_good_at"],
                "retry_after": row["retry_after"],
                "consecutive_failures": row["consecutive_failures"] or 0,
                "error_code": row["error_code"],
                "error_message": row["error_message"],
            }
            profile = publisher_profile(item)
            item.update({"publisher_cluster": profile["owner_cluster"],
                         "publisher_verification": profile["verification_status"],
                         "publisher_evidence_type": profile["evidence_type"]})
            out.append(item)
        return out

    def retain_source_links(self, folder: str, active: set[tuple[str, str]]) -> None:
        """Soft-delete industry source links absent from an authoritative refresh."""
        iid = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            rows = con.execute("""SELECT source_id,category FROM industry_sources
                WHERE industry_id=? AND deleted_at IS NULL""", (iid,)).fetchall()
            for row in rows:
                if (row["source_id"], row["category"]) not in active:
                    con.execute("""UPDATE industry_sources SET deleted_at=?
                        WHERE industry_id=? AND source_id=? AND category=?""",
                        (now, iid, row["source_id"], row["category"]))
            self._mark_compat_dirty(con, iid, "sources")

    def update_source_health(self, folder: str, source_id: str, *, adapter: str,
                             status: str, error_code: str = "",
                             error_message: str = "", retry_after: str | None = None,
                             metadata: dict | None = None) -> None:
        allowed = {"fresh", "stale", "degraded", "manual", "unconfigured", "failed"}
        if status not in allowed:
            raise ValueError("无效来源健康状态")
        iid, now = self.industry_id(folder), utc_now()
        success = status == "fresh"
        with self.transaction() as con:
            previous = con.execute("""SELECT consecutive_failures,last_success_at,last_good_at
                FROM source_health WHERE industry_id=? AND source_id=?""",
                (iid, source_id)).fetchone()
            failures = 0 if success else int(
                previous["consecutive_failures"] if previous else 0) + 1
            last_success = now if success else (
                previous["last_success_at"] if previous else None)
            last_good = now if success else (
                previous["last_good_at"] if previous else None)
            con.execute("""INSERT INTO source_health
                (industry_id,source_id,adapter,status,last_checked_at,last_success_at,
                 last_good_at,retry_after,consecutive_failures,error_code,error_message,
                 metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(industry_id,source_id) DO UPDATE SET
                adapter=excluded.adapter,status=excluded.status,
                last_checked_at=excluded.last_checked_at,
                last_success_at=excluded.last_success_at,last_good_at=excluded.last_good_at,
                retry_after=excluded.retry_after,
                consecutive_failures=excluded.consecutive_failures,
                error_code=excluded.error_code,error_message=excluded.error_message,
                metadata_json=excluded.metadata_json""",
                (iid, source_id, adapter, status, now, last_success, last_good,
                 retry_after, failures, error_code, error_message,
                 json_text(metadata or {})))
            dimensions = {"source_id": source_id, "adapter": adapter,
                          "error_code": error_code or "none"}
            self._insert_quality_observation(con, iid, {
                "observed_at": now, "metric": "source_success_rate",
                "numerator": int(success), "denominator": 1,
                "algorithm_version": "source-health-v1", "dimensions": dimensions,
            })
            latency = (metadata or {}).get("latency_ms")
            if latency is not None:
                self._insert_quality_observation(con, iid, {
                    "observed_at": now, "metric": "source_latency_ms",
                    "numerator": latency, "denominator": 1,
                    "algorithm_version": "source-health-v1", "dimensions": dimensions,
                })

    def save_story_groups(self, folder: str, groups: list[dict],
                          clustering_version: str) -> list[str]:
        """Persist clusters while preserving identity through document overlap."""
        iid, now = self.industry_id(folder), utc_now()
        saved: list[str] = []
        run_observed: list[str] = []
        with self.transaction() as con:
            locked_documents = {row["document_id"] for row in con.execute(
                "SELECT document_id FROM story_editorial_constraints WHERE industry_id=?",
                (iid,))}
            for group in groups:
                documents = [item for item in group.get("documents", [])
                             if item.get("document_id") and
                             item.get("document_id") not in locked_documents]
                if not documents:
                    continue
                marks = ",".join("?" for _ in documents)
                existing = con.execute(f"""SELECT sd.story_id,COUNT(*) AS overlap
                    FROM story_documents sd JOIN stories s ON s.id=sd.story_id
                    WHERE s.industry_id=? AND sd.document_id IN ({marks})
                    GROUP BY sd.story_id ORDER BY overlap DESC,sd.story_id LIMIT 1""",
                    [iid, *[item["document_id"] for item in documents]]).fetchone()
                story_id = existing["story_id"] if existing else stable_id(
                    "story", f"{iid}:{normalized_name(group.get('title', ''))}")
                observed = [str(item.get("observed_at") or now) for item in documents]
                run_observed.extend(observed)
                con.execute("""INSERT INTO stories
                    (id,industry_id,canonical_title,story_family,status,
                     clustering_version,first_seen_at,last_seen_at,metadata_json,
                     created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                    canonical_title=excluded.canonical_title,
                    last_seen_at=MAX(stories.last_seen_at,excluded.last_seen_at),
                    clustering_version=excluded.clustering_version,
                    metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                    (story_id, iid, group.get("title") or "Untitled",
                     group.get("story_family") or "event",
                     group.get("status") or "candidate", clustering_version,
                     min(observed), max(observed), json_text(group.get("metadata") or {}),
                     now, now))
                for item in documents:
                    con.execute("""INSERT INTO story_documents
                        (story_id,document_id,relation,publisher_cluster,added_at)
                        VALUES(?,?,?,?,?) ON CONFLICT(story_id,document_id) DO UPDATE SET
                        publisher_cluster=excluded.publisher_cluster""",
                        (story_id, item["document_id"], item.get("relation", "reports"),
                         item.get("publisher_cluster"), now))
                saved.append(story_id)
            from src.signal_momentum import rank_signals
            from intdog_core.observability_repository import _intelligence_date
            run_observed_at = max(run_observed) if run_observed else now
            run_day = _intelligence_date(run_observed_at)
            qualified = con.execute("""SELECT id,status,last_seen_at,metadata_json FROM stories
                WHERE industry_id=? AND status IN
                ('accepted','verified','corroborated','collected')""", (iid,)).fetchall()
            signals = []
            for story in qualified:
                if _intelligence_date(story["last_seen_at"]) != run_day:
                    continue
                metadata = json_value(story["metadata_json"], {})
                clusters = [row[0] for row in con.execute("""SELECT DISTINCT
                    publisher_cluster FROM story_documents WHERE story_id=?
                    AND publisher_cluster IS NOT NULL AND publisher_cluster!=''
                    ORDER BY publisher_cluster""", (story["id"],))]
                signals.append({
                    "story_id": story["id"],
                    "score": float(metadata.get(
                        "ranking_score", metadata.get("source_quality", 0)) or 0),
                    "publisher_clusters": clusters,
                    "evidence_strength": float(metadata.get(
                        "evidence_strength", metadata.get("source_quality", 0)) or 0),
                    "classification": story["status"],
                })
            for signal in rank_signals(signals):
                self._insert_story_observation(con, iid, signal["story_id"], {
                    "observed_at": run_observed_at, "rank": signal["rank"],
                    "score": signal["score"],
                    "publisher_clusters": signal["publisher_clusters"],
                    "evidence_strength": signal["evidence_strength"],
                    "classification": signal["classification"],
                    "algorithm_version": clustering_version,
                }, canonical_snapshot=True)
        return saved

    def list_stories(self, folder: str, limit: int = 100) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT s.*,COUNT(sd.document_id) AS document_count,
                COUNT(DISTINCT sd.publisher_cluster) AS publisher_count
                FROM stories s LEFT JOIN story_documents sd ON sd.story_id=s.id
                WHERE s.industry_id=? AND s.status NOT IN ('merged','ignored') GROUP BY s.id
                ORDER BY s.last_seen_at DESC LIMIT ?""", (iid, limit)).fetchall()
        return [dict(row) for row in rows]

    def ignore_story(self, folder: str, story_id: str, *, actor: str,
                     reason: str) -> None:
        """Hide one Story while retaining an auditable drift signal."""
        iid, now = self.industry_id(folder), utc_now()
        actor = str(actor or "").strip()
        reason = str(reason or "").strip()
        if not actor or not reason:
            raise ValueError("actor and reason are required")
        with self.transaction() as con:
            story = con.execute(
                "SELECT status FROM stories WHERE id=? AND industry_id=?",
                (story_id, iid)).fetchone()
            if story is None:
                raise FileNotFoundError("Story 不存在")
            if story["status"] == "ignored":
                raise ValueError("Story already ignored")
            snapshot = con.execute("""SELECT rank,intelligence_date,algorithm_version
                FROM story_daily_snapshots WHERE industry_id=? AND story_id=?
                ORDER BY intelligence_date DESC,observed_at DESC,id DESC LIMIT 1""",
                (iid, story_id)).fetchone()
            con.execute("UPDATE stories SET status='ignored',updated_at=? WHERE id=?",
                        (now, story_id))
            details = {"reason": reason}
            if snapshot:
                details.update({"rank": int(snapshot["rank"]),
                                "intelligence_date": snapshot["intelligence_date"],
                                "ranking_version": snapshot["algorithm_version"]})
            con.execute("""INSERT INTO story_reviews
                (story_id,action,actor,details_json,occurred_at) VALUES(?,?,?,?,?)""",
                (story_id, "ignore", actor, json_text(details), now))
            self._insert_quality_observation(con, iid, {
                "observed_at": now, "metric": "top_item_ignore_rate",
                "numerator": 1, "denominator": 1,
                "algorithm_version": "story-editorial-v1",
                "dimensions": {"story_id": story_id, "rank": (
                    int(snapshot["rank"]) if snapshot else 0), "reason": reason},
            })

    def merge_stories(self, folder: str, target_id: str, source_id: str,
                      actor: str = "app") -> None:
        iid, now = self.industry_id(folder), utc_now()
        if target_id == source_id:
            raise ValueError("不能合并同一个 Story")
        with self.transaction() as con:
            count = con.execute("""SELECT COUNT(*) FROM stories
                WHERE industry_id=? AND id IN (?,?)""",
                (iid, target_id, source_id)).fetchone()[0]
            if count != 2:
                raise FileNotFoundError("Story 不存在")
            con.execute("""INSERT OR IGNORE INTO story_documents
                (story_id,document_id,relation,publisher_cluster,added_at)
                SELECT ?,document_id,relation,publisher_cluster,?
                FROM story_documents WHERE story_id=?""", (target_id, now, source_id))
            con.execute("DELETE FROM story_documents WHERE story_id=?", (source_id,))
            con.execute("UPDATE stories SET status='merged',updated_at=? WHERE id=?",
                        (now, source_id))
            documents = [row[0] for row in con.execute(
                "SELECT document_id FROM story_documents WHERE story_id=?", (target_id,))]
            for document_id in documents:
                con.execute("""INSERT INTO story_editorial_constraints
                    (industry_id,document_id,story_id,decision,actor,rationale,created_at,updated_at)
                    VALUES(?,?,?,'locked',?,'manual merge',?,?)
                    ON CONFLICT(industry_id,document_id) DO UPDATE SET
                    story_id=excluded.story_id,decision='locked',actor=excluded.actor,
                    rationale=excluded.rationale,updated_at=excluded.updated_at""",
                    (iid, document_id, target_id, actor, now, now))
            con.execute("""INSERT INTO story_reviews
                (story_id,action,actor,details_json,occurred_at) VALUES(?,?,?,?,?)""",
                (target_id, "merge", actor, json_text({"source_story_id": source_id}), now))
            self._insert_quality_observation(con, iid, {
                "observed_at": now, "metric": "manual_correction_rate",
                "numerator": 1, "denominator": 1,
                "algorithm_version": "story-editorial-v1",
                "dimensions": {"action": "merge"},
            })

    def split_story(self, folder: str, story_id: str, document_ids: list[str],
                    title: str, actor: str = "app") -> str:
        iid, now = self.industry_id(folder), utc_now()
        if not document_ids or not title.strip():
            raise ValueError("拆分需要文档和标题")
        new_id = stable_id("story", f"{iid}:{normalized_name(title)}:{now}")
        marks = ",".join("?" for _ in document_ids)
        with self.transaction() as con:
            source = con.execute("SELECT * FROM stories WHERE id=? AND industry_id=?",
                                 (story_id, iid)).fetchone()
            if source is None:
                raise FileNotFoundError("Story 不存在")
            rows = con.execute(f"""SELECT * FROM story_documents
                WHERE story_id=? AND document_id IN ({marks})""",
                [story_id, *document_ids]).fetchall()
            if len(rows) != len(set(document_ids)):
                raise ValueError("拆分文档不完全属于原 Story")
            con.execute("""INSERT INTO stories
                (id,industry_id,canonical_title,story_family,status,clustering_version,
                 first_seen_at,last_seen_at,metadata_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id, iid, title.strip(), source["story_family"], "reviewed",
                 source["clustering_version"], now, now, "{}", now, now))
            for row in rows:
                con.execute("""INSERT INTO story_documents
                    (story_id,document_id,relation,publisher_cluster,added_at)
                    VALUES(?,?,?,?,?)""", (new_id, row["document_id"], row["relation"],
                                           row["publisher_cluster"], now))
            con.execute(f"DELETE FROM story_documents WHERE story_id=? AND document_id IN ({marks})",
                        [story_id, *document_ids])
            remaining = [row[0] for row in con.execute(
                "SELECT document_id FROM story_documents WHERE story_id=?", (story_id,))]
            for locked_story, locked_documents in ((new_id, document_ids),
                                                   (story_id, remaining)):
                for document_id in locked_documents:
                    con.execute("""INSERT INTO story_editorial_constraints
                        (industry_id,document_id,story_id,decision,actor,rationale,created_at,updated_at)
                        VALUES(?,?,?,'locked',?,'manual split',?,?)
                        ON CONFLICT(industry_id,document_id) DO UPDATE SET
                        story_id=excluded.story_id,decision='locked',actor=excluded.actor,
                        rationale=excluded.rationale,updated_at=excluded.updated_at""",
                        (iid, document_id, locked_story, actor, now, now))
            con.execute("""INSERT INTO story_reviews
                (story_id,action,actor,details_json,occurred_at) VALUES(?,?,?,?,?)""",
                (story_id, "split", actor,
                 json_text({"new_story_id": new_id, "document_ids": document_ids}), now))
            self._insert_quality_observation(con, iid, {
                "observed_at": now, "metric": "manual_correction_rate",
                "numerator": 1, "denominator": 1,
                "algorithm_version": "story-editorial-v1",
                "dimensions": {"action": "split"},
            })
        return new_id

    def upsert_document(self, folder: str, category: str, date: str, item: dict) -> str:
        ids = self.upsert_documents(folder, category, date, [item], strict=True)
        return ids[0]

    def upsert_documents(self, folder: str, category: str, date: str,
                         items: list[dict], *, strict: bool = False) -> list[str]:
        iid = self.industry_id(folder)
        now = utc_now()
        prepared = []
        for item in items:
            url = canonical_url(item.get("url", ""))
            title = str(item.get("title") or "").strip()
            if not url or not title:
                if strict:
                    raise ValueError("文档需要 title 和有效 URL")
                continue
            sid = None
            if item.get("source_url"):
                try:
                    sid = self.upsert_source(folder, item.get("source_category", "news"), {
                        "name": item.get("source") or item["source_url"],
                        "url": item["source_url"]})
                except ValueError:
                    pass
            prepared.append((stable_id("doc", url), url, title, sid, item))
        with self.transaction() as con:
            for did, url, title, sid, item in prepared:
                metadata = {key: value for key, value in item.items()
                            if key not in {"title", "abstract", "summary", "url"}}
                con.execute("""INSERT INTO documents
                    (id,canonical_url,content_hash,title,abstract,source_id,published_at,
                     retrieved_at,language,origin,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(canonical_url) DO UPDATE SET title=excluded.title,
                    abstract=CASE WHEN excluded.abstract!='' THEN excluded.abstract
                                  ELSE documents.abstract END,
                    content_hash=COALESCE(excluded.content_hash,documents.content_hash),
                    retrieved_at=excluded.retrieved_at,raw_json=excluded.raw_json""",
                    (did, url, item.get("content_hash"), title,
                     item.get("abstract") or item.get("summary", ""), sid,
                     item.get("published_at") or item.get("published") or date,
                     item.get("retrieved_at") or now,
                     item.get("source_language") or item.get("lang"),
                     item.get("origin"), json_text(item)))
                con.execute("""INSERT INTO industry_documents
                    (industry_id,document_id,category,observed_date,review_status,credibility,
                     ranking_score,metadata_json) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(industry_id,document_id,category,observed_date) DO UPDATE SET
                    review_status=excluded.review_status,credibility=excluded.credibility,
                    ranking_score=excluded.ranking_score,metadata_json=excluded.metadata_json,
                    deleted_at=NULL""",
                    (iid, did, category, date, item.get("review_status", "unreviewed"),
                     item.get("evidence_status") or
                     ("corroborated" if item.get("verified") else "collected"),
                     item.get("ranking_score"), json_text(metadata)))
            if prepared:
                self._mark_compat_dirty(con, iid, f"daily:{date}:{category}")
        return [row[0] for row in prepared]

    def apply_document_dedup_plan(self, folder: str, plan: dict,
                                  actor: str = "deduplication") -> int:
        """Soft-delete duplicate memberships and enrich their stable representative."""
        iid, now = self.industry_id(folder), utc_now()
        removed = 0
        with self.transaction() as con:
            for group in plan.get("duplicate_groups", []) or []:
                keeper = group.get("keeper") or {}
                keeper_id = str(keeper.get("id") or "")
                if not keeper_id:
                    continue
                con.execute("""UPDATE documents SET title=?,abstract=?,content_hash=?,raw_json=?
                    WHERE id=?""", (keeper.get("title") or "Untitled",
                    keeper.get("abstract") or keeper.get("summary") or "",
                    keeper.get("content_hash"), json_text(keeper), keeper_id))
                self._mark_compat_dirty(
                    con, iid, f"daily:{keeper.get('date')}:{keeper.get('category')}")
                for duplicate in group.get("duplicates", []) or []:
                    cur = con.execute("""UPDATE industry_documents SET deleted_at=?
                        WHERE industry_id=? AND document_id=? AND category=?
                        AND observed_date=? AND deleted_at IS NULL""",
                        (now, iid, duplicate.get("id"), duplicate.get("category"),
                         duplicate.get("date")))
                    removed += cur.rowcount
                    self._mark_compat_dirty(
                        con, iid, f"daily:{duplicate.get('date')}:{duplicate.get('category')}")
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,?,?,?)""", (now, actor, "deduplicate_history", "industry",
                iid, json_text({"algorithm": plan.get("algorithm"),
                                "input_links": plan.get("input_links", 0),
                                "suppressed_links": removed,
                                "reasons": plan.get("reasons", {})})))
        return removed

    def list_documents(self, folder: str, date: str | None = None,
                       category: str | None = None, limit: int = 5000) -> list[dict]:
        iid = self.industry_id(folder)
        sql = """SELECT d.*,x.category,x.observed_date,x.review_status,x.credibility,
                 x.ranking_score,x.metadata_json FROM industry_documents x
                 JOIN documents d ON d.id=x.document_id
                 WHERE x.industry_id=? AND x.deleted_at IS NULL"""
        args: list[object] = [iid]
        if date:
            sql += " AND x.observed_date=?"; args.append(date)
        if category:
            sql += " AND x.category=?"; args.append(category)
        sql += " ORDER BY x.observed_date DESC,d.published_at DESC LIMIT ?"; args.append(limit)
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        out = []
        for row in rows:
            item = json_value(row["raw_json"], {})
            item.update(json_value(row["metadata_json"], {}))
            item.update({"id": row["id"], "title": row["title"],
                         "url": row["canonical_url"], "abstract": row["abstract"] or "",
                         "category": row["category"], "date": row["observed_date"],
                         "published_at": row["published_at"],
                         "review_status": row["review_status"],
                         "evidence_status": row["credibility"],
                         "ranking_score": row["ranking_score"]})
            out.append(item)
        return out

    def page_documents(self, folder: str, *, date: str | None = None,
                       category: str | None = None, query: str = "",
                       sort: str = "title", cursor: str = "",
                       limit: int = 50) -> dict:
        """Return a bounded document page and an opaque continuation cursor."""
        iid = self.industry_id(folder)
        limit = max(1, min(int(limit), 100))
        offset = 0
        if cursor:
            try:
                payload = json.loads(base64.urlsafe_b64decode(
                    cursor.encode("ascii") + b"==="))
                offset = max(0, int(payload["offset"]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("无效的分页游标") from exc
        where = ["x.industry_id=?", "x.deleted_at IS NULL"]
        args: list[object] = [iid]
        if date:
            where.append("x.observed_date=?")
            args.append(date)
        if category:
            where.append("x.category=?")
            args.append(category)
        if query.strip():
            where.append("""(d.title LIKE ? OR d.abstract LIKE ?
                OR d.raw_json LIKE ?)""")
            pattern = f"%{query.strip()}%"
            args.extend([pattern, pattern, pattern])
        # Keep server-side ordering aligned with the category-aware source label
        # returned by the API.  This matters across continuation pages: sorting
        # only a page in React would not produce a globally ordered result set.
        source_expr = """LOWER(CASE x.category
            WHEN 'github' THEN COALESCE(
                json_extract(d.raw_json,'$.owner'),
                json_extract(d.raw_json,'$.developer'),
                json_extract(d.raw_json,'$.author'), '')
            WHEN 'papers' THEN COALESCE(
                json_extract(d.raw_json,'$.authors'),
                json_extract(d.raw_json,'$.author'), '')
            WHEN 'ceo' THEN COALESCE(
                json_extract(d.raw_json,'$.account'),
                json_extract(d.raw_json,'$.publisher'),
                json_extract(d.raw_json,'$.author'), '')
            ELSE COALESCE(
                json_extract(d.raw_json,'$.source_name'),
                json_extract(d.raw_json,'$.publication'),
                json_extract(d.raw_json,'$.source'),
                json_extract(d.raw_json,'$.publisher'), '') END)"""
        order = {
            "title": "LOWER(d.title),d.id",
            "category": "LOWER(x.category),LOWER(d.title),d.id",
            "source": f"{source_expr},LOWER(d.title),d.id",
            "published_at": "COALESCE(d.published_at,x.observed_date),LOWER(d.title),d.id",
        }.get(sort)
        if order is None:
            raise ValueError("不支持的排序方式")
        predicate = " AND ".join(where)
        select = f"""SELECT d.*,x.category,x.observed_date,x.review_status,
            x.credibility,x.ranking_score,x.metadata_json
            FROM industry_documents x JOIN documents d ON d.id=x.document_id
            WHERE {predicate} ORDER BY {order} LIMIT ? OFFSET ?"""
        with self.connection() as con:
            total = int(con.execute(
                f"""SELECT COUNT(*) FROM industry_documents x
                    JOIN documents d ON d.id=x.document_id
                    WHERE {predicate}""", args).fetchone()[0])
            rows = con.execute(select, [*args, limit, offset]).fetchall()
        items = []
        for row in rows:
            item = json_value(row["raw_json"], {})
            item.update(json_value(row["metadata_json"], {}))
            item.update({
                "id": row["id"], "title": row["title"],
                "url": row["canonical_url"], "abstract": row["abstract"] or "",
                "category": row["category"], "date": row["observed_date"],
                "published_at": row["published_at"],
                "review_status": row["review_status"],
                "evidence_status": row["credibility"],
                "ranking_score": row["ranking_score"],
            })
            items.append(item)
        next_cursor = None
        if offset + len(items) < total:
            next_cursor = base64.urlsafe_b64encode(json.dumps(
                {"offset": offset + len(items)}, separators=(",", ":")
            ).encode("utf-8")).decode("ascii").rstrip("=")
        return {"items": items, "total": total, "next_cursor": next_cursor}

    def list_document_dates(self, folder: str) -> list[str]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT DISTINCT observed_date FROM industry_documents
                WHERE industry_id=? AND deleted_at IS NULL ORDER BY observed_date DESC""",
                (iid,)).fetchall()
        return [row[0] for row in rows]

    def search_documents(self, folder: str, query: str, limit: int = 50) -> list[dict]:
        if not str(query or "").strip() or query == "*":
            return [{"id": item["id"], "title": item["title"], "url": item["url"],
                     "abstract": item.get("abstract", ""),
                     "published_at": item.get("published_at", ""),
                     "category": item["category"], "observed_date": item["date"],
                     "rank": 0.0} for item in self.list_documents(folder, limit=limit)]
        iid = self.industry_id(folder)
        try:
            with self.connection() as con:
                rows = con.execute("""SELECT d.id,d.title,d.canonical_url AS url,d.abstract,
                    d.published_at,x.category,x.observed_date,bm25(documents_fts) AS rank
                    FROM documents_fts JOIN documents d ON d.rowid=documents_fts.rowid
                    JOIN industry_documents x ON x.document_id=d.id
                    WHERE documents_fts MATCH ? AND x.industry_id=? AND x.deleted_at IS NULL
                    ORDER BY rank LIMIT ?""", (query, iid, limit)).fetchall()
        except sqlite3.OperationalError:
            pattern = f"%{query}%"
            with self.connection() as con:
                rows = con.execute("""SELECT d.id,d.title,d.canonical_url AS url,d.abstract,
                    d.published_at,x.category,x.observed_date,0.0 AS rank
                    FROM documents d JOIN industry_documents x ON x.document_id=d.id
                    WHERE x.industry_id=? AND x.deleted_at IS NULL
                    AND (d.title LIKE ? OR d.abstract LIKE ?)
                    ORDER BY x.observed_date DESC LIMIT ?""",
                    (iid, pattern, pattern, limit)).fetchall()
        return [dict(row) for row in rows]

    def soft_delete_documents(self, folder: str, ids: list[str], actor: str = "app") -> int:
        if not ids:
            return 0
        iid = self.industry_id(folder)
        marks = ",".join("?" for _ in ids)
        now = utc_now()
        with self.transaction() as con:
            affected = con.execute(f"""SELECT DISTINCT observed_date,category
                FROM industry_documents WHERE industry_id=?
                AND document_id IN ({marks}) AND deleted_at IS NULL""",
                [iid, *ids]).fetchall()
            cur = con.execute(f"""UPDATE industry_documents SET deleted_at=?
                WHERE industry_id=? AND document_id IN ({marks}) AND deleted_at IS NULL""",
                [now, iid, *ids])
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,details_json) VALUES(?,?,?,?,?)""",
                (now, actor, "soft_delete", "document", json_text({"ids": ids})))
            for row in affected:
                self._mark_compat_dirty(
                    con, iid, f"daily:{row['observed_date']}:{row['category']}")
        return cur.rowcount

    def upsert_entity(self, folder: str, item: dict, chain_name: str = "") -> str:
        name = str(item.get("name") or "").strip()
        kind = str(item.get("type") or item.get("kind") or "company")
        country = str(item.get("country") or "")
        if not name:
            raise ValueError("实体名称不能为空")
        aliases = [str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()]
        external_ids = {str(key).casefold(): str(value).strip()
                        for key, value in (item.get("external_ids") or {}).items()
                        if str(value).strip()}
        candidates = [name, item.get("name_en", ""), *aliases]
        eid = ""
        with self.connection() as con:
            for scheme, value in external_ids.items():
                row = con.execute("SELECT entity_id FROM entity_identifiers WHERE scheme=? AND value=?",
                                  (scheme, value)).fetchone()
                if row:
                    eid = row["entity_id"]; break
            if not eid:
                for candidate in candidates:
                    normalized = normalized_name(candidate)
                    if not normalized:
                        continue
                    row = con.execute("""SELECT entity_id FROM entity_names
                        WHERE kind=? AND country=? AND normalized_name=?""",
                        (kind, country, normalized)).fetchone()
                    if row:
                        eid = row["entity_id"]; break
        eid = eid or stable_id("ent", kind, name, country)
        iid = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            role = str(item.get("role") or kind)
            chain = chain_name or str(item.get("chain") or "")
            valid_evidence: set[tuple[str, str]] = set()
            for reference in item.get("references") or []:
                if not isinstance(reference, dict):
                    continue
                relation = str(reference.get("relation") or "supports").casefold()
                if relation not in {"supports", "qualifies", "supports_role"}:
                    continue
                if reference.get("role") and str(reference["role"]) != role:
                    continue
                referenced_chain = reference.get("chain") or reference.get("chain_stage")
                if referenced_chain and str(referenced_chain) != chain:
                    continue
                document_id = str(reference.get("document_id") or "").strip()
                if document_id and con.execute("""SELECT 1 FROM industry_documents
                    WHERE industry_id=? AND document_id=? AND deleted_at IS NULL""",
                    (iid, document_id)).fetchone():
                    valid_evidence.add(("document", document_id))
                claim_id = str(reference.get("claim_id") or "").strip()
                if claim_id and con.execute("""SELECT 1 FROM claims
                    WHERE id=? AND industry_id=? AND status='accepted'""",
                    (claim_id, iid)).fetchone():
                    valid_evidence.add(("claim", claim_id))
                assertion_id = str(reference.get("assertion_id") or "").strip()
                if assertion_id:
                    assertion = con.execute("""SELECT a.claim_id
                        FROM agent_assertions a
                        JOIN agent_results r ON r.id=a.result_id
                        JOIN claims c ON c.id=a.claim_id
                        WHERE a.id=? AND r.industry_id=? AND a.status='accepted'
                        AND c.industry_id=? AND c.status='accepted'""",
                        (assertion_id, iid, iid)).fetchone()
                    if assertion:
                        valid_evidence.add(("assertion", assertion_id))
            evidence_count = len(valid_evidence)
            derived_status = "accepted" if evidence_count else "candidate"
            stored_metadata = {
                **item,
                "requested_status": item.get("status", "candidate"),
                "derived_status": derived_status,
                "derived_evidence_count": evidence_count,
            }
            con.execute("""INSERT INTO entities
                (id,kind,canonical_name,name_en,country,external_ids_json,metadata_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                canonical_name=entities.canonical_name,
                name_en=CASE WHEN entities.name_en='' THEN excluded.name_en ELSE entities.name_en END,
                country=excluded.country,external_ids_json=excluded.external_ids_json,
                metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                (eid, kind, name, item.get("name_en", ""), country,
                 json_text(item.get("external_ids", {})),
                 json_text({**stored_metadata, "legacy_id": item.get("id", "")}), now, now))
            con.execute("""INSERT INTO industry_entities
                (industry_id,entity_id,role,chain_name,status,confidence,metadata_json)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(industry_id,entity_id,role,chain_name)
                DO UPDATE SET status=excluded.status,confidence=excluded.confidence,
                metadata_json=excluded.metadata_json""",
                (iid, eid, role, chain, derived_status,
                 item.get("confidence"), json_text(stored_metadata)))
            for alias in aliases:
                con.execute("INSERT OR IGNORE INTO entity_aliases(entity_id,alias) VALUES(?,?)",
                            (eid, alias))
            for candidate, name_type in ((name, "canonical"),
                                         (item.get("name_en", ""), "english"),
                                         *((alias, "alias") for alias in aliases)):
                normalized = normalized_name(candidate)
                if normalized:
                    con.execute("""INSERT OR IGNORE INTO entity_names
                        (entity_id,kind,country,normalized_name,name_type) VALUES(?,?,?,?,?)""",
                        (eid, kind, country, normalized, name_type))
            for scheme, value in external_ids.items():
                con.execute("""INSERT OR IGNORE INTO entity_identifiers
                    (entity_id,scheme,value) VALUES(?,?,?)""", (eid, scheme, value))
            if chain:
                chain_id = stable_id("chn", iid, chain)
                con.execute("""INSERT OR IGNORE INTO value_chain_nodes
                    (id,industry_id,name,created_at,updated_at) VALUES(?,?,?,?,?)""",
                    (chain_id, iid, chain, now, now))
                role_id = stable_id("ecr", iid, eid, chain_id, role,
                                    item.get("valid_from", ""))
                con.execute("""INSERT INTO entity_chain_roles
                    (id,industry_id,entity_id,chain_node_id,role,valid_from,valid_to,status,
                     confidence,evidence_count,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET valid_to=excluded.valid_to,
                    status=excluded.status,confidence=excluded.confidence,
                    evidence_count=excluded.evidence_count,metadata_json=excluded.metadata_json""",
                    (role_id, iid, eid, chain_id, role, item.get("valid_from") or None,
                     item.get("valid_to") or None, derived_status,
                     item.get("confidence"), evidence_count, json_text(stored_metadata)))
                self._mark_compat_dirty(con, iid, "chains")
            if kind != "supply_chain_activity":
                self._mark_compat_dirty(con, iid, "entities")
        return eid

    def upsert_relation(self, folder: str, src_id: str, predicate: str, dst_id: str,
                        *, valid_from: str = "", valid_to: str = "",
                        confidence: float | None = None, metadata: dict | None = None,
                        references: list[dict] | None = None) -> str:
        """Admit an evidenced relation or route it to the review queue.

        A caller-controlled status is intentionally not accepted.  Canonical
        relation rows require a current-industry Document or an accepted
        current-industry Claim/Assertion; otherwise only a candidate is saved.
        """
        iid = self.industry_id(folder)
        rid = stable_id("rel", iid, src_id, predicate, dst_id, valid_from)
        metadata = dict(metadata or {})
        requested_references = references if references is not None else metadata.get(
            "references", [])
        with self.transaction() as con:
            membership_count = con.execute("""SELECT COUNT(DISTINCT entity_id)
                FROM industry_entities WHERE industry_id=? AND entity_id IN (?,?)""",
                (iid, src_id, dst_id)).fetchone()[0]
            if membership_count != 2:
                raise ValueError("relation endpoints must belong to the current industry")
            valid_evidence: list[dict] = []
            for item in requested_references if isinstance(requested_references, list) else []:
                if not isinstance(item, dict):
                    continue
                document_id = str(item.get("document_id") or "").strip()
                if document_id and con.execute("""SELECT 1 FROM industry_documents
                        WHERE industry_id=? AND document_id=? AND deleted_at IS NULL""",
                        (iid, document_id)).fetchone():
                    valid_evidence.append({"kind": "document", "id": document_id})
                    continue
                claim_id = str(item.get("claim_id") or "").strip()
                if claim_id and con.execute("""SELECT 1 FROM claims WHERE id=?
                        AND industry_id=? AND status='accepted' AND superseded_at IS NULL""",
                        (claim_id, iid)).fetchone():
                    valid_evidence.append({"kind": "claim", "id": claim_id})
                    continue
                assertion_id = str(item.get("assertion_id") or "").strip()
                if assertion_id and con.execute("""SELECT 1 FROM agent_assertions a
                        JOIN agent_results r ON r.id=a.result_id JOIN claims c ON c.id=a.claim_id
                        WHERE a.id=? AND r.industry_id=? AND a.status='accepted'
                        AND c.industry_id=? AND c.status='accepted' AND c.superseded_at IS NULL""",
                        (assertion_id, iid, iid)).fetchone():
                    valid_evidence.append({"kind": "assertion", "id": assertion_id})
            if not valid_evidence:
                now = utc_now()
                row = con.execute("""SELECT id FROM coverage_rounds WHERE industry_id=?
                    AND status='planned' AND stopping_reason='relation admission review'
                    ORDER BY round_no DESC LIMIT 1""", (iid,)).fetchone()
                if row:
                    round_id = row["id"]
                else:
                    round_no = int(con.execute("""SELECT COALESCE(MAX(round_no),0)+1
                        FROM coverage_rounds WHERE industry_id=?""", (iid,)).fetchone()[0])
                    round_id = stable_id("cvr", iid, round_no)
                    con.execute("""INSERT INTO coverage_rounds
                        (id,industry_id,round_no,status,frontier_json,outcome_json,log_json,
                         stopping_reason,created_at,updated_at)
                        VALUES(?,?,?,'planned','[]','{}','[]','relation admission review',?,?)""",
                        (round_id, iid, round_no, now, now))
                payload = {"source": src_id, "target": dst_id, "relation": predicate,
                           "valid_from": valid_from, "valid_to": valid_to,
                           "confidence": confidence, **metadata}
                canonical_key = stable_id("relation-candidate-key", src_id, predicate, dst_id)
                candidate_id = stable_id("rlc", iid, canonical_key, "relation-admission")
                con.execute("""INSERT INTO relation_candidates
                    (id,industry_id,round_id,query_id,cell_id,canonical_key,payload_json,
                     document_id,assertion_id,status,status_reason,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,NULL,NULL,'manual_review',?,?,?)
                    ON CONFLICT(industry_id,canonical_key,cell_id) DO UPDATE SET
                    payload_json=CASE WHEN relation_candidates.status IN
                        ('candidate','manual_review') THEN excluded.payload_json
                        ELSE relation_candidates.payload_json END,
                    updated_at=excluded.updated_at""",
                    (candidate_id, iid, round_id, None, "relation-admission", canonical_key,
                     json_text(payload), "canonical relation requires evidence", now, now))
                return candidate_id
            stored_metadata = {**metadata, "evidence": valid_evidence,
                               "derived_evidence_count": len(valid_evidence)}
            con.execute("""INSERT INTO relations
                (id,src_entity_id,predicate,dst_entity_id,industry_id,valid_from,valid_to,
                 confidence,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET valid_to=excluded.valid_to,
                confidence=excluded.confidence,metadata_json=excluded.metadata_json""",
                (rid, src_id, predicate, dst_id, iid, valid_from or None, valid_to or None,
                 confidence, json_text(stored_metadata)))
        return rid

    def upsert_claim(self, folder: str, predicate: str, object_value,
                     *, subject_id: str | None = None, qualifiers: dict | None = None,
                     valid_from: str = "", valid_to: str = "",
                     status: str = "candidate") -> str:
        iid = self.industry_id(folder)
        object_json = json_text(object_value)
        qualifier_json = json_text(qualifiers or {})
        cid = stable_id("clm", iid, subject_id, predicate, object_json,
                        qualifier_json, valid_from, valid_to)
        now = utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO claims
                (id,industry_id,subject_id,predicate,object_json,qualifiers_json,
                 valid_from,valid_to,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,updated_at=excluded.updated_at,superseded_at=NULL""",
                (cid, iid, subject_id, predicate, object_json, qualifier_json,
                 valid_from or None, valid_to or None, status, now, now))
        return cid

    def add_evidence(self, claim_id: str, relation: str, *, document_id: str | None = None,
                     excerpt: str = "", publisher_cluster: str = "",
                     extraction_method: str = "", confidence: float | None = None) -> str:
        if relation not in {"supports", "contradicts", "qualifies"}:
            raise ValueError("evidence relation 必须是 supports/contradicts/qualifies")
        eid = stable_id("evd", claim_id, document_id, relation, excerpt)
        with self.transaction() as con:
            con.execute("""INSERT INTO evidence
                (id,claim_id,document_id,relation,excerpt,publisher_cluster,
                 extraction_method,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(claim_id,document_id,relation) DO UPDATE SET
                excerpt=excluded.excerpt,publisher_cluster=excluded.publisher_cluster,
                extraction_method=excluded.extraction_method,confidence=excluded.confidence""",
                (eid, claim_id, document_id, relation, excerpt, publisher_cluster,
                 extraction_method, confidence, utc_now()))
        return eid

    def save_claim_bundles(self, folder: str, bundles: list[dict],
                           *, replace_predicate: str = "") -> int:
        """Atomically persist extracted claims and all supporting evidence."""
        iid = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            if replace_predicate:
                con.execute("""UPDATE claims SET superseded_at=? WHERE industry_id=?
                    AND predicate=? AND superseded_at IS NULL""",
                    (now, iid, replace_predicate))
            for bundle in bundles:
                predicate = bundle["predicate"]
                object_json = json_text(bundle.get("object"))
                qualifiers_json = json_text(bundle.get("qualifiers", {}))
                subject_id = bundle.get("subject_id")
                valid_from, valid_to = bundle.get("valid_from", ""), bundle.get("valid_to", "")
                claim_id = stable_id("clm", iid, subject_id, predicate, object_json,
                                     qualifiers_json, valid_from, valid_to)
                con.execute("""INSERT INTO claims
                    (id,industry_id,subject_id,predicate,object_json,qualifiers_json,
                     valid_from,valid_to,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,updated_at=excluded.updated_at,superseded_at=NULL""",
                    (claim_id, iid, subject_id, predicate, object_json, qualifiers_json,
                     valid_from or None, valid_to or None,
                     bundle.get("status", "candidate"), now, now))
                for evidence in bundle.get("evidence", []):
                    relation = evidence.get("relation", "supports")
                    if relation not in {"supports", "contradicts", "qualifies"}:
                        raise ValueError("evidence relation 必须是 supports/contradicts/qualifies")
                    evidence_id = stable_id(
                        "evd", claim_id, evidence.get("document_id"), relation,
                        evidence.get("excerpt", ""))
                    con.execute("""INSERT INTO evidence
                        (id,claim_id,document_id,relation,excerpt,publisher_cluster,
                         extraction_method,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(claim_id,document_id,relation) DO UPDATE SET
                        excerpt=excluded.excerpt,publisher_cluster=excluded.publisher_cluster,
                        extraction_method=excluded.extraction_method,
                        confidence=excluded.confidence""",
                        (evidence_id, claim_id, evidence.get("document_id"), relation,
                         evidence.get("excerpt", ""), evidence.get("publisher_cluster", ""),
                         evidence.get("extraction_method", ""), evidence.get("confidence"), now))
        return len(bundles)

    def upsert_event(self, folder: str, item: dict) -> str:
        iid = self.industry_id(folder)
        title = str(item.get("title") or "").strip()
        event_type = str(item.get("event_type") or item.get("etype") or "industry")
        occurred = str(item.get("occurred_at") or item.get("date") or "")
        if not title:
            raise ValueError("事件标题不能为空")
        eid = stable_id("evt", iid, event_type, occurred, title)
        with self.transaction() as con:
            con.execute("""INSERT INTO events
                (id,industry_id,title,event_type,description,occurred_at,observed_at,
                 importance,status,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET description=excluded.description,
                importance=excluded.importance,status=excluded.status,
                metadata_json=excluded.metadata_json""",
                (eid, iid, title, event_type, item.get("description", ""), occurred or None,
                 item.get("observed_at") or utc_now(),
                 max(1, min(5, int(item.get("importance", 3)))),
                 item.get("status", "candidate"), json_text(item)))
        return eid

    def graph(self, folder: str, limit: int = 500) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            edge_rows = con.execute("""SELECT r.*,s.canonical_name AS src_name,
                d.canonical_name AS dst_name FROM relations r
                JOIN entities s ON s.id=r.src_entity_id
                JOIN entities d ON d.id=r.dst_entity_id
                WHERE r.industry_id=? LIMIT ?""", (iid, limit)).fetchall()
        edges = [dict(row) for row in edge_rows]
        node_ids = {edge[key] for edge in edges for key in ("src_entity_id", "dst_entity_id")}
        if not node_ids:
            return {"nodes": [], "edges": []}
        marks = ",".join("?" for _ in node_ids)
        with self.connection() as con:
            nodes = [dict(row) for row in con.execute(
                f"SELECT * FROM entities WHERE id IN ({marks})", list(node_ids))]
        return {"nodes": nodes, "edges": edges}

    def graph_neighbors(self, folder: str, name: str, depth: int = 1) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            start = con.execute("""SELECT DISTINCT e.* FROM entities e
                JOIN industry_entities x ON x.entity_id=e.id
                LEFT JOIN entity_aliases a ON a.entity_id=e.id
                WHERE x.industry_id=? AND (e.canonical_name LIKE ? OR e.name_en LIKE ?
                OR a.alias LIKE ?) LIMIT 1""",
                (iid, f"%{name}%", f"%{name}%", f"%{name}%")).fetchone()
            if not start:
                return {"nodes": [], "edges": []}
            nodes = {start["id"]: dict(start)}
            edges, frontier = {}, {start["id"]}
            for _ in range(max(1, depth)):
                if not frontier:
                    break
                marks = ",".join("?" for _ in frontier)
                rows = con.execute(f"""SELECT * FROM relations WHERE industry_id=? AND
                    (src_entity_id IN ({marks}) OR dst_entity_id IN ({marks}))""",
                    [iid, *frontier, *frontier]).fetchall()
                next_frontier = set()
                for row in rows:
                    edge = dict(row); edges[edge["id"]] = edge
                    for entity_id in (edge["src_entity_id"], edge["dst_entity_id"]):
                        if entity_id not in nodes:
                            entity = con.execute("SELECT * FROM entities WHERE id=?",
                                                 (entity_id,)).fetchone()
                            if entity:
                                nodes[entity_id] = dict(entity); next_frontier.add(entity_id)
                frontier = next_frontier
        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    def knowledge_stats(self, folder: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            scalar = lambda sql: con.execute(sql, (iid,)).fetchone()[0]
            return {
                "sources": scalar(
                    "SELECT COUNT(*) FROM industry_sources "
                    "WHERE industry_id=? AND deleted_at IS NULL"),
                "documents": scalar(
                    "SELECT COUNT(*) FROM industry_documents "
                    "WHERE industry_id=? AND deleted_at IS NULL"),
                "entities": scalar(
                    "SELECT COUNT(DISTINCT entity_id) FROM industry_entities "
                    "WHERE industry_id=? AND status!='deleted'"),
                "candidate_entities": scalar(
                    "SELECT COUNT(DISTINCT entity_id) FROM industry_entities "
                    "WHERE industry_id=? AND status='candidate'"),
                "relations": scalar("SELECT COUNT(*) FROM relations WHERE industry_id=?"),
                "claims": scalar("SELECT COUNT(*) FROM claims WHERE industry_id=? AND superseded_at IS NULL"),
                "verified_claims": scalar(
                    "SELECT COUNT(*) FROM claims WHERE industry_id=? "
                    "AND superseded_at IS NULL "
                    "AND status IN ('accepted','verified','corroborated')"),
                "evidence": scalar(
                    "SELECT COUNT(*) FROM evidence e JOIN claims c ON c.id=e.claim_id "
                    "WHERE c.industry_id=? AND c.superseded_at IS NULL"),
                "events": scalar("SELECT COUNT(*) FROM events WHERE industry_id=?"),
                "chain_nodes": scalar(
                    "SELECT COUNT(*) FROM value_chain_nodes WHERE industry_id=?"),
                "empty_chain_nodes": scalar("""SELECT COUNT(*) FROM value_chain_nodes n
                    WHERE n.industry_id=? AND NOT EXISTS
                    (SELECT 1 FROM entity_chain_roles r WHERE r.chain_node_id=n.id
                     AND r.valid_to IS NULL)"""),
            }

    def list_compat_entities(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT e.*,x.role,x.chain_name,x.status,x.confidence,
                x.metadata_json AS link_json FROM industry_entities x
                JOIN entities e ON e.id=x.entity_id
                WHERE x.industry_id=? AND x.status!='deleted'
                AND e.kind!='supply_chain_activity'
                ORDER BY e.canonical_name,x.chain_name""", (iid,)).fetchall()
        out = []
        for row in rows:
            item = json_value(row["metadata_json"], {})
            item.update(json_value(row["link_json"], {}))
            item.update({"id": row["id"], "name": row["canonical_name"],
                         "name_en": row["name_en"] or "", "type": row["kind"],
                         "country": row["country"] or "", "role": row["role"] or "",
                         "chain": row["chain_name"] or "", "status": row["status"],
                         "confidence": row["confidence"]})
            out.append(item)
        return out

    def delete_entity(self, folder: str, entity_id: str) -> bool:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            cur = con.execute("""UPDATE industry_entities SET status='deleted'
                WHERE industry_id=? AND entity_id=? AND status!='deleted'""", (iid, entity_id))
            if cur.rowcount:
                self._mark_compat_dirty(con, iid, "entities")
        return cur.rowcount > 0

    def clear_industry_entities(self, folder: str) -> int:
        """Soft-delete generated memberships and remove their industry relations."""
        iid = self.industry_id(folder)
        with self.transaction() as con:
            con.execute("DELETE FROM relations WHERE industry_id=?", (iid,))
            con.execute("DELETE FROM entity_chain_roles WHERE industry_id=?", (iid,))
            cur = con.execute("""UPDATE industry_entities SET status='deleted'
                WHERE industry_id=? AND status!='deleted'""", (iid,))
            self._mark_compat_dirty(con, iid, "entities")
        return cur.rowcount

    def start_run(self, folder: str, kind: str, stage: str = "queued") -> str:
        iid = self.industry_id(folder)
        now = utc_now()
        rid = stable_id("run", folder, kind, now, uuid.uuid4().hex)
        with self.transaction() as con:
            con.execute("""INSERT INTO runs(id,industry_id,kind,stage,status,started_at,updated_at)
                VALUES(?,?,?,?,?,?,?)""", (rid, iid, kind, stage, "running", now, now))
        return rid

    def acquire_lock(self, lock_key: str, owner: str, ttl_seconds: int = 21600) -> None:
        now = utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(
            timespec="seconds")
        try:
            with self.transaction() as con:
                con.execute("DELETE FROM locks WHERE expires_at<=?", (now,))
                con.execute("INSERT INTO locks(lock_key,owner,acquired_at,expires_at) VALUES(?,?,?,?)",
                            (lock_key, owner, now, expires))
        except sqlite3.IntegrityError as exc:
            with self.connection() as con:
                row = con.execute("SELECT owner,acquired_at FROM locks WHERE lock_key=?",
                                  (lock_key,)).fetchone()
            detail = f"，占用者={row['owner']}，开始于={row['acquired_at']}" if row else ""
            raise RuntimeError(f"行业任务正在运行，请等待或取消原任务{detail}") from exc

    def release_lock(self, lock_key: str, owner: str) -> None:
        with self.transaction() as con:
            con.execute("DELETE FROM locks WHERE lock_key=? AND owner=?", (lock_key, owner))

    def update_run(self, run_id: str, *, stage: str | None = None,
                   status: str | None = None, checkpoint: dict | None = None,
                   metrics: dict | None = None, error: Exception | None = None) -> None:
        now = utc_now()
        fields = ["updated_at=?"]; values: list[object] = [now]
        for name, value in (("stage", stage), ("status", status)):
            if value is not None:
                fields.append(f"{name}=?"); values.append(value)
        if checkpoint is not None:
            fields.append("checkpoint_json=?"); values.append(json_text(checkpoint))
        if metrics is not None:
            fields.append("metrics_json=?"); values.append(json_text(metrics))
        if error is not None:
            fields.extend(["error_code=?", "error_message=?"])
            values.extend([type(error).__name__, str(error)])
        if status in {"completed", "failed", "cancelled", "partial", "unresolved"}:
            fields.append("finished_at=?"); values.append(now)
        values.append(run_id)
        with self.transaction() as con:
            con.execute(f"UPDATE runs SET {','.join(fields)} WHERE id=?", values)

    def finish_run_if_running(self, run_id: str, status: str = "completed") -> None:
        now = utc_now()
        with self.transaction() as con:
            con.execute("""UPDATE runs SET status=?,finished_at=?,updated_at=?
                WHERE id=? AND status='running'""", (status, now, now, run_id))
