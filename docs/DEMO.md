# Local demonstration

## 1. Install

Use Python 3.10 or later and install the runtime/test dependencies. The dependency constraints install the CPU-only PyTorch build used by this local service:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

On first semantic use, the public `sentence-transformers/all-MiniLM-L6-v2` model is downloaded to the local Hugging Face cache. No provider API key is required.

## 2. Start with isolated demo databases

```powershell
$env:JOBCARE_JOB_DB = Join-Path $env:TEMP "careerpilot-demo-jobs.db"
$env:JOBCARE_PROFILE_DB = Join-Path $env:TEMP "careerpilot-demo-profiles.db"
```

Use the existing CLI to configure one or more permitted public ATS boards and sync them into SQLite. Then create a synthetic profile:

```powershell
python jobcare.py create-profile --user-id demo --education "B.Tech Computer Science" --graduation-year 2026 --skills Python FastAPI SQL --preferred-roles "Backend Engineer" "Software Engineer" --preferred-locations India Remote --type Internship
```

Creating or importing a profile does not approve it. Start the local API:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## 3. Review, correct, approve, and match

Open `http://127.0.0.1:8000/`. Select the profile ID `demo`, load the profile, correct skills/roles/location/employment preference, save, and explicitly approve it. Load saved jobs, then rank eligible/unknown jobs. Inspect deterministic/semantic scores, matched/missing skills, eligibility explanation, and original application links.

The CLI can also approve after an explicit review through the API:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/profile/review -ContentType application/json -Body '{"user_id":"demo","approved":true}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/matches -ContentType application/json -Body '{"user_id":"demo","limit":20,"semantic_weight":0.30}'
```

No screenshot is checked in; the dashboard must be opened against a running local API to capture a truthful screen image. Applying to any job remains a manual action through the source's original link.

## Runtime note

On Windows systems where Application Control blocks the official Pydantic native extension, run this demo from Ubuntu 24.04 WSL2 or another approved Linux runtime. Do not weaken or disable Windows security controls.
