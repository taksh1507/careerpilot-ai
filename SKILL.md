---
name: jobcare-job-scout
description: "Autonomous job-discovery skill: retrieve real job records from public ATS APIs (Greenhouse, Lever, Ashby), normalize, filter, verify evidence, and persist to SQLite. Use when the user wants to discover entry-level software engineering jobs, sync employers, or view job listings."
version: 1.0.0
author: JobCare AI
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jobs, career, ats, greenhouse, lever, ashby, hiring, recruiting]
    homepage: https://github.com/upstage/jobcare-job-scout
---

# JobCare AI Job Scout

Autonomous job-discovery capability that retrieves real job records from public
ATS APIs (Greenhouse, Lever, Ashby), normalizes them into a consistent schema,
filters them according to a user's career profile, verifies source evidence,
and stores results persistently.

## When to Use

- User wants to discover entry-level software engineering jobs in India
- User asks to "sync" employers or "update" the job board
- User wants to see verified open vacancies
- User asks to filter jobs by role, location, experience, skills
- User wants historical search runs or export to JSON

## How to Invoke

Run the CLI from the project root:
```bash
# Activate the virtualenv first (if using one)
python -m jobcare.commands <command>

# Or run the CLI script directly
python -m cli.commands <command>
```

Commands:
| Command | When to use |
|---|---|
| `add-employer` | Add a new ATS board (Greenhouse/Lever/Ashby) |
| `list-employers` | Show all configured boards |
| `sync` | Pull fresh job records from all enabled boards |
| `show-verified` | Display verified open vacancies |
| `search` | Search saved jobs with filters |
| `export` | Export results to JSON |
| `view-failed` | Show sync failures |
| `set-preferences` | Configure career profile filters |
| `status` | Quick status summary |

## Architecture

1. **Adapters** — Each ATS provider (Greenhouse, Lever, Ashby) implements the
   documented public API. They return normalized job records.
2. **Filters** — User-configurable career profile (roles, locations, experience,
   remote preference, skills, employment type). Excludes senior/lead/staff roles.
3. **Verification** — Separate `api_confirmed`, `browser_confirmed`, `unverified`,
   `closed`, `blocked` statuses. Never confuse an HTTP 200 search page with a
   verified individual vacancy.
4. **Storage** — SQLite (first local version). Tables: `employers`, `jobs`,
   `job_verification_history`, `search_runs`, `user_preferences`.
5. **CLI** — Add, list, sync, search, verify, view-failed, export, preferences,
   status.

## Key Concepts

- **Stable unique key**: `provider + original_job_id` — used for deduplication.
- **Verification**: `api_confirmed` means returned by authoritative API feed.
  `browser_confirmed` requires opening the specific individual job page.
- **Missing experience = unknown**: Never assume fresher eligibility when
  experience is not specified.
- **Safety**: Never apply for jobs, bypass auth, store passwords, or access
  Gmail/LinkedIn. This skill only retrieves public job data.
- **Multi-user isolation**: User profiles and match history are stored per-user
  with `user_id` as the scope. Use `UserProfileStorage` for all profile-related
  operations, never mix with job records.

## Phase 2 — User Profiles and Intelligent Matching

### Resume Parsing

Two-pass approach for all resume formats:

1. **Section detection** — identify `Skills`, `Projects`, `Work Experience`,
   `Certifications`, `Education` sections by header keywords.
2. **Fallback** — if education/projects/work-experience/certifications are not
   extracted, run keyword matching across the full text to recover missing
   fields. Never return partial data. Handle flat-text resumes (common from
   manually edited resumes).

Resume parser glyphs: keywords (`EDUCATION_KEYWORDS`, `SKILL_KEYWORDS`,
`PROJECT_KEYWORDS`, `CERTIFICATION_KEYWORDS`, `EXPERIENCE_KEYWORDS`),
section regex patterns (`r"^(project|projects|...)"` etc. in
`_is_section_header`).

### Intelligent Job Matching

Deterministic matcher with configurable weights. Scale weights via `WeightConfig`
if needed (default: `skill_overlap=0.4, role_relevance=0.2, experience_eligibility=0.2, location_preference=0.1, education_eligibility=0.1`).

Match score formula (sum of dimension × weight, clamped 0.0–1.0):
- **skill_overlap × 0.4** — extract job skills from description; match against profile skills
- **role_relevance × 0.2** — title contains a preferred role keyword
- **experience_eligibility × 0.2** — job experience range vs. user's work experience; missing experience = unknown
- **location_preference × 0.1** — preferred locations vs. job location; remote flag
- **education_eligibility × 0.1** — graduation year and education level vs. job requirements

