"""Greenhouse public Job Board API adapter."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from models.schemas import AtsProvider, JobRecord
from adapters import ATSAdapter, ATSConfig

logger = logging.getLogger(__name__)

# Greenhouse API endpoint
GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards"
JOBS_ENDPOINT = "jobs?content=true"


class GreenhouseAdapter(ATSAdapter):
    """
    Adapter for Greenhouse public Job Board API.
    Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    """

    def __init__(
        self,
        board_id: str,
        base_url: str = GREENHOUSE_BASE,
        careers_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        config = ATSConfig(
            board_id=board_id,
            base_url=base_url,
            careers_url=careers_url or f"https://boards.greenhouse.io/{board_id}",
            headers=headers,
            timeout=timeout,
        )
        super().__init__(config)
        self.provider = AtsProvider.GREENHOUSE
        self._session = requests.Session()
        self._session.headers.update(self.config.headers or {})

    def fetch_jobs(self) -> tuple[list[JobRecord], list[dict[str, Any]]]:
        """
        Fetch all jobs from the Greenhouse board API.
        Returns (jobs, errors).
        """
        url = f"{self.config.base_url}/{self.config.board_id}/{JOBS_ENDPOINT}"
        jobs = []
        errors = []

        try:
            logger.info(f"Fetching Greenhouse jobs from {self.config.board_id}")
            response = self._session.get(url, timeout=self.session_timeout)
            response.raise_for_status()
            data = response.json()

            raw_jobs = data.get("jobs", [])
            for raw in raw_jobs:
                job = self._parse_greenhouse_job(raw)
                if job:
                    jobs.append(job)

            logger.info(f"Greenhouse {self.config.board_id}: {len(jobs)} jobs fetched")
            return jobs, errors

        except requests.exceptions.Timeout as e:
            err = self._parse_error(e, "greenhouse fetch")
            errors.append(err)
            logger.warning(f"Greenhouse {self.config.board_id} timeout: {e}")
        except requests.exceptions.HTTPError as e:
            err = self._parse_error(e, "greenhouse fetch")
            errors.append(err)
            logger.warning(f"Greenhouse {self.config.board_id} HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            err = self._parse_error(e, "greenhouse fetch")
            errors.append(err)
            logger.warning(f"Greenhouse {self.config.board_id} request error: {e}")
        except ValueError as e:
            err = self._parse_error(e, "greenhouse parse")
            errors.append(err)
            logger.warning(f"Greenhouse {self.config.board_id} JSON parse error: {e}")
        except Exception as e:
            err = self._parse_error(e, "greenhouse fetch")
            errors.append(err)
            logger.exception(f"Greenhouse {self.config.board_id} unexpected error: {e}")

        return jobs, errors

    def fetch_individual_job(self, job_id: str) -> tuple[JobRecord, bool, str]:
        """
        Fetch a specific Greenhouse job by ID.
        Note: The public API doesn't provide individual job endpoints.
        Returns (job, success, evidence).
        """
        # The public API doesn't support individual job lookups.
        # We can only verify via the absolute_url from the board.
        evidence = "Greenhouse public API does not provide individual job endpoints; verified via board-level listing."
        return None, False, evidence

    def _parse_greenhouse_job(self, raw: dict) -> JobRecord | None:
        """
        Parse a single Greenhouse job record into a normalized JobRecord.
        """
        try:
            title = raw.get("title", "")
            if not title:
                return None

            # Location: may be a dict or string
            location = raw.get("location", {})
            if isinstance(location, dict):
                location = location.get("name", "")
            location = str(location) if location else ""

            # Company
            company = raw.get("company_name", "")

            # Absolute URL (application URL)
            job_url = raw.get("absolute_url", "")
            if not job_url:
                return None

            # Application URL for individual job
            application_url = job_url if job_url else ""

            # Experience
            experience = None
            content = raw.get("content", "")
            if content:
                exp_match = re.search(r"experience\s*:\s*([0-9]+)\s*[-–]\s*([0-9]+)", content.lower())
                if exp_match:
                    experience = f"{exp_match.group(1)}-{exp_match.group(2)} years"
                else:
                    # Check for "0-1 years" or similar
                    if re.search(r"0\s*-\s*1\s*years?", content.lower()):
                        experience = "0-1 years"

            # Skills
            skills = []
            desc = raw.get("content", "")
            if desc:
                skills = self._extract_skills_from_greenhouse(desc)

            # Employment type
            employment_type = raw.get("workplace_type") or raw.get("type") or None

            return JobRecord(
                provider=AtsProvider.GREENHOUSE,
                original_job_id=str(raw.get("id", "")),
                company=company,
                title=title,
                location=location,
                experience=experience,
                skills=skills,
                employment_type=employment_type,
                job_url=job_url,
                application_url=application_url,
                source_api_url=raw.get("source_api_url", ""),
                raw_data=raw,
            )

        except Exception as e:
            logger.warning(f"Failed to parse Greenhouse job: {e}")
            return None

    def _extract_skills_from_greenhouse(self, content: str) -> list[str]:
        """
        Extract skills from Greenhouse content HTML.
        Simpler: look for common skill keywords.
        """
        # Pull text from HTML
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        # Split by commas, semicolons, and newlines
        tokens = re.split(r"[,;\n]", text)
        # Filter meaningful tokens
        skills = []
        for token in tokens:
            token = token.strip().lower()
            if len(token) > 3 and token not in skills:
                skills.append(token)
        return skills[:50]
