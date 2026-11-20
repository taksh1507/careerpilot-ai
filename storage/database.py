"""SQLite storage for employers, jobs, verification history, search runs, and preferences."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from models.schemas import Employer, JobRecord, SearchRun, AtsProvider, VerificationStatus

SCHEMA = """
-- Employers: configured ATS boards
CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    board_id TEXT NOT NULL,
    careers_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_successful_sync TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE(provider, board_id)
);

-- Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    original_job_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT DEFAULT '',
    experience TEXT,
    skills TEXT,
    salary TEXT,
    employment_type TEXT,
    job_url TEXT DEFAULT '',
    application_url TEXT DEFAULT '',
    source_api_url TEXT DEFAULT '',
    verification_status TEXT DEFAULT 'api_confirmed',
    verification_evidence TEXT DEFAULT '',
    verified_at TEXT DEFAULT '',
    last_checked_at TEXT DEFAULT '',
    raw_data TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, original_job_id),
    FOREIGN KEY (provider, original_job_id) REFERENCES job_verification_history(provider, original_job_id)
);

-- Job verification history (audit trail)
CREATE TABLE IF NOT EXISTS job_verification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    original_job_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence TEXT DEFAULT '',
    verified_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(provider, original_job_id, status)
);

-- Search runs (each sync)
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    search_at TEXT NOT NULL,
    filters_applied TEXT DEFAULT '',
    total_received INTEGER DEFAULT 0,
    total_fetched INTEGER DEFAULT 0,
    total_filtered INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- User preferences (career profile)
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

