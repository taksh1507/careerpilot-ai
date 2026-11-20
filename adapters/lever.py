"""Lever public Postings API adapter."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from models.schemas import AtsProvider, JobRecord
from adapters import ATSAdapter, ATSConfig

logger = logging.getLogger(__name__)

# Lever API endpoint
LEVER_BASE = "https://api.lever.co/v0/postings"


class LeverAdapter(ATSAdapter):
    """
    Adapter for Lever public Postings API.
    Endpoint: https://api.lever.co/v0/postings/{site}?mode=json
    """

    def __init__(
        self,
        site: str,
        base_url: str = LEVER_BASE,
        careers_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        config = ATSConfig(
            board_id=site,
            base_url=base_url,
            careers_url=careers_url or f"https://jobs.lever.co/{site}",
            headers=headers,
            timeout=timeout,
        )
        super().__init__(config)
        self.provider = AtsProvider.LEVER
        self._session = requests.Session()
        self._session.headers.update(self.config.headers or {})

    def fetch_jobs(self) -> tuple[list[JobRecord], list[dict[str, Any]]]:
        """
        Fetch all jobs from the Lever postings API.
        Returns (jobs, errors).
        """
        url = f"{self.config.base_url}/{self.config.board_id}?mode=json"
        jobs = []
        errors = []

        try:
            logger.info(f"Fetching Lever jobs from {self.config.board_id}")
            response = self._session.get(url, timeout=self.session_timeout)
            response.raise_for_status()
            data = response.json()

            # Lever API can return a list or a dict with 'jobs' key
            if isinstance(data, list):
                raw_jobs = data
            elif isinstance(data, dict):
                raw_jobs = data.get("jobs", data.get("postings", []))
            else:
                raw_jobs = []

            for raw in raw_jobs:
                job = self._parse_lever_job(raw)
                if job:
                    jobs.append(job)

            logger.info(f"Lever {self.config.board_id}: {len(jobs)} jobs fetched")
            return jobs, errors

        except requests.exceptions.Timeout as e:
            err = self._parse_error(e, "lever fetch")
            errors.append(err)
            logger.warning(f"Lever {self.config.board_id} timeout: {e}")
        except requests.exceptions.HTTPError as e:
            err = self._parse_error(e, "lever fetch")
            errors.append(err)
            logger.warning(f"Lever {self.config.board_id} HTTP error: {e}")
        except requests.exceptions.RequestException as e:
            err = self._parse_error(e, "lever fetch")
            errors.append(err)
            logger.warning(f"Lever {self.config.board_id} request error: {e}")
        except ValueError as e:
            err = self._parse_error(e, "lever parse")
            errors.append(err)
            logger.warning(f"Lever {self.config.board_id} JSON parse error: {e}")
        except Exception as e:
            err = self._parse_error(e, "lever fetch")
            errors.append(err)
            logger.exception(f"Lever {self.config.board_id} unexpected error: {e}")

        return jobs, errors

    def fetch_individual_job(self, job_id: str) -> tuple[JobRecord, bool, str]:
        """
        Fetch a specific Lever job by ID (via applyUrl).
        Returns (job, success, evidence).
        """
        try:
            # Lever has per-job URLs like https://jobs.lever.co/{site}/{uuid}/apply
            # We can't fetch the individual job via the API without authentication,
            # but the board fetch provides the applyUrl.
            job = self._parse_lever_job({"id": job_id, "applyUrl": None})
            # No individual lookup; just report
            evidence = "Lever postings API does not provide individual job endpoints; verified via board-level listing."
            return None, False, evidence
        except Exception as e:
            return None, False, str(e)

    def _parse_lever_job(self, raw: dict) -> JobRecord | None:
        """
        Parse a single Lever job record into a normalized JobRecord.
        """
        try:
            title = raw.get("text", "") or raw.get("title", "")
            if not title:
                return None

            # Location
            country = raw.get("country", "")
            if not country:
                country = raw.get("location", "")
            location = str(country) if country else ""

            # Company
            company = raw.get("company", "") or self.config.board_id

            # Apply URL (individual job URL)
            job_url = raw.get("hostedUrl", "")
            application_url = raw.get("applyUrl", "") or job_url
            if not application_url:
                application_url = f"https://jobs.lever.co/{self.config.board_id}/{raw.get('id')}"

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
                skills = self._extract_skills_from_lever(desc)

            # Employment type
            employment_type = raw.get("workplaceType") or raw.get("type") or None

            return JobRecord(
                provider=AtsProvider.LEVER,
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
            logger.warning(f"Failed to parse Lever job: {e}")
            return None

    def _extract_skills_from_lever(self, description: str) -> list[str]:
        """Extract skills from Lever description."""
        text = re.sub(r"<[^>]+>", " ", description)
        text = re.sub(r"\s+", " ", text).strip()
        tokens = re.split(r"[,;\n]", text)
        skills = []
        for token in tokens:
            token = token.strip().lower()
            if len(token) > 3 and token not in skills:
                skills.append(token)
        return skills[:50]
