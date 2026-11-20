# CareerPilot AI — Job Scout Matching MVP

This repository is the existing Python discovery and matching component. Milestone 1 adds local candidate profile review, explainable deterministic and semantic matching, a FastAPI interface, and a small local demo dashboard. It preserves the existing Greenhouse, Lever, and Ashby adapters and SQLite job store.

## Architecture and status

- **Implemented:** `adapters/`, `models/`, `storage/database.py` provide public ATS board ingestion, normalized jobs, and persistent job storage.
- **Implemented:** `storage/user_profile.py` stores candidate profiles, resume extraction records, reviewed state, and match history. Additive SQLite migrations preserve existing data.
- **Implemented:** `matching/` combines weighted deterministic matching with optional local Sentence Transformers cosine similarity.
- **Implemented:** `api/main.py` exposes a loopback-only FastAPI service over the existing SQLite stores.
- **Implemented:** `web/index.html` provides a responsive local profile review, saved jobs, and ranked results dashboard.
- **Verified:** the full test suite passes on Ubuntu 24.04 WSL2, including API integration and real model execution. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md).
- **Planned:** React Native + Expo, Hermes worker on AWS EC2 with EventBridge/Lambda orchestration, S3 snapshots, and DynamoDB run metadata. No cloud resources were created. Manual applications remain the only application flow.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/API.md](docs/API.md), [docs/DEMO.md](docs/DEMO.md), and [docs/ROADMAP.md](docs/ROADMAP.md).

## Install and run locally

Use Python 3.10 or newer. The existing CLI requirements remain in `requirements.txt`; MVP dependencies use CPU-only PyTorch to avoid installing unused CUDA packages:

```powershell
python -m venv .venv
\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

On first semantic use, `sentence-transformers/all-MiniLM-L6-v2` downloads to the local Hugging Face cache and runs on CPU. No paid model API is used. Set `JOBCARE_MODEL_ID` and `JOBCARE_MODEL_REVISION` to select another compatible local model. If the model is unavailable, recommendations fall back to deterministic scoring and label the semantic score unavailable.

Set isolated database paths, then start the API bound to loopback:

```powershell
$env:JOBCARE_JOB_DB = "$env:TEMP\careerpilot-demo-jobs.db"
$env:JOBCARE_PROFILE_DB = "$env:TEMP\careerpilot-demo-profiles.db"
\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the dashboard or `http://127.0.0.1:8000/docs` for OpenAPI. Do not bind this unauthenticated demo to a public interface. On Windows systems where Application Control blocks the Pydantic native extension, run it in Ubuntu 24.04 WSL2; do not weaken security controls.

## API and candidate review

Candidate records are created or imported through the existing CLI. Resume extraction does not approve a profile. Retrieve and correct it before explicitly approving:

```http
GET /api/profile?user_id=demo
PUT /api/profile
Content-Type: application/json
```

The PUT body accepts `user_id`, `technical_skills`, `preferred_roles`, `preferred_locations`, `employment_type`, `education`, `graduation_year`, `projects`, `work_experience`, and `remote_preference`. Editing clears approval.

```http
POST /api/profile/review
{"user_id":"demo","approved":true}

POST /api/matches
{"user_id":"demo","limit":50,"semantic_weight":0.30}

GET /api/matches?user_id=demo
GET /api/jobs?limit=100&offset=0
GET /health
GET /ready
```

Matching responses contain deterministic and semantic scores, matched and missing skills, eligibility status, explanations, model/algorithm identifiers, and original application URLs. The API does not submit applications.

## Matching methodology

The deterministic score keeps existing weighted dimensions: skill overlap 0.40, role relevance 0.20, experience 0.20, location preference 0.10, and education 0.10. Scores are normalized to 0–1. With the local model available, cosine similarity between candidate text and normalized job text is combined as `0.70 × deterministic + 0.30 × semantic` by default. Callers may set the semantic weight from 0 to 1. Model identifier and algorithm version are recorded with match history.

Eligibility checks explicit role, location, employment type, and experience criteria. A clear conflict is ineligible and excluded from recommendation results. Missing listing evidence stays unknown and is retained. The matcher does not infer years of experience from resume-entry counts or convert ambiguous location text into a country.

## Tests

Install test dependencies and run:

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -q
```

The current suite covers the original 67 tests plus review enforcement, SQLite migration, scoring/explanations, eligibility, validation, API flows, duplicates, cosine similarity, and a real local transformer test. CI requires the real model test instead of silently skipping it. The verified run was `80 passed in 20.88s` on Ubuntu 24.04 WSL2; details and Windows runtime limitation are in [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## Security and limitations

- The local API has no user authentication; it only accepts loopback requests by default and must not be exposed publicly.
- The current profile store uses comma-delimited fields for some lists, so values containing commas are not lossless.
- This API serves jobs already in SQLite; discovery remains in the existing CLI.
- Semantic quality depends on model choice and CPU/memory capacity. If the model cannot load, fallback is deterministic and clearly labeled.
- Expo/mobile, Hermes deployment, EventBridge/Lambda, S3, and DynamoDB are future milestones and are not implemented.
