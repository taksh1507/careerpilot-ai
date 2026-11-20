"""Local sentence-transformer embeddings for profile-to-job similarity."""

from __future__ import annotations

import html
import os
import re
from typing import Protocol

from models.schemas import JobRecord, UserProfile

DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_ID = os.getenv("JOBCARE_MODEL_ID", DEFAULT_MODEL_ID)
MODEL_REVISION = os.getenv("JOBCARE_MODEL_REVISION", "main")


class Encoder(Protocol):
    model_id: str
    model_version: str

    def score_jobs(self, profile: UserProfile, jobs: list[JobRecord]) -> list[float]: ...


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def profile_text(profile: UserProfile) -> str:
    """Build an embedding query only from saved profile fields."""
    sections = [
        ("Target roles", profile.preferred_roles),
        ("Technical skills", profile.technical_skills),
        ("Projects", profile.projects),
        ("Work experience", profile.work_experience),
        ("Education", [profile.education] if profile.education else []),
    ]
    return "\n".join(f"{label}: {', '.join(_clean_text(v) for v in values if _clean_text(v))}"
                     for label, values in sections if values)


def job_text(job: JobRecord) -> str:
    raw = job.raw_data if isinstance(job.raw_data, dict) else {}
    description_fields = ("descriptionPlain", "description", "content", "jobDescription", "job_description")
    descriptions = [_clean_text(raw.get(key)) for key in description_fields]
    descriptions = [value for value in descriptions if value]
    return "\n".join(part for part in (
        f"Job title: {job.title}" if job.title else "",
        f"Company: {job.company}" if job.company else "",
        f"Location: {job.location}" if job.location else "",
        f"Employment type: {job.employment_type}" if job.employment_type else "",
        f"Experience: {job.experience}" if job.experience else "",
        f"Skills: {', '.join(job.skills)}" if job.skills else "",
        "Description: " + " ".join(descriptions) if descriptions else "",
    ) if part)


def job_searchable_text(job: JobRecord) -> str:
    """Text fields suitable for deterministic keyword and skill checks."""
    return " ".join((job.title, job.location, job.experience or "", " ".join(job.skills), job_text(job)))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("Embedding vectors must be non-empty and have equal dimensions")
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = sum(float(a) ** 2 for a in left) ** 0.5
    right_norm = sum(float(b) ** 2 for b in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


class SentenceTransformerEncoder:
    """Lazy CPU-first encoder; model weights stay in the local Hugging Face cache."""

    def __init__(self, model_id: str = MODEL_ID, revision: str = MODEL_REVISION):
        self.model_id = model_id
        self.revision = revision
        self.model_version = f"{model_id}@{revision}"
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Semantic matching dependencies are missing. Install requirements-mvp.txt."
            ) from exc
        try:
            model = SentenceTransformer(self.model_id, revision=self.revision, device="cpu")
        except Exception as exc:
            raise RuntimeError(
                f"Could not load local embedding model {self.model_id}@{self.revision}; "
                "check model access/network once, then retry from the local cache."
            ) from exc
        try:
            resolved = model._first_module().auto_model.config._commit_hash
        except (AttributeError, TypeError):
            resolved = None
        if resolved:
            self.model_version = f"{self.model_id}@{resolved}"
        self._model = model
        return model

    def score_jobs(self, profile: UserProfile, jobs: list[JobRecord]) -> list[float]:
        if not jobs:
            return []
        texts = [profile_text(profile)] + [job_text(job) for job in jobs]
        if not texts[0].strip():
            raise ValueError("Candidate profile has no reviewed role, skill, project, experience, or education text")
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                               show_progress_bar=False)
        rows = vectors.tolist() if hasattr(vectors, "tolist") else vectors
        return [cosine_similarity(rows[0], vector) for vector in rows[1:]]
