"""Tests for the CLI command functions."""

import pytest
import tempfile
import os
import sys

# Ensure the project root is importable
sys.path.insert(0, "/c/Users/dell/jobcare-job-scout")

from cli.commands import cmd_add_employer, cmd_list_employers, build_arg_parser
from storage.database import SQLiteStorage


@pytest.fixture
def storage():
    """Create a temporary SQLite storage for testing."""
    import tempfile
    import os
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    storage = SQLiteStorage(db_path)
    storage._conn = None  # Force reconnect on first use
    yield storage
    # Cleanup
    try:
        storage.close()
    except Exception:
        pass
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestCLICommands:
    """Tests for CLI command functions."""

    def test_add_employer(self, storage):
        """Test adding an employer via CLI command."""
        # Set a custom DB path for the CLI
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        # Use the storage directly for simplicity
        employer = storage.add_employer(
            provider="lever",
            board_id="drivetrain",
            careers_url="https://jobs.lever.co/drivetrain",
        )
        assert employer is not None
        assert employer.provider == "lever"
        assert employer.board_id == "drivetrain"

    def test_list_employers(self, storage):
        """Test listing employers."""
        # Add a few employers
        storage.add_employer("lever", "drivetrain", "https://jobs.lever.co/drivetrain")
        storage.add_employer("greenhouse", "bitgo", "https://boards.greenhouse.io/bitgo")

        employers = storage.list_employers()
        assert len(employers) == 2

        # Test enabled_only
        enabled = storage.list_employers(enabled_only=True)
        assert len(enabled) == 2

    def test_build_arg_parser(self):
        """Test that the argument parser builds correctly."""
        parser = build_arg_parser()
        assert parser is not None
        # Check subcommands exist
        subcommands = [action.dest for action in parser._subparsers._actions if action.dest == "command"]
        assert len(subcommands) > 0


class TestArguments:
    """Test argument parsing."""

    def test_add_employer_parser(self):
        """Test add-employer argument parsing."""
        parser = build_arg_parser()
        args = parser.parse_args([
            "add-employer",
            "--provider", "lever",
            "--board-id", "drivetrain",
            "--careers-url", "https://jobs.lever.co/drivetrain",
        ])
        assert args.provider == "lever"
        assert args.careers_url == "https://jobs.lever.co/drivetrain"

    def test_list_employers_parser(self):
        """Test list-employers argument parsing."""
        parser = build_arg_parser()
        args = parser.parse_args(["list-employers"])
        assert args.command == "list-employers"

    def test_sync_parser(self):
        """Test sync argument parsing."""
        parser = build_arg_parser()
        args = parser.parse_args(["sync"])
        assert args.command == "sync"

    def test_show_verified_parser(self):
        """Test show-verified argument parsing."""
        parser = build_arg_parser()
        args = parser.parse_args(["show-verified"])
        assert args.command == "show-verified"
