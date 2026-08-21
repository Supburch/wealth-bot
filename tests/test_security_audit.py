"""
test_security_audit.py — Static checks that secrets stay out of source control and logs.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SECRET_FILE_PATTERNS = (
    r"^\.env$",
    r"\.env\.",
    r"credentials.*\.json$",
    r"service.?account.*\.json$",
    r".*-.*-.*\.json$",
)

HARDCODED_SECRET_PATTERNS = (
    (r'LINE_CHANNEL_ACCESS_TOKEN\s*=\s*["\'][^"\']{10,}', "hardcoded LINE access token"),
    (r'LINE_CHANNEL_SECRET\s*=\s*["\'][^"\']{10,}', "hardcoded LINE channel secret"),
    (r'GOOGLE_CREDENTIALS_JSON\s*=\s*["\'][^"\']{10,}', "hardcoded Google credentials"),
    (r"-----BEGIN (?:RSA )?PRIVATE KEY-----", "embedded private key"),
    (r'"private_key"\s*:\s*"-----BEGIN', "embedded service-account private key"),
    (r"ya29\.[A-Za-z0-9\-_]{20,}", "Google OAuth access token"),
)

LOGGING_LEAK_PATTERNS = (
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*settings\.LINE_", "settings token in log call"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*GOOGLE_CREDENTIALS", "Google credentials in log call"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*private_key", "private key in log call"),
)

# P2.2: user/identifier PII leaks in operational logs.
PII_LOG_PATTERNS = (
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*\{user_id\}", "raw user_id interpolated in log call"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*\{user_mapping_result\}", "raw user_mapping_result interpolated in log call"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*\{spreadsheet_id\}", "raw spreadsheet_id interpolated in log call"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*, user_id\s*[,)]", "raw user_id passed as log argument"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*, spreadsheet_id\s*[,)]", "raw spreadsheet_id passed as log argument"),
    (r"extra=\{[^}]*\"(?:user_id|spreadsheet_id|text|command|raw_command|user_mapping_result)\"\s*:(?!\s*(?:mask_id|redact_text)\()", "unmasked identifier in log extra dict"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*\{e\}", "raw exception interpolated in log call"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*, e\s*[,)]", "raw exception passed as log argument"),
    (r"logger\.(?:info|debug|warning|error|exception)\([^)]*str\(e\)", "raw str(e) in log call"),
)

# P2.2: identifiers/raw exception details leaking into user-facing messages.
USER_FACING_LEAK_PATTERNS = (
    (r"spreadsheet_id\s*=\s*\{spreadsheet_id\}", "spreadsheet_id in user-facing message"),
    (r"error_message\s*=\s*f\"[^\"]*\{", "interpolated value in user-facing error_message"),
    (r"error\s*=\s*str\(e\)", "raw str(e) in user-facing error result"),
)

SCAN_IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(part in SCAN_IGNORE_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def _git_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_gitignore_excludes_env_and_credential_json():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "*.json" in gitignore


def test_no_secret_files_tracked_in_git():
    tracked = _git_tracked_files()
    # .env.example is a tracked template with placeholder values only.
    allowed_templates = {".env.example"}
    violations = [
        path
        for path in tracked
        if path not in allowed_templates
        and any(re.search(pattern, path, re.IGNORECASE) for pattern in SECRET_FILE_PATTERNS)
        and "package.json" not in path
    ]
    assert violations == [], f"Secret-like files tracked in git: {violations}"


@pytest.mark.parametrize("pattern,label", HARDCODED_SECRET_PATTERNS)
def test_source_has_no_hardcoded_secrets(pattern: str, label: str):
    violations: list[str] = []
    for path in _iter_python_files():
        content = path.read_text(encoding="utf-8")
        if re.search(pattern, content):
            violations.append(f"{path.relative_to(ROOT)} ({label})")
    assert violations == []


@pytest.mark.parametrize("pattern,label", LOGGING_LEAK_PATTERNS)
def test_logging_calls_do_not_leak_secrets(pattern: str, label: str):
    violations: list[str] = []
    for path in _iter_python_files():
        content = path.read_text(encoding="utf-8")
        if re.search(pattern, content):
            violations.append(f"{path.relative_to(ROOT)} ({label})")
    assert violations == []


@pytest.mark.parametrize("pattern,label", PII_LOG_PATTERNS)
def test_logging_calls_do_not_leak_pii(pattern: str, label: str):
    violations: list[str] = []
    for path in _iter_python_files():
        content = path.read_text(encoding="utf-8")
        if re.search(pattern, content):
            violations.append(f"{path.relative_to(ROOT)} ({label})")
    assert violations == []


@pytest.mark.parametrize("pattern,label", USER_FACING_LEAK_PATTERNS)
def test_user_facing_errors_do_not_leak_pii(pattern: str, label: str):
    violations: list[str] = []
    for path in _iter_python_files():
        content = path.read_text(encoding="utf-8")
        if re.search(pattern, content):
            violations.append(f"{path.relative_to(ROOT)} ({label})")
    assert violations == []


def test_settings_load_secrets_from_environment_only():
    config_source = (ROOT / "config.py").read_text(encoding="utf-8")
    assert "LINE_CHANNEL_ACCESS_TOKEN: str" in config_source
    assert "LINE_CHANNEL_SECRET: str" in config_source
    assert "GOOGLE_CREDENTIALS_JSON: str" in config_source
    assert 'model_config = {"env_file": ".env"' in config_source
