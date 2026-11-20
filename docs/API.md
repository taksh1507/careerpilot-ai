# Local API

Run `uvicorn api.main:app --host 127.0.0.1 --port 8000` after installing `requirements-mvp.txt`. Open `/docs` for generated OpenAPI. This API is for local development only: it is unauthenticated and must not be bound to a public interface.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/health` | Liveness response. |
| GET | `/ready` | Checks both SQLite connections; reports model loading as lazy. |
| GET | `/api/jobs?limit=100&offset=0&provider=greenhouse` | Lists locally stored jobs. `limit` is 1–500. |
| GET | `/api/profile?user_id=demo` | Returns the local profile, including whether it was reviewed. |
| PUT | `/api/profile` | Replaces profile fields for an existing user; a prior review is cleared. Unknown fields are rejected. |
| POST | `/api/profile/review` | Requires `{"user_id":"demo","approved":true}` to mark the saved profile reviewed. |
| POST | `/api/matches` | Requires a reviewed profile. Accepts `user_id`, `limit` (1–200), and `semantic_weight` (0–1, default 0.30). Persists match history. |
| GET | `/api/matches?user_id=demo` | Returns that candidate's saved match history. |

## Profile update example

`PUT /api/profile` accepts a complete corrected profile, not a partial patch:

```json
{
  "user_id": "demo",
  "education": "B.Tech Computer Science",
  "graduation_year": 2026,
  "technical_skills": ["Python", "FastAPI", "SQL"],
  "projects": ["Local recommendation demo"],
  "work_experience": [],
  "preferred_roles": ["Backend Engineer", "Software Engineer"],
  "preferred_locations": ["India", "Remote"],
  "remote_preference": true,
  "employment_type": "Internship"
}
```

After reviewing the response, call `POST /api/profile/review`. Any subsequent `PUT` requires review again.

## Recommendation response

Each result contains the normalized job, `match_score`, `deterministic_score`, `semantic_score` (null when deterministic fallback was used), model/algorithm identifiers, `matched_skills`, `missing_skills`, eligibility status, explanation lines, and original application URL. Explicit conflicts with profile role/location/employment constraints are excluded. Missing evidence is `unknown` and remains eligible for display.

## Error responses

Errors use a `detail` object with a stable `code` and human-readable `message`; validation errors also include Pydantic field errors. Common codes: `profile_not_found`, `profile_review_required`, `approval_required`, `matching_error`, `validation_error`, `not_ready`, and `local_only`.

The API does not expose a resume download endpoint or submit applications. Profile retrieval is local-only for this milestone; add authentication and authorization before connecting a mobile client over a network.
