"""Tests for the verification module."""

import pytest

from verification.verifier import VerificationService, VerificationStatus
from models.schemas import VerificationStatus as VS


class TestVerificationService:
    """Tests for verification status determination."""

    def test_http_401_blocked(self):
        """HTTP 401 should be blocked."""
        service = VerificationService()
        status, evidence = service.determine_status(
            source_api_status=401,
            has_individual_url=False,
            can_open_page=False,
        )
        assert status == VerificationStatus.BLOCKED
        assert "401" in evidence

    def test_http_403_blocked(self):
        """HTTP 403 should be blocked."""
        service = VerificationService()
        status, evidence = service.determine_status(
            source_api_status=403,
            has_individual_url=False,
            can_open_page=False,
        )
        assert status == VerificationStatus.BLOCKED
        assert "403" in evidence

    def test_http_404_blocked(self):
        """HTTP 404 should be blocked."""
        service = VerificationService()
        status, evidence = service.determine_status(
            source_api_status=404,
            has_individual_url=False,
            can_open_page=False,
        )
        assert status == VerificationStatus.BLOCKED

    def test_api_confirmed_without_url(self):
        """API response without individual URL is api_confirmed."""
        service = VerificationService()
        status, evidence = service.determine_status(
            source_api_status=200,
            has_individual_url=False,
            can_open_page=False,
        )
        assert status == VerificationStatus.API_CONFIRMED
        assert "authoritative API" in evidence

    def test_browser_confirmed_with_url(self):
        """Valid API + individual URL + accessible page is browser_confirmed."""
        service = VerificationService()
        status, evidence = service.determine_status(
            source_api_status=200,
            has_individual_url=True,
            can_open_page=True,
        )
        assert status == VerificationStatus.BROWSER_CONFIRMED

    def test_unverified_page_not_accessible(self):
        """Page not accessible is unverified."""
        service = VerificationService()
        status, evidence = service.determine_status(
            source_api_status=200,
            has_individual_url=True,
            can_open_page=False,
        )
        assert status == VerificationStatus.UNVERIFIED

    def test_api_status_above_400_blocked(self):
        """Any >= 400 status is blocked."""
        service = VerificationService()
        for status_code in [400, 401, 402, 403, 404, 500, 502]:
            status, _ = service.determine_status(
                source_api_status=status_code,
                has_individual_url=False,
                can_open_page=False,
            )
            assert status == VerificationStatus.BLOCKED, f"Status {status_code} should be blocked"

    def test_closure_recognized(self):
        """Closure keywords in description should be detected."""
        service = VerificationService()
        is_closed = service.check_closure(
            "No longer accepting applications for this position.",
            {}
        )
        assert is_closed is True

    def test_open_recognized(self):
        """Open keywords should be detected."""
        service = VerificationService()
        is_open = service.check_open(
            "Application open. Apply now for this software engineering role."
        )
        assert is_open is True

    def test_blocked_keywords(self):
        """Blocked keywords should be detected."""
        service = VerificationService()
        text = "Access denied. Please authenticate to continue."
        is_blocked = service.check_blocked(text, status_code=200)
        assert is_blocked is True
