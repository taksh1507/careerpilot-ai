"""Ashby public Job Posting API adapter."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from models.schemas import AtsProvider, JobRecord
from adapters import ATSAdapter, ATSConfig

logger = logging.getLogger(__name__)

# Ashby API endpoint
ASHBY_BASE = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyAdapter(ATSAdapter):
    """
    Adapter for Ashby public Job Posting API.
    Endpoint: https://api.ashbyhq.com/posting-api/job-board/{board_name}
    """

    def __init__(
        self,
        board_name: str,
        base_url: str = ASHBY_BASE,
        careers_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        config = ATSConfig(
            board_id=board_name,
            base_url=base_url,
            careers_url=careers_url or f"https://jobs.ashbyhq.com/{board_name}",
            headers=headers,
            timeout=timeout,
        )
        super().__init__(config)
        self.provider = AtsProvider.ASHBY
        self._session = requests.Session()
        self._session.headers.update(self.config.headers or {})

    def fetch_jobs(self) -> tuple[list[JobRecord], list[dict[str, Any]]]:
        """
        Fetch all jobs from the Ashby job board API.
        Returns (jobs, errors).
        """
        url = f"{self.config.base_url}/{self.config.board_id}"
        jobs = []
        errors = []

        try:
            logger.info(f"Fetching Ashby jobs from {self.config.board_id}")
            response = self._session.get(url, timeout=self.session_timeout)
            response.raise_for_status()
            data = response.json()

            raw_jobs = data.get("jobs", [])
            for raw in raw_jobs:
                job = self._parse_ashby_job(raw)
                if job:
                    jobs.append(job)

            logger.info(f"Ashby {self.config.board_id}: {len(jobs)} jobs fetched")
            return jobs, errors

        except requests.exceptions.Timeout as e:
            err = self._parse_error(e, "ashby fetch")
            errors.append(err)
            logger.warning(f"Ashby {self.config.board_id} timeout: {e}")
        except requests.exceptions.HTTPError as e:
            err = self._parse_error(e, "ashby fetch")
            errors.append(err)
            logger.warning(f"Ashby {self.config.board_id} HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            err = self._parse_error(e, "ashby fetch")
            errors.append(err)
            logger.warning(f"Ashby {self.config.board_id} request error: {e}")
        except ValueError as e:
            err = self._parse_error(e, "ashby parse")
            errors.append(err)
            logger.warning(f"Ashby {self.config.board_id} JSON parse error: {e}")
        except Exception as e:
            err = self._parse_error(e, "ashby fetch")
            errors.append(err)
            logger.exception(f"Ashby {self.config.board_id} unexpected error: {e}")

        return jobs, errors

    def fetch_individual_job(self, job_id: str) -> tuple[JobRecord, bool, str]:
        """
        Fetch a specific Ashby job by ID.
        Note: The public API doesn't provide individual job endpoints.
        Returns (job, success, evidence).
        """
        evidence = "Ashby posting API does not provide individual job endpoints; verified via board-level listing."
        return None, False, evidence

    def _parse_ashby_job(self, raw: dict) -> JobRecord | None:
        """
        Parse a single Ashby job record into a normalized JobRecord.
        """
        try:
            title = raw.get("title", "")
            if not title:
                return None

            # Location
            location = raw.get("location", "")
            if not location:
                location = raw.get("secondaryLocations", [{}])[0].get("location", "") if raw.get("secondaryLocations") else ""

            # Company
            company = raw.get("company", "") or self.config.board_id

            # Application URL
            job_url = raw.get("jobUrl", "")
            application_url = raw.get("applyUrl", "") or job_url
            if not application_url:
                application_url = job_url

            # Experience
            experience = None
            desc = raw.get("descriptionPlain", "") or raw.get("description", "") or ""
            content = desc.lower()

            # Look for "Experience: X-Y years" pattern
            exp_match = re.search(r"experience\s*[:\-]\s*([0-9]+)\s*[-–]\s*([0-9]+)\s*years?", content)
            if exp_match:
                experience = f"{exp_match.group(1)}-{exp_match.group(2)} years"
            elif re.search(r"0\s*-\s*1\s*years?", content):
                experience = "0-1 years"

            # Skills
            skills = []
            if desc:
                skills = self._extract_skills_from_ashby(desc)

            # Employment type
            employment_type = raw.get("employmentType") or raw.get("type") or None

            return JobRecord(
                provider=AtsProvider.ASHBY,
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
            logger.warning(f"Failed to parse Ashby job: {e}")
            return None

    def _extract_skills_from_ashby(self, description: str) -> list[str]:
        """Extract skills from Ashby description."""
        text = re.sub(r"<[^>]+>", " ", description)
        text = re.sub(r"\s+", " ", text).strip()
        tokens = re.split(r"[,;\n]", text)
        skills = []
        for token in tokens:
            token = token.strip().lower()
            if len(token) > 3 and token not in skills:
                skills.append(token)
        return skills[:50]
