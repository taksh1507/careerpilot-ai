# Roadmap

## Implemented

- Greenhouse, Lever, and Ashby public API discovery adapters, normalized records, SQLite persistence, and duplicate handling.
- Resume extraction/profile persistence with explicit review state.
- Deterministic skill/role/location/employment/experience matching and eligibility explanations.
- Local `all-MiniLM-L6-v2` Sentence Transformer cosine scoring with deterministic fallback.
- Local FastAPI contract and responsive profile/recommendation dashboard.

## In development

- Validate and stabilize the API runtime across the supported development environments.
- Improve fixture/ranking evaluation and semantic result observability without storing personal resume text in logs.

## Planned, consistent with the agreed architecture

1. Add authentication and per-candidate authorization at the backend/mobile sync boundary.
2. Build Expo Router screens for resume upload/review, recommendations, and application tracking, with local SQLite persistence.
3. Define a Hermes run contract and idempotent sync interface to FastAPI.
4. Add opt-in AWS infrastructure for EC2 t3.small/Ubuntu 24.04, EventBridge scheduling, Lambda start/stop orchestration, S3 snapshots, and DynamoDB run metadata after design/security review and explicit infrastructure approval.
5. Add deployment, monitoring, backups, and cost controls only after local/mobile workflows are verified.

Manual job applications remain in scope; no automatic application submission is planned.
