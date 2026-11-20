"""Intelligent job matching engine.

Builds a deterministic matching engine that evaluates job opportunities
based on user profile data:
- Skill overlap
- Role relevance
- Experience eligibility
- Location preference
- Education eligibility

Optional local Sentence Transformers cosine similarity complements the
deterministic weighted score. A failed model load leaves deterministic matching.

Configuration: weights for each matching dimension can be adjusted.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from models.schemas import JobRecord, MatchResult, MatchHistory, UserProfile
from storage.user_profile import UserProfileStorage
from storage import SQLiteStorage
from matching.semantic import Encoder, job_searchable_text
from filters.matcher import classify_experience


class MatchingError(Exception):
    """Exception raised when matching fails."""

    pass


class JobMatcher:
    """Explainable weighted matcher with optional local semantic scoring."""

    ALGORITHM_VERSION = "jobcare-match-v1"

    # Default weights for each matching dimension (0.0 to 1.0)
    DEFAULT_WEIGHTS = {
        "skill_overlap": 0.4,
        "role_relevance": 0.2,
        "experience_eligibility": 0.2,
        "location_preference": 0.1,
        "education_eligibility": 0.1,
    }

    # Eligibility thresholds
    MIN_MATCH_SCORE = 0.0
    HIGH_MATCH_THRESHOLD = 0.7
    MEDIUM_MATCH_THRESHOLD = 0.4

    def __init__(self, weights: dict[str, float] | None = None, *,
                 semantic_encoder: Encoder | None = None, semantic_weight: float = 0.30,
                 allow_deterministic_fallback: bool = True, eligibility_filters: Any = None):
        self.weights = weights or self.DEFAULT_WEIGHTS
        if not 0.0 <= semantic_weight <= 1.0:
            raise ValueError("semantic_weight must be between 0 and 1")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("deterministic weights must sum to 1.0")
        self.semantic_encoder = semantic_encoder
        self.semantic_weight = semantic_weight
        self.allow_deterministic_fallback = allow_deterministic_fallback
        self.eligibility_filters = eligibility_filters

    def match_jobs(
        self,
        jobs: list[JobRecord],
        user_profile: UserProfile,
        storage: UserProfileStorage,
    ) -> list[MatchResult]:
        """Match jobs against the user profile.

        Args:
            jobs: List of job records to match.
            user_profile: User profile containing preferences and qualifications.
            storage: UserProfileStorage for saving match history.

        Returns:
            List of MatchResult objects sorted by match score (highest first).
        """
        if user_profile.reviewed_at is None:
            raise MatchingError("Candidate profile must be reviewed before matching")

        semantic_scores: list[float] | None = None
        model_version = ""
        if self.semantic_encoder is not None and jobs:
            try:
                semantic_scores = self.semantic_encoder.score_jobs(user_profile, jobs)
                if len(semantic_scores) != len(jobs):
                    raise MatchingError("Semantic encoder returned a different number of scores than jobs")
                model_version = self.semantic_encoder.model_version
            except Exception as exc:
                if not self.allow_deterministic_fallback:
                    raise MatchingError(f"Semantic matching failed: {exc}") from exc

        results = []
        for index, job in enumerate(jobs):
            result = self._match_single(job, user_profile, storage,
                                        semantic_scores[index] if semantic_scores is not None else None,
                                        model_version)
            if result:
                results.append(result)

        # Sort by match score descending
        results.sort(key=lambda r: r.match_score, reverse=True)
        return results

    def _apply_eligibility(self, job: JobRecord, profile: UserProfile, result: MatchResult) -> bool:
        """Apply explicit candidate criteria; missing evidence remains unknown and is retained."""
        filters = self.eligibility_filters
        if filters is None:
            from filters.matcher import Filters
            filters = Filters(
                desired_roles=profile.preferred_roles,
                locations=profile.preferred_locations,
                remote_preference=profile.remote_preference,
                employment_type=profile.employment_type,
            )
        reasons: list[str] = []
        unknown = False
        if filters.desired_roles and job.title:
            if not any(role.casefold() in job.title.casefold() for role in filters.desired_roles):
                reasons.append("role does not match requested roles")
        elif filters.desired_roles:
            unknown = True
        if filters.locations and not filters.remote_preference:
            if job.location:
                if not any(loc.casefold() in job.location.casefold() for loc in filters.locations):
                    reasons.append("job location does not match preferred locations")
            else:
                unknown = True
        if filters.employment_type:
            if job.employment_type:
                if filters.employment_type.casefold() not in job.employment_type.casefold():
                    reasons.append("employment type does not match requested type")
            else:
                unknown = True
        exp = classify_experience(job.experience)
        if filters.experience_min is not None or filters.experience_max is not None:
            if exp is None:
                unknown = True
            elif ((filters.experience_min is not None and exp < filters.experience_min) or
                  (filters.experience_max is not None and exp > filters.experience_max)):
                reasons.append("experience requirement is outside requested range")
        result.eligibility_status = "ineligible" if reasons else "unknown" if unknown else "eligible"
        result.explanation.append("Eligibility: " + ("; ".join(reasons) if reasons else
                                  "insufficient listing evidence" if unknown else "all available criteria matched"))
        return not reasons

    def _match_single(
        self,
        job: JobRecord,
        user_profile: UserProfile,
        storage: SQLiteStorage,
        semantic_score: float | None = None,
        model_version: str = "",
    ) -> Optional[MatchResult]:
        """Match a single job against the user profile."""
        explanation = []
        # 1. Skill overlap - extract skills from description if needed
        skill_overlap = self._compute_skill_overlap(job, user_profile, explanation)
        searchable_lower = job_searchable_text(job).lower()
        job_skill_text = " ".join(job.skills).lower() if job.skills else searchable_lower
        matching_skills = [skill for skill in user_profile.technical_skills
                           if skill.strip() and (skill.lower().strip() in job_skill_text or
                                                 any(alias in job_skill_text for alias in self._get_skill_aliases(skill)))]
        missing_skills = [skill for skill in user_profile.technical_skills if skill not in matching_skills]

        # 2. Role relevance
        role_relevance = self._compute_role_relevance(job, user_profile, explanation)

        # 3. Experience eligibility
        experience_eligibility = self._compute_experience_eligibility(job, user_profile, explanation)

        # 4. Location preference
        location_score = self._compute_location_score(job, user_profile, explanation)

        # 5. Education eligibility
        education_score = self._compute_education_score(job, user_profile, explanation)

        # Compute weighted match score
        deterministic_score = (
            self.weights.get("skill_overlap", 0.4) * skill_overlap +
            self.weights.get("role_relevance", 0.2) * role_relevance +
            self.weights.get("experience_eligibility", 0.2) * experience_eligibility +
            self.weights.get("location_preference", 0.1) * location_score +
            self.weights.get("education_eligibility", 0.1) * education_score
        )
        score = deterministic_score
        if semantic_score is not None:
            semantic_score = max(0.0, min(1.0, float(semantic_score)))
            score = (1.0 - self.semantic_weight) * deterministic_score + self.semantic_weight * semantic_score
            explanation.append(
                f"Combined score: {1.0-self.semantic_weight:.0%} deterministic ({deterministic_score:.2f}) + "
                f"{self.semantic_weight:.0%} semantic ({semantic_score:.2f}); model {model_version}"
            )
        else:
            explanation.append(f"Deterministic score: {deterministic_score:.2f}; semantic score unavailable")

        # Determine eligibility status
        eligibility_status = self._determine_eligibility(
            skill_overlap, role_relevance, experience_eligibility, location_score, education_score
        )

        # Only return matches above minimum threshold
        if score < self.MIN_MATCH_SCORE:
            return None

        # Get application URL
        application_url = job.application_url or job.job_url

        match_result = MatchResult(
            job=job,
            match_score=round(max(0.0, min(1.0, score)), 4),
            matching_skills=matching_skills,
            missing_skills=missing_skills,
            eligibility_status=eligibility_status,
            explanation=explanation,
            application_url=application_url,
            deterministic_score=round(deterministic_score, 4),
            semantic_score=semantic_score if semantic_score is not None else 0.0,
            model_version=model_version,
            algorithm_version=self.ALGORITHM_VERSION,
        )
        self._apply_eligibility(job, user_profile, match_result)

        # Save to match history
        match_history = MatchHistory(
            user_id=user_profile.user_id,
            job_provider=job.provider.value,
            original_job_id=job.original_job_id,
            match_score=score,
            eligibility_status=match_result.eligibility_status,
            explanation=explanation,
            semantic_score=semantic_score,
            model_version=model_version,
            algorithm_version=self.ALGORITHM_VERSION,
        )
        storage.save_match(match_history)

        return match_result

    def _compute_skill_overlap(
        self,
        job: JobRecord,
        user_profile: UserProfile,
        explanation: list[str],
    ) -> float:
        """Compute skill overlap between job and user profile."""
        job_skills = {s.lower() for s in job.skills}

        # Extract skills from description if the skills field is not useful
        # (i.e., if skills contain large text blocks instead of keywords)
        if len(job_skills) > 50:  # Likely raw description
            extracted = self._extract_skills_from_description(job, user_profile)
            if extracted:
                job_skills = {s.lower() for s in extracted}

        if not job_skills:
            searchable = job_searchable_text(job).lower()
            job_skills = {skill.lower().strip() for skill in user_profile.technical_skills
                          if skill.strip() and skill.lower().strip() in searchable}

        user_skills = {s.lower() for s in user_profile.technical_skills}

        if not job_skills:
            return 0.0

        # Count matching skills
        matched = job_skills & user_skills
        matching_count = len(matched)

        # Calculate overlap ratio
        overlap = matching_count / len(job_skills)

        if matching_count > 0:
            explanation.append(f"Found {matching_count} matching skill(s): {', '.join(sorted(matched))}")
        else:
            explanation.append("No skill matches found")
            # Check if user has skills but job description doesn't contain them
            if user_skills:
                explanation.append(f"User skills: {', '.join(sorted(user_skills))}")

        return round(overlap, 2)

    def _extract_skills_from_description(
        self,
        job: JobRecord,
        user_profile: UserProfile,
    ) -> list[str]:
        """Extract skills from job description using keyword matching."""
        # Combine title and available text sources for extraction
        title = job.title.lower()
        description_parts = []
        if job.source_api_url:
            description_parts.append(job.source_api_url.lower())
        if job.application_url:
            description_parts.append(job.application_url.lower())

        # Use the job description field if available (from raw_data)
        if job.raw_data and isinstance(job.raw_data, dict):
            description = job.raw_data.get("description", "").lower()
        else:
            description = " "

        searchable_text = job_searchable_text(job).lower()

        # Extract skills from user's profile that appear in the job description
        extracted = []
        for skill in user_profile.technical_skills:
            skill_lower = skill.lower().strip()
            # Check exact match first
            if skill_lower in searchable_text:
                extracted.append(skill)
            else:
                # Check for variants or partial matches
                for alias in self._get_skill_aliases(skill):
                    if alias in searchable_text:
                        extracted.append(skill)
                        break

        # Deduplicate while preserving order
        seen = set()
        result = []
        for skill in extracted:
            if skill.lower() not in seen:
                seen.add(skill.lower())
                result.append(skill)

        return result

    def _get_skill_aliases(self, skill: str) -> list[str]:
        """Get common aliases for a skill name."""
        aliases = {
            "postgresql": ["postgres", "postgreSQL", "postgre"],
            "node.js": ["nodejs", "node js", "node"],
            "javascript": ["js"],
            "python": ["python3", "py"],
            "java": ["java8", "java11", "java17"],
            "c++": ["cplusplus", "c-plus-plus"],
            "c#": ["csharp", "dotnet"],
            "c": ["c-language", "ansi c"],
            "ruby": ["ruby on rails", "rails"],
            "php": ["laravel", "symfony"],
            "go": ["golang"],
            "rust": ["rust-lang"],
            "kotlin": ["kt"],
            "swift": ["swiftui"],
            "typescript": ["ts"],
            "react": ["reactjs", "react.js"],
            "angular": ["angularjs", "angular 2+"],
            "vue": ["vuejs"],
            "django": ["django framework", "djangopackages"],
            "flask": ["flask framework"],
            "spring": ["spring boot", "spring framework"],
        }
        return aliases.get(skill.lower(), [])

    def _compute_role_relevance(
        self,
        job: JobRecord,
        user_profile: UserProfile,
        explanation: list[str],
    ) -> float:
        """Compute role relevance."""
        job_title = job.title.lower()
        user_roles = [r.lower() for r in user_profile.preferred_roles]

        # Check if job title contains any preferred role
        if user_roles:
            for role in user_roles:
                if role in job_title:
                    explanation.append(f"Role relevance: job title contains '{role}'")
                    return 1.0

        # Check if job is software engineering related
        job_keywords = ["software", "developer", "engineer", "engineering", "backend",
                        "frontend", "full stack", "mobile", "data", "ai", "machine learning"]
        job_is_se = any(kw in job_title for kw in job_keywords)

        if job_is_se:
            explanation.append("Role relevance: software engineering role")
            return 0.8

        explanation.append("Role relevance: role not explicitly in preferred list")
        return 0.3

    def _compute_experience_eligibility(
        self,
        job: JobRecord,
        user_profile: UserProfile,
        explanation: list[str],
    ) -> float:
        """Compute experience eligibility."""
        job_exp = job.experience

        if not job_exp:
            explanation.append("Experience: not specified in job posting")
            # If not specified, treat as unknown (not blocking)
            return 0.6

        # Parse job experience range
        job_min = self._parse_experience(job_exp)
        # If experience is specified, check eligibility
        if job_min is not None:
            # Check user experience
            explanation.append(f"Experience: job asks for {job_min}+ years; candidate years are not explicitly recorded")
            return 0.5

        # Unknown experience = neutral
        explanation.append("Experience: not specified in job posting")
        return 0.6

    def _compute_location_score(
        self,
        job: JobRecord,
        user_profile: UserProfile,
        explanation: list[str],
    ) -> float:
        """Compute location preference score."""
        job_location = job.location.lower() if job.location else ""
        user_locations = [l.lower() for l in user_profile.preferred_locations]
        remote_preference = user_profile.remote_preference

        if not job_location:
            explanation.append("Location: not specified in job posting")
            return 0.5

        # Check remote preference
        if "remote" in job_location or "anywhere" in job_location or "worldwide" in job_location:
            if remote_preference:
                explanation.append("Location: remote job matches remote preference")
                return 1.0
            else:
                explanation.append("Location: job is remote but user prefers on-site")
                return 0.3

        # Check user's preferred locations
        for loc in user_locations:
            if loc in job_location:
                explanation.append(f"Location: job in '{loc}' matches preference")
                return 1.0

        # No country is inferred from partial text such as "IN".
        explanation.append(f"Location: job in '{job_location}' not in user's preferred locations")
        return 0.3

    def _compute_education_score(
        self,
        job: JobRecord,
        user_profile: UserProfile,
        explanation: list[str],
    ) -> float:
        """Compute education eligibility score."""
        job_title = job.title.lower()
        user_education = user_profile.education.lower()
        user_year = user_profile.graduation_year

        # Default: neutral if not specified
        score = 0.5

        # Check if job requires education
        education_requirements = ["graduate", "post-graduate", "master", "phd", "degree"]
        if any(req in job_title for req in education_requirements):
            if user_education:
                explanation.append("Education: job requires degree, user has degree")
                score = 0.8
            else:
                explanation.append("Education: job requires degree, user has no degree listed")
                score = 0.4

        # Check graduation year for fresher roles
        if user_year and user_year >= 2020:
            if not any(req in job_title for req in education_requirements):
                explanation.append(f"Education: user graduated {user_year}, is entry-level")
                score = 0.7

        explanation.append(f"Education: user education='{user_education}', year={user_year}")
        return round(score, 2)

    def _determine_eligibility(
        self,
        skill_overlap: float,
        role_relevance: float,
        experience_eligibility: float,
        location_score: float,
        education_score: float,
    ) -> str:
        """Determine eligibility status."""
        # If skills completely missing, low eligibility
        if skill_overlap == 0.0 and role_relevance < 0.5:
            return "not_eligible"

        # If high match
        if (skill_overlap >= 0.7 and experience_eligibility >= 0.6):
            return "high_match"

        # If medium match
        if skill_overlap >= 0.4 or experience_eligibility >= 0.5:
            return "medium_match"

        return "low_match"

    def _parse_experience(self, exp_str: str, max_only: bool = False) -> Optional[int]:
        """Parse experience range string."""
        if not exp_str:
            return None

        exp_lower = exp_str.lower()
        if "remote" in exp_lower:
            return None

        # Match patterns like "0-1 years", "0 to 1 years", "1 year", "2+ years"
        patterns = [
            r"(\d+)\s*-\s*(\d+)\s*years?",  # 0-1 years
            r"(\d+)\s*to\s*(\d+)\s*years?",  # 0 to 1 years
            r"(\d+)\s*years?",  # 1 year
            r"(\d+)\s*\+?\s*years?",  # 2+ years
        ]

        for pattern in patterns:
            match = re.search(pattern, exp_lower)
            if match:
                if max_only:
                    return int(match.group(2) if match.group(2) else match.group(1))
                else:
                    return int(match.group(1))

        return None

    def auto_assign_user_id(self, storage: SQLiteStorage) -> str:
        """Auto-generate or retrieve a user ID."""
        # Check for existing auto-assigned profile
        for profile in storage.list_profiles():
            if profile.user_id.startswith("auto_"):
                return profile.user_id

        # Create new auto-assigned profile
        user_id = f"auto_{uuid.uuid4().hex[:8]}"
        profile = UserProfile(
            user_id=user_id,
            technical_skills=[],
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        storage.create_profile(profile)
        return user_id
