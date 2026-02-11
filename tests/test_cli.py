"""Minimal smoke tests for the storyteller CLI wrapper.

Run with: python -m pytest tests/test_cli.py -v
"""
from __future__ import annotations

import subprocess
import sys

import pytest


def _run_cli(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "storyteller", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestCLIHelp:
    """Verify that all subcommands register and print help without errors."""

    def test_main_help(self):
        result = _run_cli("--help")
        assert result.returncode == 0
        assert "doctor" in result.stdout
        assert "setup" in result.stdout
        assert "dev" in result.stdout
        assert "ingest" in result.stdout
        assert "query" in result.stdout

    def test_doctor_help(self):
        result = _run_cli("doctor", "--help")
        assert result.returncode == 0
        assert "doctor" in result.stdout.lower()

    def test_setup_help(self):
        result = _run_cli("setup", "--help")
        assert result.returncode == 0
        assert "--skip-deps" in result.stdout

    def test_dev_help(self):
        result = _run_cli("dev", "--help")
        assert result.returncode == 0
        assert "--backend-only" in result.stdout
        assert "--ui-only" in result.stdout

    def test_ingest_help(self):
        result = _run_cli("ingest", "--help")
        assert result.returncode == 0
        assert "--pipeline" in result.stdout
        assert "simple" in result.stdout
        assert "lore" in result.stdout

    def test_query_help(self):
        result = _run_cli("query", "--help")
        assert result.returncode == 0
        assert "--k" in result.stdout


class TestDoctorRuns:
    """Doctor should run without crashing (some checks may warn/fail depending on env)."""

    def test_doctor_exits_cleanly(self):
        result = _run_cli("doctor")
        # Should exit with 0 (all ok) or 1 (issues found) — not crash
        assert result.returncode in (0, 1)
        assert "Storyteller Doctor" in result.stdout


class TestIngestGuardrails:
    """Test that ingest command validates inputs before running."""

    def test_ingest_missing_dir(self):
        result = _run_cli("ingest", "--input", "/nonexistent/path/abc123")
        assert result.returncode == 1
        assert "not found" in result.stdout.lower() or "ERROR" in result.stdout

    def test_query_missing_db(self):
        result = _run_cli("query", "test query", "--db", "/nonexistent/db/abc123")
        assert result.returncode == 1
        assert "not found" in result.stdout.lower() or "ERROR" in result.stdout
