# CareerPilot AI — Job Scout Matching MVP

This repository is the existing Python discovery and matching component. Milestone 1 adds local candidate profile review, explainable deterministic and semantic matching, a FastAPI interface, and a small local demo dashboard. It does not replace the existing Greenhouse, Lever, or Ashby adapters or the SQLite job store.

## Architecture in this milestone

- `adapters/`, `models/`, `storage/database.py`: existing public ATS board ingestion, normalized jobs, and job persistence.
- `storage/user_profile.py`: candidate profiles, resume extraction records, reviewed state, and match history. Migrations add columns without dropping older data.
- `matching/`: weighted deterministic matching and optional local Sentence Transformers embeddings.
- `api/main.py`: local FastAPI integration over the existing SQLite stores.
- `web/index.html`: responsive profile review and ranked job results page served at `/`.
- `tests/`: offline fixture tests plus a real transformer model test when the optional model dependencies are installed.

The broader agreed architecture remains React Native + Expo, a FastAPI backend, local mobile SQLite, and a Hermes worker on AWS EC2 with EventBridge/Lambda orchestration, S3 snapshots, and DynamoDB run metadata. Those mobile and AWS components are not implemented by this milestone; no AWS resources are created here. Manual applications remain the only application flow.

## Install and run locally

Use Python 3.10 or newer. The existing CLI requirements remain in `requirements.txt`; install the MVP additions in an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-mvp.txt
```

The first semantic request downloads `sentence-transformers/all-MiniLM-L6-v2` into the local Hugging Face model cache and runs it on CPU. Set `JOBCARE_MODEL_ID` and `JOBCARE_MODEL_REVISION` to select a compatible local Sentence Transformers model/revision. No paid model API is used. If the model package or local model is unavailable, recommendations fall back to deterministic scoring and label the semantic score unavailable.

The API defaults its database paths to `~/.jobcare/jobcare.db`; override with `JOBCARE_JOB_DB` and `JOBCARE_PROFILE_DB`. Tests and demos should use temporary database paths. The server binds to loopback only:

```powershell
$env:JOBCARE_JOB_DB = "$PWD\demo-jobs.db"
$env:JOBCARE_PROFILE_DB = "$PWD\demo-profiles.db"
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the dashboard or `http://127.0.0.1:8000/docs` for OpenAPI. Do not bind this unauthenticated demo to a public interface. It is not a production deployment or an authentication boundary.

## API examples

Candidate records are created/imported through the existing CLI. Resume extraction never approves the resulting profile. First inspect and correct it:

```http
GET /api/profile?user_id=demo
PUT /api/profile
Content-Type: application/json
```

The `PUT` JSON body uses `user_id`, `technical_skills`, `preferred_roles`, `preferred_locations`, `employment_type`, `education`, `graduation_year`, `projects`, `work_experience`, and `remote_preference`. Editing clears any prior approval. Explicitly approve the corrected profile:

```http
POST /api/profile/review
{"user_id":"demo","approved":true}
```

Then request recommendations and history:

```http
POST /api/matches
{"user_id":"demo","limit":50,"semantic_weight":0.30}
GET /api/matches?user_id=demo
GET /api/jobs?limit=100&offset=0
GET /health
GET /ready
```

Matching returns scores, matched/missing skills, eligibility status, explanations, model identifier, and the original application URL. The API does not submit applications.

## Matching methodology

The deterministic score keeps the existing weighted dimensions: skill overlap 0.40, role relevance 0.20, experience 0.20, location preference 0.10, and education 0.10. Scores are normalized to 0–1. Where the local model is available, cosine similarity between profile text and normalized job text is combined as `0.70 × deterministic + 0.30 × semantic` by default; callers may change the semantic weight from 0 to 1. The model identifier/revision and algorithm version are stored with match history.

Eligibility uses explicit profile constraints for role, location, employment type, and experience ranges. A clear conflict is ineligible and excluded from recommendation results. Missing listing evidence remains unknown and is retained. Candidate years of experience are not inferred from a count of resume entries. Unknown locations and ambiguous short strings are not converted to countries.

## Tests

Run the offline suite:

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -q
```

`tests/test_matching_mvp.py` exercises profile review enforcement, legacy SQLite migration, score components, skill explanations, eligibility outcomes, API validation, duplicate-safe history, cosine calculations, and a real embedding-model execution when Sentence Transformers and the cached model are available. The suite stays offline by default; set `JOBCARE_RUN_REAL_MODEL_TEST=1` to allow downloading the model for that specific test. Deterministic tests use local fixtures and make no API calls.

Latest full run: Python 3.14 isolated environment, `77 passed, 2 skipped`; the real local transformer test passed. The two FastAPI integration tests were skipped because Windows Application Control blocked the installed `pydantic_core` native extension (`DLL load failed while importing _pydantic_core`). The existing 67-test suite passed within that run. On the system interpreter, the pytest-asyncio plugin emits deprecation warnings for its use of `asyncio.iscoroutinefunction`; this originates in the installed plugin and did not fail tests. No unrelated plugin upgrade was applied.

## Limitations

- This is a local-only demo API without user authentication; it must not be exposed publicly.
- The profile store still uses the existing comma-delimited fields for several lists, which cannot losslessly represent values containing commas.
- Job source errors and discovery orchestration remain in the existing CLI; this API serves jobs already persisted in SQLite.
- Expo/mobile UI, Hermes deployment, EventBridge/Lambda, S3, and DynamoDB are future milestones and are not claimed as implemented.
- Semantic ranking depends on local model availability and CPU/memory capacity; fallback is deterministic only.
