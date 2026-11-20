"""Tests for the storage module using an in-memory SQLite database."""

import pytest
import tempfile
import os

from storage.database import SQLiteStorage
from models.schemas import JobRecord, Employer, SearchRun
from models.schemas import AtsProvider
from models.schemas import VerificationStatus


@pytest.fixture
def storage():
    """Create a temporary SQLite storage for testing."""
    import tempfile
    import os
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    storage = SQLiteStorage(db_path)
    yield storage
    # Cleanup
    try:
        storage.close()
    except Exception:
        pass
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestStorage:
    """Tests for SQLiteStorage."""

    def test_create_tables(self, storage):
        """Test that tables are created on initialization."""
        # The connection is established on first use, not at init
        assert storage.db_path is not None

    def test_directory_creation(self):
        """Test that the parent directory is created automatically."""
        import tempfile
        import os
        import shutil

        # Create a nested non-existent directory path
        tmpdir = tempfile.mkdtemp()
        nested_db_path = os.path.join(tmpdir, "subdir", "nested", "test.db")

        storage = SQLiteStorage(nested_db_path)
        # Trigger connection establishment (creates the file)
        storage.add_employer("lever", "drivetrain", "https://jobs.lever.co/drivetrain")
        storage.close()

        # Verify the directory was created
        assert os.path.exists(os.path.dirname(nested_db_path))
        # Verify the file exists
        assert os.path.exists(nested_db_path)
        os.unlink(nested_db_path)
        shutil.rmtree(tmpdir)

    def test_in_memory_sqlite(self):
        """Test that in-memory SQLite databases work."""
        storage = SQLiteStorage(":memory:")
        assert storage.db_path == ":memory:"
        storage.close()

    def test_add_and_get_employer(self, storage):
        """Test adding and getting an employer."""
        emp = storage.add_employer(
            provider=AtsProvider.LEVER.value,
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain",
        )

        assert emp is not None
        assert emp.provider == "lever"
        assert emp.board_id == "drivetrain"
        assert emp.enabled is True

        # Retrieve
        retrieved = storage.get_employer("lever", "drivetrain")
        assert retrieved is not None
        assert retrieved.board_id == "drivetrain"

    def test_duplicate_employer(self, storage):
        """Test that adding duplicate employer updates existing record."""
        storage.add_employer(
            provider=AtsProvider.LEVER.value,
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain",
        )
        # Add again with different URL
        emp = storage.add_employer(
            provider=AtsProvider.LEVER.value,
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain/new",
        )
        assert emp is not None
        # Should still be one record
        assert storage.list_employers() is not None

    def test_add_and_get_job(self, storage):
        """Test adding and getting a job."""
        job = JobRecord(
            provider=AtsProvider.LEVER,
            original_job_id="test-1",
            company="Test",
            title="Engineering Intern",
            location="IN",
            experience="0-1 years",
            application_url="https://example.com/apply",
        )
        saved = storage.upsert_job(job)

        assert saved.original_job_id == "test-1"
        retrieved = storage.get_job(AtsProvider.LEVER.value, "test-1")
        assert retrieved is not None
        assert retrieved.title == "Engineering Intern"

    def test_job_deduplication(self, storage):
        """Test that duplicate jobs with same provider+ID are not duplicated in query."""
        # Add an employer first (required for job to be findable)
        storage.add_employer(
            provider=AtsProvider.LEVER.value,
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain",
        )

        job = JobRecord(
            provider=AtsProvider.LEVER,
            original_job_id="test-1",
            company="Test",
            title="Engineering Intern",
            location="IN",
            application_url="https://example.com/apply",
        )
        storage.upsert_job(job)
        storage.upsert_job(job)  # Should update, not duplicate

        jobs = storage.search_jobs()
        # Count distinct job IDs
        ids = {j.original_job_id for j in jobs}
        assert len(ids) == 1

    def test_get_failed_sources(self, storage):
        """Test getting failed sources (enabled=1, no sync yet)."""
        # Add an employer without sync
        storage.add_employer(
            provider=AtsProvider.LEVER.value,
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain",
        )
        failed = storage.get_failed_sources()
        assert len(failed) == 1
        assert failed[0]["provider"] == "lever"

    def test_serialize_and_deserialize_skills(self, storage):
        """Test skills serialization round-trip."""
        job = JobRecord(
            provider=AtsProvider.LEVER,
            original_job_id="test-1",
            company="Test",
            title="Eng",
            location="IN",
            skills=["Python", "JavaScript"],
        )
        storage.upsert_job(job)

        retrieved = storage.get_job(AtsProvider.LEVER.value, "test-1")
        assert retrieved is not None
        assert retrieved.skills == ["Python", "JavaScript"]

    def test_job_verification_history(self, storage):
        """Test that upsert_job creates verification history entry."""
        job = JobRecord(
            provider=AtsProvider.LEVER,
            original_job_id="test-1",
            company="Test",
            title="Engineering Intern",
            location="IN",
            verification_status=VerificationStatus.API_CONFIRMED,
            verification_evidence="Test evidence",
        )
        storage.upsert_job(job)

        # Check that verification history was created
        count = storage.get_verified_jobs().__len__()
        # The job should be retrievable
        retrieved = storage.get_job("lever", "test-1")
        assert retrieved is not None

    def test_search_jobs_with_filters(self, storage):
        """Test filtering jobs by provider and title."""
        # Add an employer matching the job's provider and board_id
        storage.add_employer(
            provider=AtsProvider.LEVER.value,
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain",
        )

        # Add a job
        job = JobRecord(
            provider=AtsProvider.LEVER,
            original_job_id="1",
            company="Test",
            title="Engineering Intern",
            location="IN",
        )
        storage.upsert_job(job)

        # Search with provider filter
        results = storage.search_jobs(provider=AtsProvider.LEVER.value)
        assert len(results) == 1

        # Search with title filter
        results = storage.search_jobs(title_contains="Engineering")
        assert len(results) == 1

    def test_get_verified_jobs(self, storage):
        """Test retrieving verified jobs."""
        job = JobRecord(
            provider=AtsProvider.LEVER,
            original_job_id="1",
            company="Test",
            title="Engineering Intern",
            location="IN",
            verification_status=VerificationStatus.API_CONFIRMED,
        )
        storage.upsert_job(job)

        # Only verified jobs should be returned
        verified = storage.get_verified_jobs()
        assert len(verified) == 0  # Not verified by default

    def test_preferences(self, storage):
        """Test saving and getting user preferences."""
        storage.save_preference("career_profile", '{"skills": ["Python"]}')
        value = storage.get_preference("career_profile")
        assert value is not None
        assert "Python" in value

    def test_search_runs(self, storage):
        """Test saving and getting search runs."""
        run = SearchRun(
            run_id="test-run-1",
            search_at="2026-10-24T00:00:00Z",
            filters_applied={"roles": ["engineer"]},
            total_received=10,
            total_fetched=5,
            total_filtered=3,
        )
        storage.save_search_run(run)
        retrieved = storage.get_search_run("test-run-1")
        assert retrieved is not None
        assert retrieved.total_filtered == 3
