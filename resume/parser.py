"""Resume parser for PDF and DOCX files.

Supports extraction of:
- Technical skills
- Education
- Projects
- Work experience
- Certifications

Does not invent qualifications or experience.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.schemas import ResumeData

try:
    import fitz  # PyMuPDF
    has_pymupdf = True
except ImportError:
    has_pymupdf = False

try:
    import docx
    has_docx = True
except ImportError:
    has_docx = False


class ResumeParserError(Exception):
    """Exception raised when resume parsing fails."""

    pass


class ResumeParser:
    """Parse PDF and DOCX resumes into structured data."""

    # Common skill keywords
    SKILL_KEYWORDS = [
        "Python", "Java", "JavaScript", "TypeScript", "C++", "C", "C#", "Go", "Rust",
        "Ruby", "PHP", "Swift", "Kotlin", "Scala", "Perl", "R", "SQL", "HTML", "CSS",
        "React", "Angular", "Vue", "Node.js", "Django", "Flask", "Spring", "TensorFlow",
        "PyTorch", "scikit-learn", "pandas", "NumPy", "AWS", "Azure", "GCP", "Docker",
        "Kubernetes", "Linux", "Git", "CI/CD", "REST", "GraphQL", "PostgreSQL", "MongoDB",
        "Redis", "Kafka", "Apache", "Kibana", "Elasticsearch", "Selenium", "Jenkins",
        "Kubernetes", "Terraform", "Ansible", "PowerShell", "Bash", "HTML5", "CSS3",
        "Bootstrap", "Tailwind", "Webpack", "Nginx", "Linux", "Unix", "Windows",
        "Data Structures", "Algorithms", "OOP", "SOLID", "Design Patterns", "APM",
        "Testing", "TDD", "BDD", "Agile", "Scrum", "CI/CD", "Microservices",
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "Data Science",
        "Big Data", "Hadoop", "Spark", "Tableau", "Power BI", "Excel", "Airflow",
        "GraphQL", "Graph Database", "Neo4j", "Cypher", "Ethereum", "Blockchain",
        "React Native", "Flutter", "SwiftUI", "Android Studio", "Xcode", "Ionic",
    ]

    # Education keywords
    EDUCATION_KEYWORDS = [
        "Bachelor", "Master", "PhD", "B.Tech", "M.Tech", "MBA", "BBA", "BSc", "MSc",
        "BA", "B.Com", "M.Com", "BCom", "MCom", "BE", "ME", "B.E.", "M.E.",
        "B.Arch", "M.Arch", "B.Des", "M.Des", "BFA", "MFA", "LLB", "LLM",
    ]

    # Experience keywords
    EXPERIENCE_KEYWORDS = [
        "Work Experience", "Professional Experience", "Engineering Experience",
        "Full-time", "Part-time", "Internship", "Fresher", "Graduate", "Junior",
        "Senior", "Lead", "Manager", "Director", "VP", "CEO", "CTO", "COO",
        "Software Engineer", "Developer", "Engineer", "Analyst", "Architect",
    ]

    # Project keywords
    PROJECT_KEYWORDS = [
        "Project", "Graduation Project", "Capstone", "Final Year Project",
        "Personal Project", "Open Source", "Hackathon", "Portfolio",
    ]

    # Certification keywords
    CERTIFICATION_KEYWORDS = [
        "Certification", "Certified", "Certification Program", "Certification Course",
        "AWS Certified", "Google Certified", "Microsoft Certified", "CompTIA",
        "Cisco Certified", "PMI", "Six Sigma", "Scrum Certified", "Oracle Certified",
    ]

    def __init__(self):
        self.parsed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def parse(self, file_path: str) -> ResumeData:
        """Parse a resume file (PDF or DOCX).

        Args:
            file_path: Path to the resume file.

        Returns:
            ResumeData with extracted information.

        Raises:
            ResumeParserError: If the file cannot be parsed.
        """
        path = Path(file_path)
        if not path.exists():
            raise ResumeParserError(f"Resume file not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            if not has_pymupdf:
                raise ResumeParserError("PyMuPDF not installed. Install with: pip install PyMuPDF")
            return self._parse_pdf(path)
        elif suffix == ".docx":
            if not has_docx:
                raise ResumeParserError("python-docx not installed. Install with: pip install python-docx")
            return self._parse_docx(path)
        elif suffix == ".txt":
            with open(path, "r") as f:
                text = f.read()
            return self._extract_from_text(text, str(path))
        else:
            raise ResumeParserError(f"Unsupported file format: {suffix}. Supported: .pdf, .docx, .txt")

    def _parse_pdf(self, path: Path) -> ResumeData:
        """Parse a PDF resume."""
        doc = fitz.open(str(path))
        text = ""
        for page in doc:
            text += page.get_text()
        return self._extract_from_text(text, str(path))

    def _parse_docx(self, path: Path) -> ResumeData:
        """Parse a DOCX resume."""
        doc = docx.Document(str(path))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += "\n" + cell.text
        return self._extract_from_text(text, str(path))

    def _extract_from_text(self, text: str, file_path: str) -> ResumeData:
        """Extract structured data from raw resume text."""
        lines = text.split("\n")
        skills = []
        education = ""
        graduation_year = None
        projects = []
        work_experience = []
        certifications = []
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                current_section = None
                continue

            header_match = self._is_section_header(line)
            if header_match:
                current_section = header_match.group(1).lower()
                continue

            if current_section == "education":
                self._extract_education(line, education, graduation_year)
            elif current_section == "experience":
                self._extract_experience(line, work_experience)
            elif current_section == "project":
                self._extract_project(line, projects)
            elif current_section == "certification":
                self._extract_certification(line, certifications)
            else:
                self._extract_skills_from_line(line, skills)

        # Fallback: if education, projects, work experience, or certifications
        # are missing, try advanced extraction from the full text
        if not education or not projects or not work_experience or not certifications:
            flat = self._extract_flat_text(lines, file_path)
            education = flat.education or education
            graduation_year = flat.graduation_year or graduation_year
            projects = flat.projects or projects
            work_experience = flat.work_experience or work_experience
            certifications = flat.certifications or certifications

        return ResumeData(
            user_id="",
            skills=skills,
            education=education,
            graduation_year=graduation_year,
            projects=projects,
            work_experience=work_experience,
            certifications=certifications,
            parsed_at=self.parsed_at,
            file_path=file_path,
        )

    def _extract_flat_text(self, lines: list[str], file_path: str) -> ResumeData:
        """Extract data from flat text format (no section headers)."""
        text = " ".join(lines)
        skills = []
        education = ""
        graduation_year = None
        projects = []
        work_experience = []
        certifications = []

        # Extract skills using keyword matching
        for keyword in self.SKILL_KEYWORDS:
            if keyword.lower() in text.lower():
                if keyword not in skills:
                    skills.append(keyword)

        # Extract education and graduation year
        for line in lines:
            line_lower = line.lower()
            for keyword in self.EDUCATION_KEYWORDS:
                if keyword.lower() in line_lower:
                    if not education:
                        education = line
                    break
            year_match = re.search(r"(19|20)\d{2}", line)
            if year_match:
                year = int(year_match.group(0))
                if 1990 <= year <= 2026 and not graduation_year:
                    graduation_year = year

        # Extract experience, projects, certifications using keywords
        header_patterns = [
            r"^(education|degree|qualification|bachelor|master|phd|skills|project|projects|certification|certifications|experience|work experience)[\s:_-]*$",
        ]
        for line in lines:
            line_lower = line.lower()
            is_header = any(re.match(p, line_lower) for p in header_patterns)
            if is_header:
                continue

            if any(kw in line_lower for kw in self.EXPERIENCE_KEYWORDS) and len(line) > 10:
                if line not in work_experience:
                    work_experience.append(line)
            if any(kw in line_lower for kw in self.PROJECT_KEYWORDS) and len(line) > 10:
                if line not in projects:
                    projects.append(line)
            if any(kw in line_lower for kw in self.CERTIFICATION_KEYWORDS) and len(line) > 10:
                if line not in certifications:
                    certifications.append(line)

        return ResumeData(
            user_id="",
            skills=skills,
            education=education,
            graduation_year=graduation_year,
            projects=projects,
            work_experience=work_experience,
            certifications=certifications,
            parsed_at=self.parsed_at,
            file_path=file_path,
        )

    def _is_section_header(self, line: str) -> Optional[re.Match]:
        header_patterns = [
            r"^(education|degree|qualification|bachelor|master|phd)[\s:_-]*$",
            r"^(experience|work experience|professional experience|engineering experience)[\s:_-]*$",
            r"^(project|projects|graduation project|capstone|final year project)[\s:_-]*$",
            r"^(certification|certificates|certification program)[\s:_-]*$",
            r"^(skills|technical skills|qualifications|competencies)[\s:_-]*$",
        ]
        for pattern in header_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return match
        return None

    def _extract_skills_from_line(self, line: str, skills: list[str]):
        line_lower = line.lower()
        for keyword in self.SKILL_KEYWORDS:
            if keyword.lower() in line_lower:
                if keyword not in skills:
                    skills.append(keyword)

    def _extract_education(self, line: str, education: str, graduation_year: Optional[int]):
        line_lower = line.lower()
        for keyword in self.EDUCATION_KEYWORDS:
            if keyword.lower() in line_lower:
                if not education:
                    education = line
                break
        year_match = re.search(r"(19|20)\d{2}", line)
        if year_match:
            year = int(year_match.group(0))
            if 1990 <= year <= 2026 and not graduation_year:
                graduation_year = year

    def _extract_experience(self, line: str, work_experience: list[str]):
        line_lower = line.lower()
        for keyword in self.EXPERIENCE_KEYWORDS:
            if keyword.lower() in line_lower and len(line) > 10:
                if line not in work_experience:
                    work_experience.append(line)
                break

    def _extract_project(self, line: str, projects: list[str]):
        line_lower = line.lower()
        for keyword in self.PROJECT_KEYWORDS:
            if keyword.lower() in line_lower and len(line) > 10:
                if line not in projects:
                    projects.append(line)
                break

    def _extract_certification(self, line: str, certifications: list[str]):
        line_lower = line.lower()
        for keyword in self.CERTIFICATION_KEYWORDS:
            if keyword.lower() in line_lower and len(line) > 10:
                if line not in certifications:
                    certifications.append(line)
                break

    def parse_to_dict(self, file_path: str) -> dict[str, Any]:
        resume = self.parse(file_path)
        return {
            "user_id": resume.user_id,
            "skills": resume.skills,
            "education": resume.education,
            "graduation_year": resume.graduation_year,
            "projects": resume.projects,
            "work_experience": resume.work_experience,
            "certifications": resume.certifications,
            "parsed_at": resume.parsed_at,
            "file_path": resume.file_path,
        }
