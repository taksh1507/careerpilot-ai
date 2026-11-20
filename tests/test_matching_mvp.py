"""Offline tests for profile review, deterministic/semantic matching, and API behavior."""

import sqlite3

import pytest

from filters.matcher import Filters
from matching.matcher import JobMatcher, MatchingError
from matching.semantic import cosine_similarity
from models.schemas import AtsProvider, JobRecord, MatchHistory, UserProfile
from storage.database import SQLiteStorage
from storage.user_profile import UserProfileStorage


class FakeEncoder:
    model_version = "fake-model@fixture"

    def score_jobs(self, profile, jobs):
        return [0.91 if "Python" in job.skills else 0.25 for job in jobs]


class BrokenEncoder:
    model_version = "unavailable"

    def score_jobs(self, profile, jobs):
        raise RuntimeError("fixture model unavailable")


@pytest.fixture
def stores(tmp_path):
    return (SQLiteStorage(str(tmp_path / "jobs.db")),
            UserProfileStorage(str(tmp_path / "profiles.db")))


def job(job_id="j1", **kwargs):
    fields = dict(provider=AtsProvider.GREENHOUSE, original_job_id=job_id,
                  company="Example", title="Backend Engineer", location="India",
                  skills=["Python"], employment_type="Full-time",
                  application_url="https://example.test/apply",
                  raw_data={"descriptionPlain": "Build distributed Python APIs"})
    fields.update(kwargs)
    return JobRecord(**fields)


def profile(**kwargs):
    fields = dict(user_id="candidate-1", technical_skills=["Python", "SQL"],
                  preferred_roles=["Backend"], preferred_locations=["India"],
                  employment_type="Full-time", reviewed_at="2026-11-20T00:00:00Z")
    fields.update(kwargs)
    return UserProfile(**fields)


def test_review_required_and_profile_edits_clear_approval(stores):
    _, profiles = stores
    candidate = profile(reviewed_at=None)
    profiles.create_profile(candidate)
    with pytest.raises(MatchingError, match="reviewed"):
        JobMatcher().match_jobs([job()], candidate, profiles)
    reviewed = profiles.mark_profile_reviewed(candidate.user_id)
    assert reviewed and reviewed.reviewed_at
    profiles.update_profile(profile(user_id=candidate.user_id, reviewed_at=reviewed.reviewed_at,
                                    technical_skills=["Go"]))
    assert profiles.get_profile(candidate.user_id).reviewed_at is None


def test_profile_creation_never_implicitly_approves(stores):
    _, profiles = stores
    saved = profiles.create_profile(profile())
    assert saved.reviewed_at is None


