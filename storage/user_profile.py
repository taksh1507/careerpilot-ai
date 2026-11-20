"""User profile storage and management."""

from __future__ import annotations

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from models.schemas import UserProfile, ResumeData, MatchHistory


class UserProfileStorage:
    """Storage for user profiles and match history."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(Path.home() / ".jobcare" / "jobcare.db")
        self.db_path = db_path
        # Ensure the parent directory exists (Windows-safe)
        path = Path(self.db_path)
        if path.parent and str(path.parent) != "":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_schema(self):
        """Create tables if they don't exist."""
        conn = self._connect()
        conn.executescript(
            """
            -- User profiles
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                education TEXT DEFAULT '',
                graduation_year INTEGER,
                skills TEXT DEFAULT '',
                projects TEXT DEFAULT '',
                work_experience TEXT DEFAULT '',
                preferred_roles TEXT DEFAULT '',
                preferred_locations TEXT DEFAULT '',
                remote_preference INTEGER DEFAULT 0,
                employment_type TEXT,
                resume_file TEXT DEFAULT '',
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- Resumes
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                skills TEXT DEFAULT '',
                education TEXT DEFAULT '',
                graduation_year INTEGER,
                projects TEXT DEFAULT '',
                work_experience TEXT DEFAULT '',
                certifications TEXT DEFAULT '',
                parsed_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
            );

            -- Match history
            CREATE TABLE IF NOT EXISTS match_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                job_provider TEXT NOT NULL,
                original_job_id TEXT NOT NULL,
                match_score REAL NOT NULL,
                eligibility_status TEXT NOT NULL,
                explanation TEXT DEFAULT '',
                semantic_score REAL,
                model_version TEXT DEFAULT '',
                algorithm_version TEXT DEFAULT '',
                matched_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, job_provider, original_job_id)
            );
            """
        )
        profile_columns = {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)")}
        if "reviewed_at" not in profile_columns:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN reviewed_at TEXT")
        match_columns = {row[1] for row in conn.execute("PRAGMA table_info(match_history)")}
        for name, declaration in (
            ("semantic_score", "REAL"),
            ("model_version", "TEXT NOT NULL DEFAULT ''"),
            ("algorithm_version", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in match_columns:
                conn.execute(f"ALTER TABLE match_history ADD COLUMN {name} {declaration}")
        conn.commit()

    # ---- User profiles ----

    def create_profile(self, profile: UserProfile) -> UserProfile:
        """Create a new user profile."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor = conn.execute(
            """
            INSERT INTO user_profiles
                (user_id, education, graduation_year, skills, projects, work_experience,
                 preferred_roles, preferred_locations, remote_preference, employment_type,
                 resume_file, reviewed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.user_id,
                profile.education,
                profile.graduation_year,
                ",".join(profile.technical_skills) if profile.technical_skills else "",
                ",".join(profile.projects) if profile.projects else "",
                ",".join(profile.work_experience) if profile.work_experience else "",
                ",".join(profile.preferred_roles) if profile.preferred_roles else "",
                ",".join(profile.preferred_locations) if profile.preferred_locations else "",
                1 if profile.remote_preference else 0,
                profile.employment_type or "",
                profile.resume_file,
                None,  # Approval is granted only by mark_profile_reviewed after explicit review.
                now,
                now,
            ),
        )
        conn.commit()
        return self.get_profile(profile.user_id)

    def update_profile(self, profile: UserProfile) -> UserProfile:
        """Update an existing user profile."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            UPDATE user_profiles
            SET education = ?,
                graduation_year = ?,
                skills = ?,
                projects = ?,
                work_experience = ?,
                preferred_roles = ?,
                preferred_locations = ?,
                remote_preference = ?,
                employment_type = ?,
                resume_file = ?,
                reviewed_at = NULL,
                updated_at = ?
            WHERE user_id = ?
            """,
            (
                profile.education,
                profile.graduation_year,
                ",".join(profile.technical_skills) if profile.technical_skills else "",
                ",".join(profile.projects) if profile.projects else "",
                ",".join(profile.work_experience) if profile.work_experience else "",
                ",".join(profile.preferred_roles) if profile.preferred_roles else "",
                ",".join(profile.preferred_locations) if profile.preferred_locations else "",
                1 if profile.remote_preference else 0,
                profile.employment_type or "",
                profile.resume_file,
                now,
                profile.user_id,
            ),
        )
        conn.commit()
        return self.get_profile(profile.user_id)

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get a user profile by user_id."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_profile(row)

    def list_profiles(self) -> list[UserProfile]:
        """List all user profiles."""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM user_profiles ORDER BY user_id").fetchall()
        return [self._row_to_profile(r) for r in rows]

    def delete_profile(self, user_id: str) -> bool:
        """Delete a user profile and all associated data."""
        conn = self._connect()
        cursor = conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

    def _row_to_profile(self, row: sqlite3.Row) -> UserProfile:
        return UserProfile(
            user_id=row["user_id"],
            education=row["education"],
            graduation_year=row["graduation_year"],
            technical_skills=[s for s in row["skills"].split(",") if s] if row["skills"] else [],
            projects=[p for p in row["projects"].split(",") if p] if row["projects"] else [],
            work_experience=[e for e in row["work_experience"].split(",") if e] if row["work_experience"] else [],
            preferred_roles=[r for r in row["preferred_roles"].split(",") if r] if row["preferred_roles"] else [],
            preferred_locations=[l for l in row["preferred_locations"].split(",") if l] if row["preferred_locations"] else [],
            remote_preference=bool(row["remote_preference"]),
            employment_type=row["employment_type"] or None,
            resume_file=row["resume_file"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            reviewed_at=row["reviewed_at"],
        )

    def mark_profile_reviewed(self, user_id: str) -> Optional[UserProfile]:
        """Record explicit user confirmation of the current saved profile."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor = conn.execute(
            "UPDATE user_profiles SET reviewed_at = ?, updated_at = ? WHERE user_id = ?",
            (now, now, user_id),
        )
        conn.commit()
        return self.get_profile(user_id) if cursor.rowcount else None

    # ---- Resumes ----

    def save_resume(self, resume: ResumeData) -> ResumeData:
        """Save a parsed resume."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            INSERT INTO resumes
                (user_id, file_path, skills, education, graduation_year, projects,
                 work_experience, certifications, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resume.user_id,
                resume.file_path,
                ",".join(resume.skills) if resume.skills else "",
                resume.education,
                resume.graduation_year,
                ",".join(resume.projects) if resume.projects else "",
                ",".join(resume.work_experience) if resume.work_experience else "",
                ",".join(resume.certifications) if resume.certifications else "",
                now,
            ),
        )
        conn.commit()
        return resume

    def get_resume(self, user_id: str) -> Optional[ResumeData]:
        """Get the most recently parsed resume for a user."""
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM resumes WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_resume(row)

    def _row_to_resume(self, row: sqlite3.Row) -> ResumeData:
        return ResumeData(
            user_id=row["user_id"],
            skills=[s for s in row["skills"].split(",") if s] if row["skills"] else [],
            education=row["education"],
            graduation_year=row["graduation_year"],
            projects=[p for p in row["projects"].split(",") if p] if row["projects"] else [],
            work_experience=[e for e in row["work_experience"].split(",") if e] if row["work_experience"] else [],
            certifications=[c for c in row["certifications"].split(",") if c] if row["certifications"] else [],
            parsed_at=row["parsed_at"],
            file_path=row["file_path"],
        )

    # ---- Match history ----

    def save_match(self, match: MatchHistory) -> MatchHistory:
        """Save a match result."""
        conn = self._connect()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            INSERT INTO match_history
                (user_id, job_provider, original_job_id, match_score, eligibility_status,
                 explanation, semantic_score, model_version, algorithm_version, matched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, job_provider, original_job_id) DO UPDATE SET
                match_score = excluded.match_score,
                eligibility_status = excluded.eligibility_status,
                explanation = excluded.explanation,
                semantic_score = excluded.semantic_score,
                model_version = excluded.model_version,
                algorithm_version = excluded.algorithm_version,
                matched_at = excluded.matched_at
            """,
            (
                match.user_id,
                match.job_provider,
                match.original_job_id,
                match.match_score,
                match.eligibility_status,
                json.dumps(match.explanation, ensure_ascii=False),
                match.semantic_score,
                match.model_version,
                match.algorithm_version,
                now,
            ),
        )
        conn.commit()
        return match

    def get_match_history(self, user_id: str) -> list[MatchHistory]:
        """Get all match history for a user."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM match_history WHERE user_id = ? ORDER BY matched_at DESC",
            (user_id,),
        ).fetchall()
        return [self._row_to_match(r) for r in rows]

    def get_match(self, user_id: str, provider: str, original_job_id: str) -> Optional[MatchHistory]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM match_history WHERE user_id=? AND job_provider=? AND original_job_id=?",
            (user_id, provider, original_job_id),
        ).fetchone()
        return self._row_to_match(row) if row else None

    def _row_to_match(self, row: sqlite3.Row) -> MatchHistory:
        try:
            explanation = json.loads(row["explanation"] or "[]")
            if not isinstance(explanation, list):
                explanation = [str(explanation)]
        except (ValueError, TypeError):
            explanation = [e for e in row["explanation"].split(",") if e] if row["explanation"] else []
        return MatchHistory(
            user_id=row["user_id"],
            job_provider=row["job_provider"],
            original_job_id=row["original_job_id"],
            match_score=row["match_score"],
            eligibility_status=row["eligibility_status"],
            explanation=explanation,
            matched_at=row["matched_at"],
            semantic_score=row["semantic_score"],
            model_version=row["model_version"],
            algorithm_version=row["algorithm_version"],
        )
