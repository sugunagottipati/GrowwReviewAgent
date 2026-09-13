import re
from pathlib import Path


def test_no_direct_google_oauth_or_rest_clients() -> None:
    """Audit source files to ensure no direct Google OAuth or REST API clients exist."""
    src_dir = Path(__file__).parents[2] / "src"
    pyproject_file = Path(__file__).parents[2] / "pyproject.toml"

    forbidden_patterns = [
        re.compile(r"google-api-python-client", re.IGNORECASE),
        re.compile(r"google-auth-oauthlib", re.IGNORECASE),
        re.compile(r"google_auth_oauthlib", re.IGNORECASE),
        re.compile(r"InstalledAppFlow", re.IGNORECASE),
        re.compile(r"OAuth2WebServerFlow", re.IGNORECASE),
        re.compile(r"client_secret\.json", re.IGNORECASE),
        re.compile(r"credentials\.json", re.IGNORECASE),
        re.compile(r"https://docs\.googleapis\.com", re.IGNORECASE),
        re.compile(r"https://gmail\.googleapis\.com", re.IGNORECASE),
    ]

    # Check pyproject.toml
    pyproject_content = pyproject_file.read_text(encoding="utf-8")
    for pattern in forbidden_patterns:
        assert not pattern.search(pyproject_content), (
            f"Found forbidden Google REST/OAuth dependency or pattern in pyproject.toml: {pattern.pattern}"
        )

    # Check all python files under src
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert not pattern.search(content), (
                f"Found forbidden Google REST/OAuth code in {py_file}: {pattern.pattern}"
            )
