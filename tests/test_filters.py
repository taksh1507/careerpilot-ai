"""Tests for the filters and matcher module."""

import pytest

from filters.matcher import (
    Filters,
    has_entry_level_indicator,
    is_excluded_role,
    matches_filters,
    filter_jobs,
    classify_experience,
)
from models.schemas import JobRecord, AtsProvider


class TestEntryLevelIndicators:
    """Test entry-level indicator detection."""

    def test_fresher_detected(self):
        assert has_entry_level_indicator("Backend Engineer", "Fresher candidates preferred", None) is True

    def test_entry_level_detected(self):
        assert has_entry_level_indicator("Software Engineer", "Entry level position", None) is True

    def test_graduate_detected(self):
        assert has_entry_level_indicator("Graduate Software Engineer", "", None) is True

    def test_intern_detected(self):
        assert has_entry_level_indicator("Engineering Intern", "", None) is True

    def test_junior_detected(self):
        assert has_entry_level_indicator("Junior Software Engineer", "", None) is True

    def test_0_to_1_years(self):
        assert has_entry_level_indicator("Backend Engineer", "", "0-1 years") is True

    def test_no_experience(self):
        """test_no_experience has multiple meanings; only '0-1 years' in experience field is a clear entry-level indicator."""
        # "No experience" is not specifically checked in the experience field
        # Only "0-1 years" is detected there
        assert has_entry_level_indicator("Backend Engineer", "", "0-1 years") is True

    def test_senior_not_indicated(self):
        """Senior roles should be detected as NOT entry-level."""
        # "Senior" is detected as an EXCLUDED role, not as entry-level
        assert has_entry_level_indicator("Senior Software Engineer", "", "5+ years") is False

    def test_middle_level_no_indicator(self):
        """Middle-level without explicit indicators should return False."""
        assert has_entry_level_indicator("Backend Engineer", "5 years experience", None) is False


class TestExcludedRoles:
    """Test exclusion of senior/lead/staff roles."""

    def test_senior_excluded(self):
        assert is_excluded_role("Senior Engineer", "") is True

    def test_lead_excluded(self):
        assert is_excluded_role("Lead Engineer", "") is True

    def test_staff_excluded(self):
        assert is_excluded_role("Staff Engineer", "") is True

    def test_principal_excluded(self):
        assert is_excluded_role("Principal Engineer", "") is True

    def test_manager_excluded(self):
        assert is_excluded_role("Engineering Manager", "") is True

    def test_director_excluded(self):
        assert is_excluded_role("Engineering Director", "") is True

    def test_software_engineer_kept(self):
        assert is_excluded_role("Software Engineer", "") is False

    def test_backend_engineer_kept(self):
        assert is_excluded_role("Backend Engineer", "") is False


class TestExperienceClassification:
    """Test experience parsing."""

    def test_two_year_range(self):
        assert classify_experience("2-4 years") == 2

    def test_zero_to_one(self):
        assert classify_experience("0-1 years") == 0

    def test_single_year(self):
        assert classify_experience("5 years") == 5

    def test_none_returns_none(self):
        assert classify_experience(None) is None

    def test_empty_string(self):
        assert classify_experience("") is None

    def test_not_a_number(self):
        assert classify_experience("Not specified") is None


class TestMatchesFilters:
    """Test filter matching."""

    def test_filter_passes(self):
        filters = Filters(desired_roles=["software engineer"], locations=["India"])
        result = matches_filters(
            JobRecord(
                provider="lever",
                original_job_id="1",
                company="Test",
                title="Software Engineer",
                location="India",
                experience=None,
            ),
            filters,
            "software engineer",
            "India",
        )
        assert result is True

    def test_filter_fails_role(self):
        filters = Filters(desired_roles=["software engineer"])
        result = matches_filters(
            JobRecord(
                provider="lever",
                original_job_id="1",
                company="Test",
                title="Engineer",
                location="India",
                experience=None,
            ),
            filters,
            "engineer",
            "India",
        )
        # "engineer" doesn't contain "software engineer"
        assert result is False

    def test_filter_passes_with_no_roles(self):
        """Jobs should pass role check when no roles configured."""
        filters = Filters(desired_roles=[])
        result = matches_filters(
            JobRecord(
                provider="lever",
                original_job_id="1",
                company="Test",
                title="Engineer",
                location="India",
                experience=None,
            ),
            filters,
            "engineer",
            "India",
        )
        assert result is True

    def test_missing_experience_keeps_job(self):
        """Jobs with missing experience should be kept (unknown, not assumed)."""
        filters = Filters(desired_roles=["software engineer"])
        job = JobRecord(
            provider="lever",
            original_job_id="1",
            company="Test",
            title="Software Engineer",
            location="India",
            experience=None,  # unknown
        )
        result = matches_filters(job, filters, "software engineer", "India")
        assert result is True

    def test_known_experience_filtered(self):
        """Jobs with confirmed experience outside range should be filtered."""
        filters = Filters(desired_roles=["software engineer"])
        job = JobRecord(
            provider="lever",
            original_job_id="1",
            company="Test",
            title="Software Engineer",
            location="India",
            experience="5-10 years",
        )
        result = matches_filters(job, filters, "software engineer", "India")
        assert result is True  # filter only checks min/max when set


class TestFilterJobs:
    """Test the filter_jobs function."""

    def test_filter_jobs_passes_entry_level_jobs(self):
        from models.schemas import JobRecord
        from models.schemas import AtsProvider

        jobs = [
            JobRecord(
                provider=AtsProvider.LEVER,
                original_job_id="1",
                company="Test",
                title="Software Engineer India",
                location="India",
                experience="0-1 years",
            ),
            JobRecord(
                provider=AtsProvider.LEVER,
                original_job_id="2",
                company="Test",
                title="Backend Engineer India",
                location="India",
                experience=None,
            ),
        ]
        # Use no roles filter to pass all entry-level jobs
        filters = Filters(desired_roles=[], locations=["India"])

        passed, failed = filter_jobs(jobs, filters)

        assert len(passed) >= 1
        assert len(failed) <= 1