Return: match score, matching skills, missing skills, eligibility status, explanation, application URL.

#### Skill Alias Normalization (Phase 2.1)

Build an alias map for skill name variants before comparing job text against profile skills:

| User lists | Also match in job text |
|---|---|
| PostgreSQL | postgres, postgreSQL, postgre |
| Node.js | nodejs, node js, node |
| JavaScript | js |
| Java | java8, java11, java17 |
| C++ | cplusplus, c-plus-plus |
| C# | csharp, dotnet |
| Python | python3, py |
| Ruby | ruby on rails, rails |
| PHP | laravel, symfony |
| Go | golang |
| Rust | rust-lang |
| Kotlin | kt |
| Swift | swiftui |
| TypeScript | ts |
| React | reactjs, react.js |
| Angular | angularjs, angular 2+ |
| Vue | vuejs |
| Django | django framework, djangopackages |
| Flask | flask framework |
| Spring | spring boot, spring framework |

**Rule**: normalize to lowercase, trim whitespace, then check both the exact name and all aliases.

#### Skill Extraction Bypass (Phase 2.1)

Job `skills` field from these API feeds often contains the entire job description text (50+ entries) instead of parsed keywords. Always check `len(job.skills)` first:

- If ≤ 50: treat `job.skills` as the skill list.
- If > 50: extract keywords from the description text (title + source_api_url + application_url) using the alias map above. Extract only the user's profile skills that appear in the job text.

#### Weak Match Labeling (Phase 2.1)

All results below `MIN_MATCH_SCORE = 0.5` must **never** be labeled "Strong recommendation":

- `0.0` = fully disqualified (hard eligibility failure)
- `0.1–0.4` = weak available match (low relevance; show as `low_match` with evidence line "No skill matches found")
- Always show dimension scores and evidence per match, so the user sees which dimension (if any) drove the score.
- A job with 0 skill overlap but a title match is still a `low_match`, not a `high_match`.

## CLI Adapter Reference

When calling the CLI's `sync` command, each provider maps to a different
adapter constructor parameter. Do not pass `board_id` blindly — verify the
parameter name for each provider:

| Provider | Constructor parameter | Example |
|---|---|---|
| `greenhouse` | `board_id` | `GreenhouseAdapter(board_id="bitgo")` |
| `lever` | `site` | `LeverAdapter(site="drivetrain")` |
| `ashby` | `board_name` | `AshbyAdapter(board_name="airbound")` |

If the sync command rejects an argument, the parameter name is wrong — the
`cmd_sync` dispatcher resolves this automatically, but if writing a custom
sync loop, check the adapter signature with `inspect.signature`.



### CLI Commands (Phase 2)

| Command | When to use |
|---|---|
| `create-profile` | Create a new user profile with education, skills, preferences |
| `import-resume` | Parse a resume (.pdf/.docx/.txt) and update the user profile |
| `update-preferences` | Update an existing user profile's preferences |
| `match` | Match saved jobs against the user's profile, show top N |
| `show-matches` | Display stored match history for a user |
| `explain` | Explain why a specific job matched a user's profile |
| `export-matches` | Export personalized match results to JSON |

## Verification Workflow

When performing a live sync against public ATS APIs:

1. Call each documented endpoint with no authentication headers.
2. Record the HTTP status code per source — do not assume 200 means success.
3. Parse the actual JSON response; never invent job IDs, titles, locations,
   or application URLs.
4. Apply the entry-level filter: exclude senior/lead/staff/principal/
   manager roles, treat missing experience as unknown.
5. Assign `api_confirmed` only for records returned by an authoritative
   ATS feed; never treat an aggregator page (HTTP 200) as confirmation of
   an individual vacancy.
6. Insert records into SQLite with `provider + original_job_id` as the
   unique key.

---

## Test Framework

- All tests must use mocked API fixtures; no live external services.
- Run tests with `python -m pytest tests/ -v` using the interpreter where
  pytest is installed (not necessarily the system `python`).
- Cover each ATS response parser, duplicate prevention, entry-level
  filtering, missing experience, closed/blocked sources, invalid
  application URLs, JSON export, and accurate summary counts.
- When writing SQLite storage tests, call `storage.close()` before deleting
  the temp db file to avoid file-locking errors.
