"""Data models and normalization schema for JobCare Job Scout skill."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class VerificationStatus(Enum):
    """Verification status for job listings."""

    API_CONFIRMED = "api_confirmed"
    BROWSER_CONFIRMED = "browser_confirmed"
    UNVERIFIED = "unverified"
    CLOSED = "closed"
    BLOCKED = "blocked"


class AtsProvider(Enum):
    """ATS provider enum."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"


@dataclass
class UserProfile:
    """User profile for personalized job matching."""

    user_id: str
    education: str = ""
    graduation_year: Optional[int] = None
    technical_skills: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    work_experience: list[str] = field(default_factory=list)
    preferred_roles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    remote_preference: bool = False
    employment_type: Optional[str] = None
    resume_file: str = ""
    created_at: str = ""
    updated_at: str = ""
    reviewed_at: Optional[str] = None


@dataclass
class ResumeData:
    """Parsed resume data."""

    user_id: str
    skills: list[str] = field(default_factory=list)
    education: str = ""
    graduation_year: Optional[int] = None
    projects: list[str] = field(default_factory=list)
    work_experience: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    parsed_at: str = ""
    file_path: str = ""


@dataclass
class MatchResult:
    """Result of job matching."""

    job: JobRecord
    match_score: float
    matching_skills: list[str]
    missing_skills: list[str]
    eligibility_status: str
    explanation: list[str]
    application_url: str
    deterministic_score: float = 0.0
    semantic_score: float = 0.0
    model_version: str = ""
    algorithm_version: str = ""


@dataclass
class MatchHistory:
    """Record of a job match for a user."""

    user_id: str
    job_provider: str
    original_job_id: str
    match_score: float
    eligibility_status: str
    explanation: list[str]
    matched_at: str = ""
    semantic_score: Optional[float] = None
    model_version: str = ""
    algorithm_version: str = ""


@dataclass
class JobRecord:
    """Normalized job record from any ATS source."""

    # Stable unique key: provider + original job id
    provider: AtsProvider
    original_job_id: str
    company: str
    title: str
    location: str
    experience: Optional[str] = None
    skills: list[str] = field(default_factory=list)
    salary: Optional[str] = None
    employment_type: Optional[str] = None

    # Source URLs (individual job URL preferred over source page)
    job_url: str = ""
    application_url: str = ""

    # Source API URL for this job
    source_api_url: str = ""

    # Verification
    verification_status: VerificationStatus = VerificationStatus.API_CONFIRMED
    verification_evidence: str = ""
    verified_at: str = ""

    # Metadata
    last_checked_at: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Normalize empty strings to None
        if self.salary == "":
            self.salary = None
        if self.experience == "":
            self.experience = None
        if self.employment_type == "":
            self.employment_type = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        return {
            "provider": self.provider.value,
            "original_job_id": self.original_job_id,
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "experience": self.experience,
            "skills": self.skills,
            "salary": self.salary,
            "employment_type": self.employment_type,
            "job_url": self.job_url,
            "application_url": self.application_url,
            "source_api_url": self.source_api_url,
            "verification_status": self.verification_status.value,
            "verification_evidence": self.verification_evidence,
            "verified_at": self.verified_at,
            "last_checked_at": self.last_checked_at,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRecord:
        """Create JobRecord from dictionary."""
        return cls(
            provider=AtsProvider(data.get("provider", AtsProvider.GREENHOUSE.value)),
            original_job_id=data.get("original_job_id", ""),
            company=data.get("company", ""),
            title=data.get("title", ""),
            location=data.get("location", ""),
            experience=data.get("experience"),
            skills=data.get("skills", []),
            salary=data.get("salary"),
            employment_type=data.get("employment_type"),
            job_url=data.get("job_url", ""),
            application_url=data.get("application_url", ""),
            source_api_url=data.get("source_api_url", ""),
            verification_status=VerificationStatus(
                data.get("verification_status", VerificationStatus.API_CONFIRMED.value)
            ),
            verification_evidence=data.get("verification_evidence", ""),
            verified_at=data.get("verified_at", ""),
            last_checked_at=data.get("last_checked_at", ""),
            raw_data=data.get("raw_data", {}),
        )


@dataclass
class Employer:
    """Employer entry in the registry."""

    provider: AtsProvider
    board_id: str  # e.g., company slug for Greenhouse, site for Lever, board name for Ashby
    careers_url: str
    enabled: bool = True
    last_successful_sync: Optional[str] = None
    created_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "board_id": self.board_id,
            "careers_url": self.careers_url,
            "enabled": self.enabled,
            "last_successful_sync": self.last_successful_sync,
            "created_at": self.created_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Employer:
        return cls(
            provider=AtsProvider(data.get("provider", AtsProvider.GREENHOUSE.value)),
            board_id=data.get("board_id", ""),
            careers_url=data.get("careers_url", ""),
            enabled=data.get("enabled", True),
            last_successful_sync=data.get("last_successful_sync"),
            created_at=data.get("created_at", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class SearchRun:
    """Record of a sync/search run."""

    run_id: str
    search_at: str = ""
    filters_applied: dict[str, Any] = field(default_factory=dict)
    total_received: int = 0
    total_fetched: int = 0
    total_filtered: int = 0
    result_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    skipped_employers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "search_at": self.search_at,
            "filters_applied": self.filters_applied,
            "total_received": self.total_received,
            "total_fetched": self.total_fetched,
            "total_filtered": self.total_filtered,
            "result_ids": self.result_ids,
            "errors": self.errors,
            "skipped_employers": self.skipped_employers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchRun:
        return cls(
            run_id=data.get("run_id", ""),
            search_at=data.get("search_at", ""),
            filters_applied=data.get("filters_applied", {}),
            total_received=data.get("total_received", 0),
            total_fetched=data.get("total_fetched", 0),
            total_filtered=data.get("total_filtered", 0),
            result_ids=data.get("result_ids", []),
            errors=data.get("errors", []),
            skipped_employers=data.get("skipped_employers", []),
        )


@dataclass
class Filter:
    """User-configurable career profile filters."""

    desired_roles: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_preference: bool = False
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    skills: list[str] = field(default_factory=list)
    employment_type: Optional[str] = None
