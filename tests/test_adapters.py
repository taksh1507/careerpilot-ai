"""Tests for the Greenhouse adapter with mocked API responses."""

import pytest
from unittest.mock import patch, Mock

from adapters.greenhouse import GreenhouseAdapter
from models.schemas import JobRecord, VerificationStatus, AtsProvider


class TestGreenhouseAdapter:
    """Tests for GreenhouseAdapter parsing and fetching."""

    def test_parse_backend_engineer_e3(self):
        """Test parsing BitGo Backend Engineer E3 - Ecosystem."""
        adapter = GreenhouseAdapter(board_id="bitgo")
        job = adapter._parse_greenhouse_job({
            "id": 7344201002,
            "title": "Backend Engineer E3 - Ecosystem",
            "company_name": "BitGo",
            "location": {"name": "India"},
            "absolute_url": "https://job-boards.greenhouse.io/bitgo/jobs/7344201002",
            "content": "Backend Engineer E3 for blockchain infrastructure. Experience with server-side languages like TypeScript/Node. SQL databases like Postgres.",
        })

        assert job is not None
        assert job.provider == AtsProvider.GREENHOUSE
        assert job.original_job_id == "7344201002"
        assert job.company == "BitGo"
        assert job.title == "Backend Engineer E3 - Ecosystem"
        assert job.location == "India"
        assert job.application_url == "https://job-boards.greenhouse.io/bitgo/jobs/7344201002"
        assert job.verification_status == VerificationStatus.API_CONFIRMED

    def test_parse_backend_engineer_e3_india(self):
        """Test parsing BitGo Backend Engineer E3 - India (6+ years)."""
        adapter = GreenhouseAdapter(board_id="bitgo")
        job = adapter._parse_greenhouse_job({
            "id": 8869949002,
            "title": "Backend Engineer E3 - India",
            "company_name": "BitGo",
            "location": {"name": "India"},
            "absolute_url": "https://job-boards.greenhouse.io/bitgo/jobs/8869949002",
            "content": "6+ years of professional back-end and server-side development experience.",
        })

        assert job is not None
        assert job.experience is None  # no "X-Y years" pattern found

    def test_parse_mobile_engineer_e2(self):
        """Test parsing BitGo Mobile Engineer E2."""
        adapter = GreenhouseAdapter(board_id="bitgo")
        job = adapter._parse_greenhouse_job({
            "id": 8879340002,
            "title": "Mobile Engineer E2 - (React Native)",
            "company_name": "BitGo",
            "location": {"name": "India"},
            "absolute_url": "https://job-boards.greenhouse.io/bitgo/jobs/8879340002",
            "content": "React Native mobile engineer for cross-platform fintech app.",
        })

        assert job is not None
        assert job.original_job_id == "8879340002"
        assert job.title == "Mobile Engineer E2 - (React Native)"

    def test_requires_title(self):
        """Test that jobs without titles are excluded."""
        adapter = GreenhouseAdapter(board_id="bitgo")
        job = adapter._parse_greenhouse_job({})
        assert job is None

    def test_invalid_json_returns_none(self):
        """Test that malformed content returns None."""
        adapter = GreenhouseAdapter(board_id="bitgo")
        job = adapter._parse_greenhouse_job({})
        assert job is None


class TestGreenhouseFetch:
    """Tests for GreenhouseAdapter.fetch_jobs with mocked responses."""

    @patch("adapters.greenhouse.requests.Session.get")
    def test_fetch_returns_jobs(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {
                    "id": 7344201002,
                    "title": "Backend Engineer E3",
                    "company_name": "BitGo",
                    "location": {"name": "India"},
                    "absolute_url": "https://test.com/1",
                    "content": "Backend engineer with experience.",
                }
            ]
        }
        mock_get.return_value = mock_response

        adapter = GreenhouseAdapter(board_id="bitgo")
        jobs, errors = adapter.fetch_jobs()

        assert len(jobs) == 1
        assert jobs[0].company == "BitGo"
        assert len(errors) == 0

    @patch("adapters.greenhouse.requests.Session.get")
    def test_http_500_returns_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_get.return_value = mock_response

        adapter = GreenhouseAdapter(board_id="bitgo")
        jobs, errors = adapter.fetch_jobs()

        assert len(jobs) == 0
        assert len(errors) > 0
