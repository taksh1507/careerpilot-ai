"""Base adapter interface for ATS providers."""

from __future__ import annotations

import abc
import logging
from typing import Any

from models.schemas import JobRecord, AtsProvider

logger = logging.getLogger(__name__)


class ATSConfig:
    """Configuration for an ATS provider."""

    def __init__(
        self,
        board_id: str,
        base_url: str,
        careers_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        rate_limit_delay: float = 0.5,
    ):
        self.board_id = board_id
        self.base_url = base_url
        self.careers_url = careers_url
        self.headers = headers or {}
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay


class ATSAdapter(abc.ABC):
    """Abstract base class for ATS adapters."""

    provider: AtsProvider

    def __init__(self, config: ATSConfig | None = None):
        self.config = config
        self.session_timeout = config.timeout if config else 30.0

    @property
    def provider(self) -> AtsProvider:
        return self._provider

    @provider.setter
    def provider(self, value: AtsProvider):
        self._provider = value

    @abc.abstractmethod
    def fetch_jobs(self) -> tuple[list[JobRecord], list[dict[str, Any]]]:
        """
        Fetch jobs from the ATS API.
        Returns (jobs, errors).
        """
        pass

    @abc.abstractmethod
    def fetch_individual_job(self, job_id: str) -> tuple[JobRecord, bool, str]:
        """
        Fetch a specific job by ID (for verification).
        Returns (job, success, evidence).
        """
        pass

    def _parse_error(self, error: Exception, context: str) -> dict[str, Any]:
        """Standard error parsing."""
        return {
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
