"""CLI interface for JobCare Job Scout."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from storage import SQLiteStorage
from models.schemas import JobRecord, Filter, VerificationStatus, SearchRun
from filters.matcher import filter_jobs, matches_filters, Filters, count_filtered_summary
from verification.verifier import VerificationService

# Default employers from Test 4 discovery
DEFAULT_EMPLOYERS = [
    # Greenhouse (company, board_id, careers_url)
    {"provider": "greenhouse", "board_id": "bitgo", "careers_url": "https://boards.greenhouse.io/bitgo"},
    {"provider": "greenhouse", "board_id": "greenhouse", "careers_url": "https://boards.greenhouse.io/greenhouse"},
    # Lever (site, site)
    {"provider": "lever", "board_id": "drivetrain", "careers_url": "https://jobs.lever.co/drivetrain"},
    {"provider": "lever", "board_id": "smart-working-solutions", "careers_url": "https://jobs.lever.co/smart-working-solutions"},
    {"provider": "lever", "board_id": "hevodata", "careers_url": "https://jobs.lever.co/hevodata"},
    {"provider": "lever", "board_id": "mindtickle", "careers_url": "https://jobs.lever.co/mindtickle"},
    # Ashby (board_name, board_name)
    {"provider": "ashby", "board_id": "g2", "careers_url": "https://jobs.ashbyhq.com/g2"},
    {"provider": "ashby", "board_id": "airbound", "careers_url": "https://jobs.ashbyhq.com/airbound"},
]


def create_storage(db_path: str | None = None) -> SQLiteStorage:
    """Create and return a SQLiteStorage instance."""
    return SQLiteStorage(db_path)


def cmd_add_employer(args):
    """Add an employer to the registry."""
    storage = create_storage()
    # Parse provider
    provider_map = {
        "greenhouse": "greenhouse",
        "lever": "lever",
        "ashby": "ashby",
    }
    provider = provider_map.get(args.provider, args.provider.lower())

    # Get or create board_id (default to the argument value)
    board_id = args.board_id or args.careers_url.split("//")[-1].split("/")[0]

    try:
        employer = storage.add_employer(
            provider=provider,
            board_id=board_id,
            careers_url=args.careers_url,
            enabled=args.enabled,
            notes=args.notes,
        )
        print(f"✓ Added employer: {employer.provider} / {employer.board_id}")
        print(f"  Careers: {employer.careers_url}")
        print(f"  Enabled: {employer.enabled}")
    except Exception as e:
        print(f"✗ Error adding employer: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_employers(args):
    """List all employers in the registry."""
    storage = create_storage()
    employers = storage.list_employers(enabled_only=args.enabled_only)

    if not employers:
        print("No employers found.")
        return

    print(f"Found {len(employers)} employer(s):\n")
    for emp in employers:
        status = "✓" if emp.enabled else "✗"
        print(f"  [{status}] {emp.provider} / {emp.board_id}")
        print(f"      Careers: {emp.careers_url}")
        if emp.last_successful_sync:
            print(f"      Last sync: {emp.last_successful_sync}")
        if emp.notes:
            print(f"      Notes: {emp.notes}")


def cmd_sync(args):
    """Sync all enabled employers."""
    from adapters.greenhouse import GreenhouseAdapter
    from adapters.lever import LeverAdapter
    from adapters.ashby import AshbyAdapter
    from verification.verifier import VerificationService

    storage = create_storage()
    verifier = VerificationService()

    # Load preferences (max_jobs)
    max_jobs = storage.get_preference("max_jobs") or "100"
    try:
        max_jobs = int(max_jobs)
    except ValueError:
        max_jobs = 100

    # Build employer registry
    employers = storage.list_employers(enabled_only=args.enabled_only)
    if not employers:
        print("No enabled employers found. Use 'jobcare add-employer' first.")
        return

    # Import adapters dynamically
    adapters_map = {
        "greenhouse": (GreenhouseAdapter, "board_id"),
        "lever": (LeverAdapter, "site"),
        "ashby": (AshbyAdapter, "board_name"),
    }

    # Collect all jobs
    all_jobs = []
    all_errors = []
    skipped = []
    jobs_seen = set()

    for emp in employers:
        adapter_class, adapter_param = adapters_map.get(emp.provider)
        if not adapter_class:
            skipped.append(f"{emp.provider}/{emp.board_id}: no adapter")
            continue

        if adapter_param == "site":
            adapter = adapter_class(site=emp.board_id, careers_url=emp.careers_url)
        elif adapter_param == "board_name":
            adapter = adapter_class(board_name=emp.board_id, careers_url=emp.careers_url)
        else:
            adapter = adapter_class(board_id=emp.board_id, careers_url=emp.careers_url)

        jobs, errors = adapter.fetch_jobs()
        all_errors.extend(errors)

        for job in jobs:
            # Create stable unique key
            key = f"{job.provider.value}|{job.original_job_id}"
            if key in jobs_seen:
                continue
            jobs_seen.add(key)
            all_jobs.append(job)

        # Update last sync time
        storage.update_last_sync(emp.provider, emp.board_id, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

        if not jobs:
            skipped.append(f"{emp.provider}/{emp.board_id}: no jobs found")

    # Filter jobs based on preferences
    search_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filters = Filter()
    # Load saved preferences
    pref = storage.get_preference("career_profile")
    if pref:
        try:
            import json
            filters = Filter(**json.loads(pref))
        except json.JSONDecodeError:
            pass

    passed, failed = filter_jobs(all_jobs, filters)

    # Trim to max_jobs
    if len(passed) > max_jobs:
        passed = passed[:max_jobs]

    # Save jobs to database
    for job in passed:
        job.verified_at = search_at
        job.last_checked_at = search_at
        storage.upsert_job(job)

    # Save search run
    run = SearchRun(
        run_id=str(uuid.uuid4()),
        search_at=search_at,
        filters_applied=filters.__dict__ if hasattr(filters, "__dict__") else {},
        total_received=len(all_jobs),
        total_fetched=len(passed),
        total_filtered=len(failed),
    )
    storage.save_search_run(run)

    # Print summary
    print(f"Sync complete at {search_at}")
    print(f"  Received: {len(all_jobs)}")
    print(f"  Filtered: {len(passed)}")
    print(f"  Errors: {len(all_errors)}")
    if skipped:
        print(f"  Skipped: {len(skipped)}")
        for s in skipped:
            print(f"    - {s}")
    print(f"  Last sync: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")


def cmd_show_verified(args):
    """Show verified jobs (api_confirmed and verified statuses)."""
    from filters.matcher import count_filtered_summary

    storage = create_storage()

    # Query verified jobs (individual page confirmed)
    verified_jobs = storage.get_verified_jobs()

    # Query API-confirmed jobs (returned by authoritative API feed, not individually verified)
    api_confirmed_jobs = storage.get_jobs_by_status("api_confirmed")

    # Combine: verified first, then api_confirmed
    jobs = verified_jobs + api_confirmed_jobs

    # Filter by location if requested
    if args.location:
        jobs = [j for j in jobs if args.location.lower() in j.location.lower()]

    # Filter by employment type if requested
    if args.type:
        jobs = [j for j in jobs if args.type.lower() in (j.employment_type or "").lower()]

    # Filter by experience range
    if args.experience_min or args.experience_max:
        jobs = [
            j for j in jobs
            if (j.experience or "").lower() != "" and (
                args.experience_min is None or int(j.experience.split("-")[0].strip()) >= args.experience_min,
                args.experience_max is None or int(j.experience.split("-")[1].strip()) <= args.experience_max,
            )
        ]

    # Separate for display
    verified_display = [j for j in jobs if j.verification_status == "verified" or j.verification_status.value == "verified"]
    api_confirmed_display = [j for j in jobs if j.verification_status == "api_confirmed" or j.verification_status.value == "api_confirmed"]

    if not jobs:
        print("No verified jobs found.")
        return

    print(f"Verified jobs ({len(verified_display)})+[API-confirmed {len(api_confirmed_display)}]:\n")

    for job in verified_display:
        print(f"  • [verified] {job.company} — {job.title}")
        print(f"    Location: {job.location}")
        print(f"    Experience: {job.experience or 'Not specified'}")
        print(f"    Application: {job.application_url}")
        print()

    if api_confirmed_display:
        print(f"--- API-confirmed (returned by authoritative ATS feed, not individually verified) ---")
        for job in api_confirmed_display:
            print(f"  • [api_confirmed] {job.company} — {job.title}")
            print(f"    Location: {job.location}")
            print(f"    Experience: {job.experience or 'Not specified'}")
            print(f"    Application: {job.application_url}")
            print()


def cmd_search(args):
    """Search saved jobs."""
    from models.schemas import Filter

    storage = create_storage()
    jobs = storage.search_jobs(
        title_contains=args.title,
        location_contains=args.location,
        verification_status=args.status,
    )

    # Apply filters from arguments
    if args.title or args.location:
        pass

    # Apply user preferences
    pref = storage.get_preference("career_profile")
    filters = Filter()
    if pref:
        import json
        try:
            filters = Filter(**json.loads(pref))
        except json.JSONDecodeError:
            pass

    if args.passed_only:
        from filters.matcher import filter_jobs, Filters
        filtered, failed = filter_jobs(jobs, Filter(
            desired_roles=filters.desired_roles or ["software engineer"],
            locations=filters.locations,
            remote_preference=filters.remote_preference,
            experience_min=filters.experience_min,
            experience_max=filters.experience_max,
            skills=filters.skills,
            employment_type=filters.employment_type,
        ))
        jobs = filtered

    if not jobs:
        print("No jobs found matching your criteria.")
        return

    # Print summary
    print(f"Found {len(jobs)} jobs:\n")
    for job in jobs:
        print(f"  • {job.company} — {job.title}")
        print(f"    Location: {job.location}")
        print(f"    Experience: {job.experience or 'Not specified'}")
        print(f"    Application: {job.application_url}")
        print()


def cmd_export(args):
    """Export results to JSON."""
    from models.schemas import JobRecord
    import tempfile

    storage = create_storage()
    provider = args.provider.lower() if args.provider else None
    title_contains = args.title or None
    location_contains = args.location or None
    verification_status = args.status or None

    jobs = storage.search_jobs(
        provider=provider,
        title_contains=title_contains,
        location_contains=location_contains,
        verification_status=verification_status,
    )

    # Convert to dict
    results = [j.to_dict() for j in jobs]

    # Write to file
    if args.output:
        output_path = args.output
    else:
        output_path = tempfile.mktemp(suffix=".json")

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Exported {len(results)} jobs to {output_path}")


def cmd_view_failed(args):
    """View failed sources."""
    storage = create_storage()
    failed = storage.get_failed_sources()

    if not failed:
        print("No failed sources found.")
        return

    print(f"Failed sources ({len(failed)}):\n")
    for src in failed:
        print(f"  • {src['provider']} / {src['board_id']}")
        print(f"    Created: {src['created_at']}")


def cmd_set_preferences(args):
    """Set user preferences (career profile)."""
    storage = create_storage()
    import json

    prefs = {}
    if args.roles:
        prefs["desired_roles"] = args.roles
    if args.locations:
        prefs["locations"] = args.locations
    if args.remote:
        prefs["remote_preference"] = True
    if args.experience_min is not None:
        prefs["experience_min"] = args.experience_min
    if args.experience_max is not None:
        prefs["experience_max"] = args.experience_max
    if args.skills:
        prefs["skills"] = args.skills
    if args.type:
        prefs["employment_type"] = args.type

    if prefs:
        storage.save_preference("career_profile", json.dumps(prefs))
        print(f"✓ Saved {len(prefs)} preference(s).")
    else:
        print("No preferences set.")


def cmd_status(args):
    """Show skill status summary."""
    storage = create_storage()
    employers = storage.list_employers(enabled_only=True)
    jobs = storage.search_jobs()
    runs = storage.list_search_runs()

    print("=== JobCare Job Scout Status ===")
    print(f"Employers: {len(employers)}")
    print(f"Jobs: {len(jobs)}")
    print(f"Search runs: {len(runs)}")

    if runs:
        latest = runs[0]
        print(f"Latest run: {latest.run_id}")
        print(f"  Received: {latest.total_received}, Filtered: {latest.total_filtered}")

    print("\n=== Employer Registry ===")
    for emp in employers:
        print(f"  ✓ {emp.provider} / {emp.board_id}")
        if emp.last_successful_sync:
            print(f"    Last sync: {emp.last_successful_sync}")


def cmd_create_profile(args):
    """Create a user profile."""
    from storage.user_profile import UserProfileStorage
    from models.schemas import UserProfile

    storage = UserProfileStorage()

    # Generate user ID if not provided
    user_id = args.user_id
    if not user_id:
        # Auto-generate
        user_id = f"user_{uuid.uuid4().hex[:8]}"

    # Get skills from args
    skills = args.skills or []
    projects = args.projects or []
    work_exp = args.work_experience or []

    profile = UserProfile(
        user_id=user_id,
        education=args.education or "",
        graduation_year=args.graduation_year,
        technical_skills=skills,
        projects=projects,
        work_experience=work_exp,
        preferred_roles=args.preferred_roles or [],
        preferred_locations=args.preferred_locations or [],
        remote_preference=args.remote,
        employment_type=args.type,
        resume_file=args.resume,
        created_at="",
        updated_at="",
    )

    # Set timestamps
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile.created_at = now
    profile.updated_at = now

    storage.create_profile(profile)

    print(f"✓ Created profile for user: {user_id}")
    print(f"  Education: {profile.education or 'Not specified'}")
    print(f"  Skills: {', '.join(profile.technical_skills) if profile.technical_skills else 'None'}")
    print(f"  Preferred roles: {', '.join(profile.preferred_roles) if profile.preferred_roles else 'None'}")


def cmd_import_resume(args):
    """Import and parse a resume file."""
    from storage.user_profile import UserProfileStorage
    from resume.parser import ResumeParser

    storage = UserProfileStorage()

    # Parse the resume
    parser = ResumeParser()
    resume = parser.parse(args.file)

    # Assign user ID if not set in resume
    resume.user_id = args.user_id

    # Save the resume
    storage.save_resume(resume)

    # Update the profile with resume data
    profile = storage.get_profile(args.user_id)
    if profile:
        # Update skills from resume
        profile.technical_skills = resume.skills
        profile.education = resume.education
        profile.graduation_year = resume.graduation_year
        profile.projects = resume.projects
        profile.work_experience = resume.work_experience
        profile.resume_file = args.file

        # Update timestamp
        profile.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        storage.update_profile(profile)

        print(f"✓ Parsed resume and updated profile: {args.file}")
        print(f"  User: {args.user_id}")
        print(f"  Skills found: {len(resume.skills)}")
        print(f"  Education: {profile.education or 'Not specified'}")
        print(f"  Projects: {len(profile.projects)}")
        print(f"  Work Experience: {len(profile.work_experience)}")
        print(f"  Certifications: {len(resume.certifications)}")
    else:
        # Create a new profile from resume data
        from models.schemas import UserProfile
        profile = UserProfile(
            user_id=args.user_id,
            education=resume.education,
            graduation_year=resume.graduation_year,
            technical_skills=resume.skills,
            projects=resume.projects,
            work_experience=resume.work_experience,
            resume_file=args.file,
        )
        storage.create_profile(profile)
        print(f"✓ Created profile and imported resume: {args.file}")
        print(f"  User: {args.user_id}")
        print(f"  Skills found: {len(resume.skills)}")
        print(f"  Education: {resume.education or 'Not specified'}")
        print(f"  Projects: {len(resume.projects)}")
        print(f"  Work Experience: {len(resume.work_experience)}")
        print(f"  Certifications: {len(resume.certifications)}")


def cmd_update_preferences(args):
    """Update user profile preferences."""
    from storage.user_profile import UserProfileStorage
    from models.schemas import UserProfile
    from datetime import datetime, timezone

    storage = UserProfileStorage()

    profile = storage.get_profile(args.user_id)
    if not profile:
        print(f"✗ Profile not found: {args.user_id}")
        return

    # Update fields
    if args.education is not None:
        profile.education = args.education
    if args.graduation_year is not None:
        profile.graduation_year = args.graduation_year
    if args.skills is not None:
        profile.technical_skills = args.skills
    if args.projects is not None:
        profile.projects = args.projects
    if args.work_experience is not None:
        profile.work_experience = args.work_experience
    if args.preferred_roles is not None:
        profile.preferred_roles = args.preferred_roles
    if args.preferred_locations is not None:
        profile.preferred_locations = args.preferred_locations
    if args.remote:
        profile.remote_preference = True
    if args.type:
        profile.employment_type = args.type
    if args.resume:
        profile.resume_file = args.resume

    # Update timestamp
    profile.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    storage.update_profile(profile)

    print(f"✓ Updated profile for user: {args.user_id}")


def cmd_match(args):
    """Match saved jobs against user profile."""
    from storage.user_profile import UserProfileStorage
    from storage import SQLiteStorage
    from matching.matcher import JobMatcher
    from models.schemas import JobRecord

    user_storage = UserProfileStorage()
    job_storage = SQLiteStorage()

    profile = user_storage.get_profile(args.user_id)
    if not profile:
        print(f"✗ Profile not found: {args.user_id}")
        return

    if profile and profile.reviewed_at is None:
        print("Profile is not reviewed. Review and approve it before matching.")
        job_storage.close()
        user_storage.close()
        return

    print(f"Matching jobs for user: {args.user_id}")

    # Load all jobs
    jobs = job_storage.search_jobs(enabled=True)
    print(f"  Found {len(jobs)} jobs to match")

    # Run matching
    matcher = JobMatcher()
    results = matcher.match_jobs(jobs, profile, user_storage)

    # Ineligible records stay in match history but are not shown as recommendations.
    recommendations = [r for r in results if r.eligibility_status != "ineligible"]
    top_results = recommendations[:args.top]

    print(f"\n=== Top {len(top_results)} Matches ===")
    for i, result in enumerate(top_results, 1):
        print(f"\n{i}. {result.job.company} — {result.job.title}")
        print(f"   Match Score: {result.match_score}/1.00")
        print(f"   Eligibility: {result.eligibility_status}")
        print(f"   Matching skills: {', '.join(result.matching_skills) if result.matching_skills else 'None'}")
        if result.missing_skills:
            print(f"   Missing skills: {', '.join(result.missing_skills)}")
        for line in result.explanation:
            print(f"   → {line}")
        if result.application_url:
            print(f"   Apply: {result.application_url}")

    # Summary
    eligible = sum(1 for r in results if r.eligibility_status == "eligible")
    unknown = sum(1 for r in results if r.eligibility_status == "unknown")
    ineligible = sum(1 for r in results if r.eligibility_status == "ineligible")
    print(f"\nSummary: {eligible} eligible, {unknown} unknown, {ineligible} ineligible")

    job_storage.close()
    user_storage.close()


def cmd_show_matches(args):
    """Display stored match history."""
    from storage.user_profile import UserProfileStorage

    storage = UserProfileStorage()
    matches = storage.get_match_history(args.user_id)

    if not matches:
        print(f"No match history found for user: {args.user_id}")
        return

    print(f"\n=== Match History for {args.user_id} ===")
    for match in matches:
        print(f"\n  Score: {match.match_score:.2f} - {match.eligibility_status}")
        print(f"  Job: {match.job_provider} / {match.original_job_id}")
        if match.explanation:
            for line in match.explanation:
                print(f"  → {line}")


def cmd_explain(args):
    """Explain why a job matched."""
    from storage.user_profile import UserProfileStorage
    from matching.matcher import JobMatcher

    user_storage = UserProfileStorage()
    job_storage = SQLiteStorage()

    profile = user_storage.get_profile(args.user_id)
    if not profile:
        print(f"✗ Profile not found: {args.user_id}")
        job_storage.close()
        user_storage.close()
        return

    # Get the job
    job = job_storage.get_job(args.job_provider, args.job_id)
    if not job:
        print(f"✗ Job not found: {args.job_provider}/{args.job_id}")
        job_storage.close()
        user_storage.close()
        return

    # Recompute match
    matcher = JobMatcher()
    result = matcher._match_single(job, profile, job_storage)

    if result:
        print(f"Job: {result.job.company} — {result.job.title}")
        print(f"Match Score: {result.match_score:.2f}")
        print(f"Eligibility: {result.eligibility_status}")
        print(f"\nExplanation:")
        for line in result.explanation:
            print(f"  • {line}")
        if result.matching_skills:
            print(f"\nMatching skills: {', '.join(result.matching_skills)}")
        if result.missing_skills:
            print(f"\nMissing skills: {', '.join(result.missing_skills)}")
        if result.application_url:
            print(f"\nApplication URL: {result.application_url}")

    job_storage.close()
    user_storage.close()


def cmd_export_matches(args):
    """Export personalized match results."""
    from storage.user_profile import UserProfileStorage
    from matching.matcher import JobMatcher
    from storage import SQLiteStorage
    from models.schemas import JobRecord
    import json

    user_storage = UserProfileStorage()
    job_storage = SQLiteStorage()

    profile = user_storage.get_profile(args.user_id)
    if not profile:
        print(f"✗ Profile not found: {args.user_id}")
        job_storage.close()
        user_storage.close()
        return

    # Load jobs
    jobs = job_storage.search_jobs(enabled=True)

    # Match
    matcher = JobMatcher()
    results = matcher.match_jobs(jobs, profile, job_storage)

    # Format output
    output = []
    for result in results:
        output.append({
            "job": {
                "company": result.job.company,
                "title": result.job.title,
                "location": result.job.location,
                "application_url": result.application_url,
            },
            "match_score": result.match_score,
            "eligibility_status": result.eligibility_status,
            "matching_skills": result.matching_skills,
            "missing_skills": result.missing_skills,
            "explanation": result.explanation,
        })

    # Write to file
    if args.output:
        output_path = args.output
    else:
        import tempfile
        output_path = tempfile.mktemp(suffix=".json")

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✓ Exported {len(output)} matches to {output_path}")

    job_storage.close()
    user_storage.close()

    print("\n=== Employer Registry ===")
    for emp in employers:
        print(f"  ✓ {emp.provider} / {emp.board_id}")
        if emp.last_successful_sync:
            print(f"    Last sync: {emp.last_successful_sync}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="jobcare",
        description="JobCare AI Job Scout — autonomous job discovery from ATS APIs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add-employer
    p_add = subparsers.add_parser("add-employer", help="Add an employer to the registry")
    p_add.add_argument("--provider", required=True, help="ATS provider: greenhouse, lever, or ashby")
    p_add.add_argument("--board-id", help="Board identifier")
    p_add.add_argument("--careers-url", required=True, help="Careers URL")
    p_add.add_argument("--enabled", action="store_true", help="Enable the employer")
    p_add.add_argument("--notes", help="Notes about the employer")
    p_add.set_defaults(func=cmd_add_employer)

    # list-employers
    p_list = subparsers.add_parser("list-employers", help="List all employers")
    p_list.add_argument("--enabled-only", action="store_true", help="Show only enabled employers")
    p_list.set_defaults(func=cmd_list_employers)

    # sync
    p_sync = subparsers.add_parser("sync", help="Sync all enabled employers")
    p_sync.add_argument("--enabled-only", action="store_true", help="Only sync enabled employers")
    p_sync.set_defaults(func=cmd_sync)

    # show-verified
    p_show = subparsers.add_parser("show-verified", help="Show verified jobs")
    p_show.add_argument("--location", help="Filter by location")
    p_show.add_argument("--type", help="Filter by employment type")
    p_show.add_argument("--experience-min", type=int)
    p_show.add_argument("--experience-max", type=int)
    p_show.set_defaults(func=cmd_show_verified)

    # search
    p_search = subparsers.add_parser("search", help="Search saved jobs")
    p_search.add_argument("--title", help="Filter by title containing")
    p_search.add_argument("--location", help="Filter by location")
    p_search.add_argument("--status", help="Filter by verification status")
    p_search.add_argument("--passed-only", action="store_true", help="Only show passed jobs")
    p_search.set_defaults(func=cmd_search)

    # export
    p_export = subparsers.add_parser("export", help="Export results to JSON")
    p_export.add_argument("--provider", help="Filter by provider")
    p_export.add_argument("--title", help="Filter by title")
    p_export.add_argument("--location", help="Filter by location")
    p_export.add_argument("--status", help="Filter by verification status")
    p_export.add_argument("--output", help="Output file path")
    p_export.set_defaults(func=cmd_export)

    # view-failed
    p_failed = subparsers.add_parser("view-failed", help="View failed sources")
    p_failed.set_defaults(func=cmd_view_failed)

    # set-preferences
    p_pref = subparsers.add_parser("set-preferences", help="Set career profile preferences")
    p_pref.add_argument("--roles", nargs="*", help="Desired roles")
    p_pref.add_argument("--locations", nargs="*", help="Locations")
    p_pref.add_argument("--remote", action="store_true", help="Remote preference")
    p_pref.add_argument("--experience-min", type=int)
    p_pref.add_argument("--experience-max", type=int)
    p_pref.add_argument("--skills", nargs="*", help="Required skills")
    p_pref.add_argument("--type", help="Employment type")
    p_pref.set_defaults(func=cmd_set_preferences)

    # status
    p_status = subparsers.add_parser("status", help="Show status summary")
    p_status.set_defaults(func=cmd_status)

    # User profile commands (Phase 2)
    # create-profile
    p_create = subparsers.add_parser("create-profile", help="Create a user profile")
    p_create.add_argument("--user-id", required=True, help="Unique user ID")
    p_create.add_argument("--education", help="Education (e.g., 'B.Tech in Computer Science')")
    p_create.add_argument("--graduation-year", type=int, help="Graduation year")
    p_create.add_argument("--skills", nargs="*", help="Technical skills")
    p_create.add_argument("--projects", nargs="*", help="Projects")
    p_create.add_argument("--work-experience", nargs="*", help="Work experience entries")
    p_create.add_argument("--preferred-roles", nargs="*", help="Preferred job roles")
    p_create.add_argument("--preferred-locations", nargs="*", help="Preferred locations")
    p_create.add_argument("--remote", action="store_true", help="Remote preference")
    p_create.add_argument("--type", help="Employment type (full-time, part-time, contract)")
    p_create.add_argument("--resume", help="Resume file path")
    p_create.set_defaults(func=cmd_create_profile)

    # import-resume
    p_import = subparsers.add_parser("import-resume", help="Import and parse a resume file")
    p_import.add_argument("--user-id", required=True, help="User ID")
    p_import.add_argument("--file", required=True, help="Path to resume file (.pdf or .docx)")
    p_import.set_defaults(func=cmd_import_resume)

    # update-preferences
    p_update = subparsers.add_parser("update-preferences", help="Update user profile preferences")
    p_update.add_argument("--user-id", required=True, help="User ID")
    p_update.add_argument("--education", help="Education")
    p_update.add_argument("--graduation-year", type=int, help="Graduation year")
    p_update.add_argument("--skills", nargs="*", help="Technical skills")
    p_update.add_argument("--projects", nargs="*", help="Projects")
    p_update.add_argument("--work-experience", nargs="*", help="Work experience entries")
    p_update.add_argument("--preferred-roles", nargs="*", help="Preferred job roles")
    p_update.add_argument("--preferred-locations", nargs="*", help="Preferred locations")
    p_update.add_argument("--remote", action="store_true", help="Remote preference")
    p_update.add_argument("--type", help="Employment type")
    p_update.add_argument("--resume", help="Resume file path")
    p_update.set_defaults(func=cmd_update_preferences)

    # match
    p_match = subparsers.add_parser("match", help="Match saved jobs against user profile")
    p_match.add_argument("--user-id", required=True, help="User ID")
    p_match.add_argument("--top", type=int, default=10, help="Number of top matches to show")
    p_match.set_defaults(func=cmd_match)

    # show-matches
    p_show = subparsers.add_parser("show-matches", help="Display stored match history")
    p_show.add_argument("--user-id", required=True, help="User ID")
    p_show.set_defaults(func=cmd_show_matches)

    # explain
    p_explain = subparsers.add_parser("explain", help="Explain why a job matched")
    p_explain.add_argument("--user-id", required=True, help="User ID")
    p_explain.add_argument("--job-provider", required=True, help="Job provider")
    p_explain.add_argument("--job-id", required=True, help="Job original ID")
    p_explain.set_defaults(func=cmd_explain)

    # export-matches
    p_export = subparsers.add_parser("export-matches", help="Export personalized match results")
    p_export.add_argument("--user-id", required=True, help="User ID")
    p_export.add_argument("--output", help="Output file path")
    p_export.set_defaults(func=cmd_export_matches)

    return parser


def main(argv: Optional[list[str]] = None):
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