CREATE_TABLES_SQL = """
-- Employers
CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    board_id TEXT NOT NULL,
    careers_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_successful_sync TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE(provider, board_id)
);

-- Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    original_job_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT DEFAULT '',
    experience TEXT,
    skills TEXT,
    salary TEXT,
    employment_type TEXT,
    job_url TEXT DEFAULT '',
    application_url TEXT DEFAULT '',
    source_api_url TEXT DEFAULT '',
    verification_status TEXT DEFAULT 'api_confirmed',
    verification_evidence TEXT DEFAULT '',
    verified_at TEXT DEFAULT '',
    last_checked_at TEXT DEFAULT '',
    raw_data TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, original_job_id)
);

-- Job verification history
CREATE TABLE IF NOT EXISTS job_verification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    original_job_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence TEXT DEFAULT '',
    verified_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(provider, original_job_id, status)
);

-- Search runs
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    search_at TEXT NOT NULL,
    filters_applied TEXT DEFAULT '',
    total_received INTEGER DEFAULT 0,
    total_fetched INTEGER DEFAULT 0,
    total_filtered INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- User preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SQLiteStorage:
    """SQLite-backed persistent storage for the JobCare Job Scout."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path.home() / ".jobcare" / "jobcare.db")
        self.db_path = db_path
        # Ensure the parent directory exists (Windows-safe)
        path = Path(self.db_path)
        if path.parent and str(path.parent) != "":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(CREATE_TABLES_SQL)
            self._conn.commit()
        return self._conn

    def close(self):
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- Employers ----

    def add_employer(
        self,
        provider: str,
        board_id: str,
        careers_url: str,
        enabled: bool = True,
        notes: str = "",
    ) -> Employer:
        """Add or update an employer in the registry."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        provider_name = provider.lower()
        cursor = conn.execute(
            """
            INSERT INTO employers
                (provider, board_id, careers_url, enabled, last_successful_sync, created_at, updated_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, board_id) DO UPDATE SET
                enabled=excluded.enabled,
                last_successful_sync=excluded.last_successful_sync,
                notes=excluded.notes,
                updated_at=excluded.created_at
            """,
            (
                provider_name,
                board_id,
                careers_url,
                1 if enabled else 0,
                None,
                now,
                now,
                notes,
            ),
        )
        conn.commit()
        return self.get_employer(provider_name, board_id)

    def get_employer(self, provider: str, board_id: str) -> Optional[Employer]:
        """Get an employer by provider and board_id."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM employers WHERE provider=? AND board_id=?",
            (provider.lower(), board_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_employer(row)

    def list_employers(self, enabled_only: bool = True) -> list[Employer]:
        """List all employers, optionally only enabled ones."""
        conn = self._connect()
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM employers WHERE enabled=1 ORDER BY provider, board_id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM employers ORDER BY provider, board_id"
            ).fetchall()
        return [self._row_to_employer(r) for r in rows]

    def set_employer_enabled(
        self, provider: str, board_id: str, enabled: bool
    ) -> bool:
        """Enable or disable an employer."""
        conn = self._connect()
        conn.execute(
            "UPDATE employers SET enabled=? WHERE provider=? AND board_id=?",
            (1 if enabled else 0, provider.lower(), board_id),
        )
        conn.commit()
        return True

    def update_last_sync(self, provider: str, board_id: str, timestamp: str):
        """Update the last successful sync timestamp for an employer."""
        conn = self._connect()
        conn.execute(
            "UPDATE employers SET last_successful_sync=? WHERE provider=? AND board_id=?",
            (timestamp, provider.lower(), board_id),
        )
        conn.commit()

    # ---- Jobs ----

    def upsert_job(self, job: JobRecord) -> JobRecord:
        """Insert or update a job record."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Also insert verification history entry
        conn.execute(
            """
            INSERT INTO job_verification_history
                (provider, original_job_id, company, title, status, evidence, verified_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, original_job_id, status) DO UPDATE SET
                evidence=excluded.evidence,
                verified_at=excluded.verified_at,
                created_at=excluded.created_at
            """,
            (
                job.provider.value,
                job.original_job_id,
                job.company,
                job.title,
                job.verification_status.value,
                job.verification_evidence,
                job.verified_at,
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs
                (provider, original_job_id, company, title, location, experience,
                 skills, salary, employment_type, job_url, application_url,
                 source_api_url, verification_status, verification_evidence,
                 verified_at, last_checked_at, raw_data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.provider.value,
                job.original_job_id,
                job.company,
                job.title,
                job.location,
                job.experience,
                self._serialize_skills(job.skills),
                job.salary,
                job.employment_type,
                job.job_url,
                job.application_url,
                job.source_api_url,
                job.verification_status.value,
                job.verification_evidence,
                job.verified_at,
                job.last_checked_at,
                self._serialize_raw(job.raw_data),
                now,
                now,
            ),
        )
        conn.commit()
        return job

    def get_job(self, provider: str, original_job_id: str) -> Optional[JobRecord]:
        """Get a job by provider and original_job_id."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM jobs WHERE provider=? AND original_job_id=?",
            (provider.lower(), original_job_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def search_jobs(
        self,
        provider: Optional[str] = None,
        title_contains: Optional[str] = None,
        location_contains: Optional[str] = None,
        verification_status: Optional[str] = None,
        enabled: bool = True,
    ) -> list[JobRecord]:
        """Search jobs with optional filters."""
        conn = self._connect()
        query = "SELECT * FROM jobs WHERE 1=1"
        params = []
        if provider:
            query += " AND provider=?"
            params.append(provider.lower())
        if title_contains:
            query += " AND title LIKE ?"
            params.append(f"%{title_contains}%")
        if location_contains:
            query += " AND location LIKE ?"
            params.append(f"%{location_contains}%")
        if verification_status:
            query += " AND verification_status=?"
            params.append(verification_status.lower())
        if enabled:
            query += " AND EXISTS (SELECT 1 FROM employers WHERE employers.provider=jobs.provider AND employers.enabled=1)"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_verified_jobs(self) -> list[JobRecord]:
        """Get all jobs with verification_status = verified."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(verification_status)='verified'"
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_jobs_by_status(self, status: str) -> list[JobRecord]:
        """Get all jobs with a given verification_status."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(verification_status)=?",
            (status.lower(),),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_failed_sources(self) -> list[dict[str, Any]]:
        """Get records of failed sync sources."""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT provider, board_id, last_successful_sync, created_at
            FROM employers
            WHERE enabled=1 AND last_successful_sync IS NULL
            ORDER BY provider, board_id
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def save_search_run(self, run: SearchRun):
        """Save a search run record."""
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO search_runs
                (run_id, search_at, filters_applied, total_received, total_fetched, total_filtered, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.search_at,
                self._serialize_dict(run.filters_applied),
                run.total_received,
                run.total_fetched,
                run.total_filtered,
                run.search_at,
            ),
        )
        conn.commit()

    def get_search_run(self, run_id: str) -> Optional[SearchRun]:
        """Get a search run by run_id."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM search_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_search_run(row)

    def list_search_runs(self) -> list[SearchRun]:
        """List all search runs."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM search_runs ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_search_run(r) for r in rows]

    def save_preference(self, key: str, value: str):
        """Save a user preference."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            INSERT INTO user_preferences (key, value, updated_at, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, now, now),
        )
        conn.commit()

    def get_preference(self, key: str) -> Optional[str]:
        """Get a user preference by key."""
        conn = self._connect()
        row = conn.execute(
            "SELECT value FROM user_preferences WHERE key=?",
            (key,),
        ).fetchone()
        return row["value"] if row else None

    # ---- Private helpers ----

    def _row_to_employer(self, row: sqlite3.Row) -> Employer:
        return Employer(
            provider=row["provider"],
            board_id=row["board_id"],
            careers_url=row["careers_url"],
            enabled=bool(row["enabled"]),
            last_successful_sync=row["last_successful_sync"],
            created_at=row["created_at"],
            notes=row["notes"],
        )

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
            raw_data = self._deserialize_raw(row["raw_data"]) if row["raw_data"] else {}
            # Convert provider string to enum
            provider_val = row["provider"]
            if isinstance(provider_val, str):
                provider_val = AtsProvider(provider_val)
            # Convert verification_status string to enum
            verification_status = row["verification_status"]
            if isinstance(verification_status, str):
                verification_status = (
                    VerificationStatus.VERIFIED
                    if verification_status == "verified"
                    else VerificationStatus(verification_status)
                )
            return JobRecord(
                provider=provider_val,
                original_job_id=row["original_job_id"],
                company=row["company"],
                title=row["title"],
                location=row["location"],
                experience=row["experience"],
                skills=self._deserialize_skills(row["skills"]),
                salary=row["salary"],
                employment_type=row["employment_type"],
                job_url=row["job_url"],
                application_url=row["application_url"],
                source_api_url=row["source_api_url"],
                verification_status=verification_status,
                verification_evidence=row["verification_evidence"],
                verified_at=row["verified_at"],
                last_checked_at=row["last_checked_at"],
                raw_data=raw_data,
            )

    def _row_to_search_run(self, row: sqlite3.Row) -> SearchRun:
        return SearchRun(
            run_id=row["run_id"],
            search_at=row["search_at"],
            filters_applied=self._deserialize_dict(row["filters_applied"]) if row["filters_applied"] else {},
            total_received=row["total_received"],
            total_fetched=row["total_fetched"],
            total_filtered=row["total_filtered"],
            result_ids=[],
        )

    def _serialize_skills(self, skills: list[str]) -> str:
        """Serialize skills list to JSON string."""
        import json
        return json.dumps(skills) if skills else ""

    def _deserialize_skills(self, skills_str: str) -> list[str]:
        """Deserialize skills from JSON string."""
        if not skills_str:
            return []
        import json
        try:
            return json.loads(skills_str)
        except json.JSONDecodeError:
            return [skills_str]

    def _serialize_raw(self, raw: dict) -> str:
        """Serialize raw data dict to JSON string."""
        import json
        return json.dumps(raw) if raw else ""

    def _deserialize_raw(self, raw_str: str) -> dict:
        """Deserialize raw data from JSON string."""
        if not raw_str:
            return {}
        import json
        try:
            return json.loads(raw_str)
        except json.JSONDecodeError:
            return {}

    def _serialize_dict(self, d: dict) -> str:
        """Serialize dict to JSON string."""
        import json
        return json.dumps(d) if d else ""

    def _deserialize_dict(self, s: str) -> dict:
        """Deserialize dict from JSON string."""
        if not s:
            return {}
        import json
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return {}
