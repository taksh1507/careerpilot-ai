"""Filtering, matching, and entry-level role classification for job records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from models.schemas import AtsProvider, JobRecord

# Roles explicitly excluded from entry-level searches (case-insensitive substring match)
EXCLUDED_ROLE_PATTERNS = [
    r"senior",  # Senior
    r"lead",  # Lead
    r"staff",  # Staff
    r"principal",  # Principal
    r"manager",  # Manager
    r"director",  # Director
    r"architect",  # Architect
    r"vp",  # VP
    r"chief",  # Chief
]

# Entry-level / fresher indicators
ENTRY_LEVEL_INDICATORS = [
    r"fresher",
    r"entry",  # entry-level, entry level
    r"graduate",
    r"intern",
    r"apprentice",
    r"junior",  # junior software engineer
    r"0\s*-\s*1",  # 0-1 years
    r"0\s*to\s*1",  # 0 to 1 years
    r"no\s*experience",
    r"0\s*-\s*2\s*month*",  # 0-2 months
    r"first\s*job",
]

# Roles that are usually entry-level even without explicit experience
ENTRY_PORTIONS = [
    "engineer",
    "software developer",
    "backend",
    "frontend",
    "full stack",
    "mobile",
    "sdets",
    "sde",
]


@dataclass
class Filters:
    """User-configurable filters for job matching."""

    desired_roles: list[str] = None
    locations: list[str] = None
    remote_preference: bool = False
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    skills: list[str] = None
    employment_type: Optional[str] = None

    def __post_init__(self):
        if self.desired_roles is None:
            self.desired_roles = []
        if self.locations is None:
            self.locations = []
        if self.skills is None:
            self.skills = []


def compile_role_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile regex patterns for role exclusion."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


ROLE_PATTERNS = compile_role_patterns(EXCLUDED_ROLE_PATTERNS)


def classify_experience(experience: Optional[str]) -> Optional[int]:
    """
    Parse an experience string like "2-4 years" or "0-1 years" into a numeric range.
    Returns None if unknown.
    """
    if not experience:
        return None
    text = experience.lower()
    # Match "X-Y years" or "X to Y years"
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*years?", text)
    if m:
        return int(m.group(1))  # return minimum
    # Single year like "2 years"
    m = re.search(r"(\d+)\s*years?", text)
    if m:
        return int(m.group(1))
    # "0-2 months" or similar
    m = re.search(r"0\s*-\s*2\s*month", text)
    if m:
        return 0
    # If no description exists, return None (unknown)
    return None


def has_entry_level_indicator(title: str, description: str, experience: Optional[str]) -> bool:
    """
    Determine if a job has entry-level indicators.
    Returns True if any of: fresher, entry, graduate, intern, apprentice, junior, 0-1, no experience, first job.
    """
    if not title and not description:
        return False

    combined = (title + " " + description).lower()

    for indicator in ENTRY_LEVEL_INDICATORS:
        if re.search(indicator, combined):
            return True

    # Check the experience field for 0-1 years
    if experience:
        exp_text = str(experience).lower()
        if re.search(r"0\s*-\s*1\s*year", exp_text):
            return True

    return False


def is_excluded_role(title: str, description: str) -> bool:
    """
    Check if the job title matches explicitly senior/lead/staff/principal/manager patterns.
    """
    combined = (title + " " + description).lower()
    for pattern in ROLE_PATTERNS:
        if pattern.search(combined):
            return True
    return False


def matches_roles(title: str, description: str, role_keywords: list[str]) -> bool:
    """Check if the job matches desired role keywords."""
    combined = (title + " " + description).lower()
    return any(kw.lower() in combined for kw in role_keywords)


def matches_locations(location: str, location_keywords: list[str]) -> bool:
    """Check if the job location matches desired locations."""
    loc = location.lower()
    return any(kw.lower() in loc for kw in location_keywords)


def matches_skills(description: str, skill_keywords: list[str]) -> bool:
    """Check if the job description contains the desired skills."""
    desc = description.lower()
    return any(kw.lower() in desc for kw in skill_keywords)


def matches_employment_type(
    employment_type: Optional[str], desired_type: Optional[str]
) -> bool:
    """Check if employment type matches."""
    if not desired_type:
        return True
    if not employment_type:
        return False
    return desired_type.lower() in employment_type.lower()


def matches_filters(
    job: JobRecord,
    filters: Filters,
    job_description: str,
    location: str,
) -> bool:
    """
    Check if a job matches all configured filters.
    Returns True if the job passes all filters.
    """
    # 1. Check desired roles
    if filters.desired_roles:
        if not matches_roles(job.title, job_description, filters.desired_roles):
            return False

    # 2. Check locations (include remote if preferred)
    if not filters.remote_preference and filters.locations:
        if not matches_locations(job.location, filters.locations):
            return False
    elif filters.remote_preference and filters.locations:
        # Remote preference: allow any location (including remote)
        pass

    # 3. Check employment type
    if not matches_employment_type(job.employment_type, filters.employment_type):
        return False

    # 4. Check skills
    if filters.skills:
        if not matches_skills(job_description, filters.skills):
            return False

    # 5. Check experience range
    experience_min = convert_experience_to_int(job.experience)
    if filters.experience_min is not None:
        if experience_min is None:
            pass  # unknown experience - keep, as per requirements
        elif experience_min < filters.experience_min:
            return False

    if filters.experience_max is not None:
        if experience_min is None:
            pass  # unknown experience
        elif experience_min > filters.experience_max:
            return False

    return True


def convert_experience_to_int(experience: Optional[str]) -> Optional[int]:
    """Convert experience string to minimum integer years."""
    if not experience:
        return None
    text = experience.lower()
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*years?", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*years?", text)
    if m:
        return int(m.group(1))
    m = re.search(r"0\s*-\s*2\s*month", text)
    if m:
        return 0
    return None


def filter_jobs(
    jobs: list[JobRecord],
    filters: Filters,
) -> tuple[list[JobRecord], list[dict[str, Any]]]:
    """
    Filter jobs according to the configured filters.
    Returns (passed_jobs, failed_jobs_with_reasons).
    """
    passed = []
    failed = []

    for job in jobs:
        description = " ".join(job.skills) + " " + job.verification_evidence
        loc = job.location

        # Skip explicitly excluded roles
        if is_excluded_role(job.title, description):
            failed.append(
                {"job_id": job.original_job_id, "reason": "excluded_role", "job": job}
            )
            continue

        # Check entry-level
        if not has_entry_level_indicator(job.title, description, job.experience):
            # Only pass if experience is missing (unknown) - per requirements
            if job.experience:
                failed.append(
                    {
                        "job_id": job.original_job_id,
                        "reason": "not_entry_level",
                        "job": job,
                    }
                )
                continue

        # Check filters
        if not matches_filters(job, filters, description, loc):
            failed.append({"job_id": job.original_job_id, "reason": "filter_fail", "job": job})
            continue

        passed.append(job)

    return passed, failed


def count_filtered_summary(passed: list[JobRecord], failed: list[dict]) -> dict[str, int]:
    """Generate a summary of filter results."""
    reasons = {}
    for item in failed:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    return {
        "total_jobs": len(passed) + len(failed),
        "passed": len(passed),
        "failed": len(failed),
        "by_reason": reasons,
    }
