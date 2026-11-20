"""Test fixtures with mocked API responses for the JobCare Job Scout."""

from unittest.mock import Mock, patch

# === Greenhouse mock fixtures ===
GREENHOUSE_BITGO_JOBS = {
    "jobs": [
        {
            "id": 7344201002,
            "title": "Backend Engineer E3 - Ecosystem",
            "company_name": "BitGo",
            "location": {"name": "India"},
            "absolute_url": "https://job-boards.greenhouse.io/bitgo/jobs/7344201002",
            "requisition_id": "1124",
            "content": "Backend Engineer E3 for blockchain infrastructure. Experience with server-side languages like TypeScript/Node. SQL databases like Postgres. RESTful API design.",
            "workplace_type": "Full Time",
        },
        {
            "id": 8869949002,
            "title": "Backend Engineer E3 - India",
            "company_name": "BitGo",
            "location": {"name": "India"},
            "absolute_url": "https://job-boards.greenhouse.io/bitgo/jobs/8869949002",
            "requisition_id": "1124",
            "content": "6+ years of professional back-end and server-side development experience. Strong experience with TypeScript and Node.",
            "workplace_type": "Full Time",
        },
        {
            "id": 8879340002,
            "title": "Mobile Engineer E2 - (React Native)",
            "company_name": "BitGo",
            "location": {"name": "India"},
            "absolute_url": "https://job-boards.greenhouse.io/bitgo/jobs/8879340002",
            "requisition_id": "1125",
            "content": "React Native mobile engineer for cross-platform fintech app. Experience with JavaScript, React Native, and mobile development.",
            "workplace_type": "Full Time",
        },
    ]
}

GREENHOUSE_GREENHOUSE_JOBS = {
    "jobs": [
        {
            "id": 7000000001,
            "title": "Engineering Intern",
            "company_name": "Greenhouse",
            "location": {"name": "United States"},
            "absolute_url": "https://job-boards.greenhouse.io/greenhouse/jobs/7000000001",
            "requisition_id": "2026-P1",
            "content": "Engineering Intern for Greenhouse's product team. Experience with Python, Go, and Kubernetes.",
            "workplace_type": "Internship",
        }
    ]
}

# === Lever mock fixtures ===
LEVCO_JOBS = [
    {
        "id": "test-1",
        "text": "Engineering Intern",
        "company": "Test Company",
        "country": "IN",
        "workplaceType": "Internship",
        "hostedUrl": "https://jobs.lever.co/test/1",
        "applyUrl": "https://jobs.lever.co/test/1/apply",
        "descriptionPlain": "Engineering Intern with 0-1 years of experience. Build and deploy software applications.",
        "description": "<p>Engineering Intern with 0-1 years of experience. Build and deploy software applications.</p>",
    }
]

LEVCO_NO_EXP_JOBS = [
    {
        "id": "test-2",
        "text": "Backend Engineer",
        "company": "Test Company",
        "country": "IN",
        "workplaceType": "Full Time",
        "hostedUrl": "https://jobs.lever.co/test/2",
        "applyUrl": "https://jobs.lever.co/test/2/apply",
        "descriptionPlain": "Backend Engineer for cloud infrastructure. Build and maintain distributed systems.",
        "description": "<p>Backend Engineer for cloud infrastructure. Build and maintain distributed systems.</p>",
    }
]

# === Ashby mock fixtures ===
ASHBY_G2_JOBS = {
    "jobs": [
        {
            "id": "g2-1",
            "title": "Data Engineer II",
            "company": "G2",
            "location": "Bengaluru",
            "jobUrl": "https://jobs.ashbyhq.com/g2/g2-1",
            "applyUrl": "https://jobs.ashbyhq.com/g2/g2-1/application",
            "employmentType": "Full Time",
            "descriptionPlain": "Data Engineer II for G2's data platform. Experience with SQL, Python, and data pipelines.",
            "description": "<p>Data Engineer II for G2's data platform. Experience with SQL, Python, and data pipelines.</p>",
        },
        {
            "id": "g2-2",
            "title": "Senior Software Engineer - RoR",
            "company": "G2",
            "location": "Bengaluru",
            "jobUrl": "https://jobs.ashbyhq.com/g2/g2-2",
            "applyUrl": "https://jobs.ashbyhq.com/g2/g2-2/application",
            "employmentType": "Full Time",
            "descriptionPlain": "Senior Software Engineer with 5+ years of Ruby on Rails experience.",
            "description": "<p>Senior Software Engineer with 5+ years of Ruby on Rails experience.</p>",
        }
    ]
}

ASHBY_AIRBND_JOBS = {
    "jobs": [
        {
            "id": "airb-1",
            "title": "Embedded Software Engineer",
            "company": "Airbound",
            "location": "Bangalore",
            "jobUrl": "https://jobs.ashbyhq.com/airbound/airb-1",
            "applyUrl": "https://jobs.ashbyhq.com/airbound/airb-1/application",
            "employmentType": "Full Time",
            "descriptionPlain": "Embedded Software Engineer with experience in C++ and real-time systems.",
            "description": "<p>Embedded Software Engineer with experience in C++ and real-time systems.</p>",
        }
    ]
}

# === Storage mock fixtures ===
SAMPLE_JOB_DICT = {
    "provider": "lever",
    "original_job_id": "test-1",
    "company": "Test Company",
    "title": "Engineering Intern",
    "location": "IN",
    "experience": "0-1 years",
    "skills": ["Python", "JavaScript"],
    "salary": None,
    "employment_type": "Internship",
    "job_url": "https://jobs.lever.co/test/1",
    "application_url": "https://jobs.lever.co/test/1/apply",
    "source_api_url": "https://api.lever.co/v0/postings/test?mode=json",
    "verification_status": "api_confirmed",
    "verification_evidence": "Returned by Lever Postings API (200 OK) without authentication.",
    "verified_at": "2026-10-24T00:00:00Z",
    "last_checked_at": "2026-10-24T00:00:00Z",
    "raw_data": {},
}

SAMPLE_EMPLOYER_DICT = {
    "provider": "lever",
    "board_id": "drivetrain",
    "careers_url": "https://jobs.lever.co/drivetrain",
    "enabled": True,
    "last_successful_sync": None,
    "created_at": "2026-10-24T00:00:00Z",
    "notes": "Entry-level software roles",
}
