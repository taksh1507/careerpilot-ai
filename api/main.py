"""Local-only FastAPI service for profile review and explainable job matches."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
try:  # Support both Pydantic generations accepted by FastAPI 0.115+.
    from pydantic import ConfigDict, field_validator
    PYDANTIC_V2 = True
except ImportError:  # pragma: no cover - exercised in the compatibility test environment
    from pydantic import validator
    PYDANTIC_V2 = False

    def field_validator(*fields):
        def decorate(function):
            raw = function.__func__ if isinstance(function, classmethod) else function
            return validator(*fields, allow_reuse=True)(raw)
        return decorate

from matching.matcher import JobMatcher, MatchingError
from matching.semantic import SentenceTransformerEncoder
from models.schemas import UserProfile
from storage import SQLiteStorage
from storage.user_profile import UserProfileStorage


class StrictModel(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")
    else:
        class Config:
            extra = "forbid"


class ProfilePayload(StrictModel):
    user_id: str = Field(min_length=1, max_length=120)
    education: str = ""
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)
    technical_skills: list[str] = Field(default_factory=list, max_length=100)
    projects: list[str] = Field(default_factory=list, max_length=100)
    work_experience: list[str] = Field(default_factory=list, max_length=100)
    preferred_roles: list[str] = Field(default_factory=list, max_length=50)
    preferred_locations: list[str] = Field(default_factory=list, max_length=50)
    remote_preference: bool = False
    employment_type: str | None = None

    @field_validator("technical_skills", "projects", "work_experience", "preferred_roles", "preferred_locations")
    @classmethod
    def trim_strings(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class ReviewPayload(StrictModel):
    user_id: str = Field(min_length=1, max_length=120)
    approved: bool


class MatchPayload(StrictModel):
    user_id: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=50, ge=1, le=200)
    semantic_weight: float = Field(default=0.30, ge=0, le=1)


def _profile_from_payload(payload: ProfilePayload, existing: UserProfile | None = None) -> UserProfile:
    return UserProfile(
        user_id=payload.user_id,
        education=payload.education,
        graduation_year=payload.graduation_year,
        technical_skills=payload.technical_skills,
        projects=payload.projects,
        work_experience=payload.work_experience,
        preferred_roles=payload.preferred_roles,
        preferred_locations=payload.preferred_locations,
        remote_preference=payload.remote_preference,
        employment_type=payload.employment_type,
        resume_file=existing.resume_file if existing else "",
        created_at=existing.created_at if existing else "",
        updated_at=existing.updated_at if existing else "",
    )


def create_app(job_db_path: str | None = None, profile_db_path: str | None = None,
               semantic_encoder: Any = None, *, local_only: bool = True) -> FastAPI:
    job_db_path = job_db_path or os.getenv("JOBCARE_JOB_DB", str(Path.home() / ".jobcare" / "jobcare.db"))
    profile_db_path = profile_db_path or os.getenv("JOBCARE_PROFILE_DB", job_db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.jobs = SQLiteStorage(job_db_path)
        app.state.profiles = UserProfileStorage(profile_db_path)
        app.state.encoder = semantic_encoder if semantic_encoder is not None else SentenceTransformerEncoder()
        yield
        app.state.jobs.close()
        app.state.profiles.close()

    app = FastAPI(title="JobCare Matching API", version="0.1.0", lifespan=lifespan)
    app.state.paths = (job_db_path, profile_db_path)

    @app.middleware("http")
    async def local_request_only(request: Request, call_next):
        if local_only:
            host = request.client.host if request.client else ""
            if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
                return JSONResponse(
                    {"detail": {"code": "local_only", "message": "This demo API accepts loopback requests only"}},
                    status_code=403,
                )
        return await call_next(request)

    @app.exception_handler(MatchingError)
    async def matching_error_handler(request: Request, exc: MatchingError):
        return JSONResponse(
            {"detail": {"code": "matching_error", "message": str(exc)}}, status_code=409
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(jsonable_encoder(
            {"detail": {"code": "validation_error", "message": "Request input is invalid",
                         "errors": exc.errors()}}), status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "jobcare-matching"}

    @app.get("/ready")
    def ready(request: Request):
        try:
            request.app.state.jobs._connect().execute("SELECT 1")
            request.app.state.profiles._connect().execute("SELECT 1")
            return {"ready": True, "database": "ok", "semantic_model": "lazy_local_load"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"code": "not_ready", "message": str(exc)})

    @app.get("/api/jobs")
    def list_jobs(request: Request, limit: int = Query(default=100, ge=1, le=500),
                  offset: int = Query(default=0, ge=0), provider: str | None = None):
        jobs = request.app.state.jobs.search_jobs(provider=provider, enabled=False)
        selected = jobs[offset:offset + limit]
        return {"items": [job.to_dict() for job in selected], "total": len(jobs), "limit": limit, "offset": offset}

    @app.get("/api/profile")
    def get_profile(request: Request, user_id: str = Query(min_length=1, max_length=120)):
        profile = request.app.state.profiles.get_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail={"code": "profile_not_found", "message": "Candidate profile was not found"})
        return profile.__dict__

    @app.put("/api/profile")
    def update_profile(payload: ProfilePayload, request: Request):
        existing = request.app.state.profiles.get_profile(payload.user_id)
        if not existing:
            raise HTTPException(status_code=404, detail={"code": "profile_not_found", "message": "Create a profile through the existing CLI before editing it"})
        saved = request.app.state.profiles.update_profile(_profile_from_payload(payload, existing))
        return saved.__dict__

    @app.post("/api/profile/review")
    def review_profile(payload: ReviewPayload, request: Request):
        if not payload.approved:
            raise HTTPException(status_code=422, detail={"code": "approval_required", "message": "Set approved=true after checking and correcting the profile"})
        reviewed = request.app.state.profiles.mark_profile_reviewed(payload.user_id)
        if not reviewed:
            raise HTTPException(status_code=404, detail={"code": "profile_not_found", "message": "Candidate profile was not found"})
        return reviewed.__dict__

    @app.post("/api/matches")
    def recommend(payload: MatchPayload, request: Request):
        profiles = request.app.state.profiles
        profile = profiles.get_profile(payload.user_id)
        if not profile:
            raise HTTPException(status_code=404, detail={"code": "profile_not_found", "message": "Candidate profile was not found"})
        if profile.reviewed_at is None:
            raise HTTPException(status_code=409, detail={"code": "profile_review_required", "message": "Review and approve the candidate profile before matching"})
        jobs = request.app.state.jobs.search_jobs(enabled=False)
        encoder = request.app.state.encoder
        matcher = JobMatcher(semantic_encoder=encoder, semantic_weight=payload.semantic_weight,
                             allow_deterministic_fallback=True)
        results = [item for item in matcher.match_jobs(jobs, profile, profiles)
                   if item.eligibility_status != "ineligible"][:payload.limit]
        return {"items": [{
            "job": result.job.to_dict(), "match_score": result.match_score,
            "deterministic_score": result.deterministic_score,
            "semantic_score": result.semantic_score if result.model_version else None,
            "model_version": result.model_version or None,
            "algorithm_version": result.algorithm_version,
            "matched_skills": result.matching_skills, "missing_skills": result.missing_skills,
            "eligibility_status": result.eligibility_status,
            "explanation": result.explanation, "application_url": result.application_url,
        } for result in results], "total": len(results)}

    @app.get("/api/matches")
    def match_history(request: Request, user_id: str = Query(min_length=1, max_length=120)):
        history = request.app.state.profiles.get_match_history(user_id)
        return {"items": [item.__dict__ for item in history], "total": len(history)}

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        dashboard_path = Path(__file__).resolve().parent.parent / "web" / "index.html"
        return dashboard_path.read_text(encoding="utf-8")

    return app


app = create_app()
