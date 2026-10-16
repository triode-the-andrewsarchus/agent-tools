"""Tests for AST-based reuse candidate finder."""

from pathlib import Path
from architecture_fitness.reuse_finder import ReuseFinder


def test_reuse_finder_python(temp_dir):
    src = temp_dir / "auth.py"
    src.write_text('''
def verify_user_credentials(username, password_hash):
    """Check whether username and hashed password match database records."""
    return username == "admin"

class TokenValidator:
    def validate_jwt_token(self, token):
        """Validate expiration and signature of JWT token."""
        return True
''')
    finder = ReuseFinder()
    candidates = finder.find_candidates(temp_dir, query="authenticate user password")

    assert len(candidates) >= 1
    top = candidates[0]
    assert top.symbol_name == "verify_user_credentials"
    assert top.file_path == "auth.py"
    assert top.kind == "function"
    assert "user" in top.relevance_reason.lower() or "password" in top.relevance_reason.lower()


def test_reuse_finder_generic_js(temp_dir):
    src = temp_dir / "formatters.js"
    src.write_text('''
function formatCurrencyUSD(cents) {
    return '$' + (cents / 100).toFixed(2);
}
''')
    finder = ReuseFinder()
    candidates = finder.find_candidates(temp_dir, query="format currency money")

    assert len(candidates) >= 1
    assert candidates[0].symbol_name == "formatCurrencyUSD"


def test_reuse_finder_respects_gitignore(temp_dir):
    (temp_dir / ".gitignore").write_text("/ignored_dir\n*.tmp.py\n")
    ign_dir = temp_dir / "ignored_dir"
    ign_dir.mkdir()
    (ign_dir / "secret.py").write_text("def authenticate_admin_user():\n    pass\n")
    (temp_dir / "test.tmp.py").write_text("def authenticate_guest_user():\n    pass\n")
    (temp_dir / "valid.py").write_text("def authenticate_member_user():\n    pass\n")

    finder = ReuseFinder()
    candidates = finder.find_candidates(temp_dir, query="authenticate user")

    assert len(candidates) == 1
    assert candidates[0].symbol_name == "authenticate_member_user"
    assert candidates[0].file_path == "valid.py"