def test_old_profile_database_migrates_without_losing_profile_data(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
      CREATE TABLE user_profiles (user_id TEXT PRIMARY KEY, education TEXT DEFAULT '', graduation_year INTEGER,
        skills TEXT DEFAULT '', projects TEXT DEFAULT '', work_experience TEXT DEFAULT '', preferred_roles TEXT DEFAULT '',
        preferred_locations TEXT DEFAULT '', remote_preference INTEGER DEFAULT 0, employment_type TEXT,
        resume_file TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
      INSERT INTO user_profiles VALUES ('old','BSc',2024,'Python','proj','', 'Backend','India',0,'Full-time','', '2024','2024');
      CREATE TABLE match_history (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,job_provider TEXT NOT NULL,
        original_job_id TEXT NOT NULL,match_score REAL NOT NULL,eligibility_status TEXT NOT NULL,
        explanation TEXT DEFAULT '',matched_at TEXT NOT NULL,UNIQUE(user_id,job_provider,original_job_id));
    """)
    conn.commit()
    conn.close()
    storage = UserProfileStorage(str(path))
    old = storage.get_profile("old")
    assert old.education == "BSc" and old.technical_skills == ["Python"]
    assert old.reviewed_at is None
    names = {r[1] for r in storage._connect().execute("PRAGMA table_info(match_history)")}
    assert {"semantic_score", "model_version", "algorithm_version"} <= names
    storage.close()


def test_skill_explanation_and_semantic_weight_are_persisted(stores):
    _, profiles = stores
    candidate = profile()
    profiles.create_profile(candidate)
    results = JobMatcher(semantic_encoder=FakeEncoder(), semantic_weight=0.4).match_jobs(
        [job()], candidate, profiles
    )
    assert len(results) == 1
    result = results[0]
    assert result.matching_skills == ["Python"]
    assert result.missing_skills == ["SQL"]
    assert 0 <= result.match_score <= 1
    assert result.semantic_score == 0.91
    assert result.match_score == pytest.approx(0.6 * result.deterministic_score + 0.4 * 0.91)
    assert result.model_version == FakeEncoder.model_version
    saved = profiles.get_match(candidate.user_id, "greenhouse", "j1")
    assert saved and saved.semantic_score == 0.91
    assert saved.model_version == FakeEncoder.model_version


def test_matching_fallback_is_explicitly_deterministic(stores):
    _, profiles = stores
    candidate = profile()
    results = JobMatcher(semantic_encoder=BrokenEncoder(), allow_deterministic_fallback=True).match_jobs(
        [job()], candidate, profiles
    )
    assert len(results) == 1
    assert results[0].model_version == ""
    assert any("semantic score unavailable" in line for line in results[0].explanation)
    assert profiles.get_match(candidate.user_id, "greenhouse", "j1").semantic_score is None


def test_empty_and_duplicate_jobs_have_stable_history(stores):
    _, profiles = stores
    candidate = profile()
    matcher = JobMatcher()
    assert matcher.match_jobs([], candidate, profiles) == []
    results = matcher.match_jobs([job(), job()], candidate, profiles)
    assert len(results) == 2
    assert len(profiles.get_match_history(candidate.user_id)) == 1


def test_explicit_eligibility_distinguishes_failure_from_unknown(stores):
    _, profiles = stores
    candidate = profile()
    matcher = JobMatcher(eligibility_filters=Filters(locations=["India"], employment_type="Full-time"))
    passed = matcher._match_single(job(), candidate, profiles)
    assert matcher._apply_eligibility(job(), candidate, passed)
    assert passed.eligibility_status == "eligible"
    missing = job("missing", location="", employment_type=None)
    unknown_result = matcher._match_single(missing, candidate, profiles)
    assert matcher._apply_eligibility(missing, candidate, unknown_result)
    assert unknown_result.eligibility_status == "unknown"
    outside = job("outside", location="Berlin", employment_type="Internship")
    rejected = matcher._match_single(outside, candidate, profiles)
    assert not matcher._apply_eligibility(outside, candidate, rejected)
    assert rejected.eligibility_status == "ineligible"


def test_cosine_similarity_is_bounded():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cosine_similarity([1], [1, 2])


def test_real_sentence_transformer_model_executes_when_installed(monkeypatch):
    pytest.importorskip("sentence_transformers")
    from matching.semantic import SentenceTransformerEncoder
    try:
        from huggingface_hub import snapshot_download
        snapshot_download("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
    except Exception:
        import os
        if os.getenv("JOBCARE_RUN_REAL_MODEL_TEST") != "1":
            pytest.skip("Model is not cached locally; set JOBCARE_RUN_REAL_MODEL_TEST=1 to allow its download")
    monkeypatch.setenv("HF_HUB_ETAG_TIMEOUT", "15")
    monkeypatch.setenv("HF_HUB_DOWNLOAD_TIMEOUT", "30")
    encoder = SentenceTransformerEncoder()
    try:
        scores = encoder.score_jobs(profile(), [
            job("relevant", title="Python Backend Developer", skills=["Python"],
                raw_data={"descriptionPlain": "Develop Python APIs and backend services"}),
            job("unrelated", title="Pastry Chef", skills=["Baking"], location="Paris",
                raw_data={"descriptionPlain": "Prepare pastries and desserts in a bakery"}),
        ])
    except Exception as exc:
        pytest.skip(f"Local transformer model could not be loaded in this environment: {exc}")
    assert len(scores) == 2 and all(0.0 <= score <= 1.0 for score in scores)
    assert scores[0] > scores[1]
    assert "@" in encoder.model_version


def test_match_history_keeps_backward_compatible_explanations(stores):
    _, profiles = stores
    profiles.create_profile(profile())
    profiles.save_match(MatchHistory("candidate-1", "lever", "x", 0.7, "unknown",
                                     ["skill match"], semantic_score=None,
                                     model_version="", algorithm_version="v1"))
    assert profiles.get_match_history("candidate-1")[0].explanation == ["skill match"]


def test_fastapi_profile_jobs_review_and_recommendations(tmp_path):
    try:
        import fastapi  # noqa: F401
    except Exception as exc:
        pytest.skip(f"FastAPI dependencies cannot be loaded in this interpreter: {exc}")
    from fastapi.testclient import TestClient
    from api.main import create_app

    app = create_app(str(tmp_path / "jobs.db"), str(tmp_path / "profiles.db"), FakeEncoder())
    with TestClient(app) as client:
        app.state.profiles.create_profile(profile(reviewed_at=None))
        app.state.jobs.upsert_job(job())
        assert client.get("/health").status_code == 200
        assert client.get("/ready").json()["ready"] is True
        assert client.get("/api/jobs").json()["total"] == 1
        assert client.post("/api/matches", json={"user_id": "candidate-1"}).status_code == 409
        update = profile(reviewed_at=None).__dict__
        assert client.put("/api/profile", json=update).status_code == 200
        assert client.post("/api/profile/review", json={"user_id": "candidate-1", "approved": True}).status_code == 200
        recommendations = client.post("/api/matches", json={"user_id": "candidate-1"})
        assert recommendations.status_code == 200
        match = recommendations.json()["items"][0]
        assert match["matched_skills"] == ["Python"]
        assert match["missing_skills"] == ["SQL"]
        assert client.get("/api/matches?user_id=candidate-1").json()["total"] == 1
        assert client.get("/api/profile?user_id=not-found").status_code == 404


def test_api_rejects_bad_input_and_requires_explicit_approval(tmp_path):
    try:
        import fastapi  # noqa: F401
    except Exception as exc:
        pytest.skip(f"FastAPI dependencies cannot be loaded in this interpreter: {exc}")
    from fastapi.testclient import TestClient
    from api.main import create_app

    app = create_app(str(tmp_path / "jobs.db"), str(tmp_path / "profiles.db"), FakeEncoder())
    with TestClient(app) as client:
        app.state.profiles.create_profile(profile(reviewed_at=None))
        invalid = client.post("/api/profile/review", json={"user_id": "candidate-1", "approved": False})
        assert invalid.status_code == 422
        invalid = client.post("/api/matches", json={"user_id": "candidate-1", "limit": 0})
        assert invalid.status_code == 422
        invalid = client.put("/api/profile", json={"user_id": "candidate-1", "unexpected": True})
        assert invalid.status_code == 422
