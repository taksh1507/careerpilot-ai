"""Verification logic for job listings."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from models.schemas import JobRecord, VerificationStatus

# Keywords that indicate a vacancy is closed (case-insensitive)
CLOSED_KEYWORDS = [
    "no longer accepting",
    "closed",
    "filled",
    "no longer accepting applications",
    "not accepting applications",
    "application closed",
    "position filled",
    "no longer available",
    "position no longer available",
    "submitted",
]

# Keywords that indicate a blocked/unavailable source
BLOCKED_KEYWORDS = [
    "access denied",
    "authentication required",
    "paywall",
    "captcha",
    "rate limit",
    "too many requests",
    "not found",
    "login required",
]

# Keywords that indicate the posting is still open
OPEN_KEYWORDS = [
    "apply now",
    "apply",
    "open to",
    "accepting applications",
    "hiring",
    "application open",
    "join us",
]


class VerificationService:
    """Service for verifying job listing status."""

    def __init__(self):
        self._timestamp = None

    def _now_utc(self) -> str:
        """Get current UTC timestamp."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def check_closure(self, description: str, raw_data: dict) -> bool:
        """
        Check if a job posting is closed.
        Returns True if closure is strongly indicated.
        """
        text = (description or "") + " " + str(raw_data)
        text_lower = text.lower()

        # Check for explicit closure keywords
        for keyword in CLOSED_KEYWORDS:
            if keyword.lower() in text_lower:
                return True

        # Check for "closed" in title or location
        if "closed" in text_lower:
            return True

        return False

    def check_blocked(self, description: str, status_code: Optional[int]) -> bool:
        """
        Check if a source is blocked or inaccessible.
        """
        if status_code is not None and status_code >= 400:
            return True

        text = (description or "").lower()
        for keyword in BLOCKED_KEYWORDS:
            if keyword in text:
                return True
        return False

    def check_open(self, description: str) -> bool:
        """
        Check if a posting is clearly open with an application path.
        """
        text = (description or "").lower()
        text_with_url = text + " " + str(description or "")
        # Also check for application-related URLs
        for keyword in OPEN_KEYWORDS:
            if keyword.lower() in text_with_url:
                return True
        return False

    def determine_status(
        self,
        source_api_status: int,
        has_individual_url: bool,
        can_open_page: bool,
        description: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> tuple[VerificationStatus, str]:
        """
        Determine verification status based on API response and page accessibility.
        Returns (status, evidence_string).
        """
        evidence_parts = []
        status = VerificationStatus.API_CONFIRMED

        # HTTP status check
        if source_api_status is not None and source_api_status >= 400:
            if source_api_status == 401:
                status = VerificationStatus.BLOCKED
                evidence_parts.append("HTTP 401: authentication required")
            elif source_api_status == 403:
                status = VerificationStatus.BLOCKED
                evidence_parts.append("HTTP 403: access denied")
            elif source_api_status == 404:
                status = VerificationStatus.BLOCKED
                evidence_parts.append("HTTP 404: endpoint not found")
            else:
                status = VerificationStatus.BLOCKED
                evidence_parts.append(f"HTTP {source_api_status}: error")
            return status, " ".join(evidence_parts)

        # If we have a valid API response and individual job URL
        if has_individual_url:
            # Check if we can open the page
            if can_open_page:
                status = VerificationStatus.BROWSER_CONFIRMED
                if description:
                    if self.check_open(description):
                        evidence_parts.append("application path detected on page")
                    if self.check_closure(description, raw_data or {}):
                        status = VerificationStatus.CLOSED
                        evidence_parts.append("closure detected on page")
                else:
                    evidence_parts.append("page opened successfully; individual job URL confirmed")
            else:
                status = VerificationStatus.UNVERIFIED
                evidence_parts.append("page not accessible via browser; awaiting manual review")
        else:
            # No individual URL; can only be api_confirmed
            status = VerificationStatus.API_CONFIRMED
            evidence_parts.append(
                "job record returned by authoritative API feed; individual URL not found"
            )

        # Fallback default evidence
        if not evidence_parts:
            evidence_parts.append("record returned by authoritative API feed")

        return status, " ".join(evidence_parts)

    def generate_verification_evidence(
        self,
        provider: str,
        original_job_id: str,
        source_api_url: str,
        source_api_status: int,
        has_individual_url: bool,
        can_open_page: bool,
        description: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> str:
        """
        Generate a human-readable verification evidence string.
        """
        status, evidence = self.determine_status(
            source_api_status,
            has_individual_url,
            can_open_page,
            description,
            raw_data,
        )
        return evidence


class VerificationTracker:
    """Tracks verification history for jobs."""

    def __init__(self):
        self.history: list[dict[str, Any]] = []

    def record(
        self,
        job: JobRecord,
        status: VerificationStatus,
        evidence: str,
        verified_at: str,
    ):
        """Record a verification event."""
        self.history.append(
            {
                "job_id": job.original_job_id,
                "provider": job.provider.value,
                "company": job.company,
                "status": status.value,
                "evidence": evidence,
                "verified_at": verified_at,
            }
        )

    def get_job_verification(self, job_id: str) -> Optional[dict]:
        """Get the latest verification record for a job."""
        for entry in reversed(self.history):
            if entry["job_id"] == job_id:
                return entry
        return None
