"""
CentauriControl – authentication manager.

Owns password hashing (bcrypt), session token lifecycle, and HTTP cookie
parsing.  All persistence goes through DataStore — this module writes no
files directly.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Optional

from centauricontrol.persistence.store import DataStore

try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None  # type: ignore[assignment]
    _BCRYPT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SESSION_COOKIE: str = "centauricontrol_sid"
SESSION_TTL: int = 30 * 24 * 3600  # 30 days in seconds
BCRYPT_ROUNDS: int = 12

#: Read once at import time so the HTTP handler can check it without re-reading
#: the environment on every request.
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower() != "false"

_AUTH_FILE = "auth.json"
_SESSIONS_FILE = "sessions.json"

# ---------------------------------------------------------------------------
# Module-level singleton (set by __main__.py via set_auth_manager)
# ---------------------------------------------------------------------------

_auth_manager: Optional["AuthManager"] = None


def set_auth_manager(manager: "AuthManager") -> None:
    """Register the application-wide AuthManager singleton."""
    global _auth_manager
    _auth_manager = manager


def get_auth_manager() -> Optional["AuthManager"]:
    return _auth_manager


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """Manages passwords, sessions, and authentication state.

    Args:
        store: DataStore instance used for reading/writing auth.json.
    """

    def __init__(self, store: DataStore) -> None:
        self._store = store
        # token → Unix epoch expiry (float)
        self._sessions: dict[str, float] = {}
        self._load_sessions()

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def has_password(self) -> bool:
        """Return True if a password hash is configured."""
        if os.getenv("CENTAURICONTROL_PW_HASH", ""):
            return True
        record = self._store.read(_AUTH_FILE)
        if not isinstance(record, dict):
            return False
        return bool(record.get("pw_hash"))

    def get_username(self) -> str:
        """Return the configured username; defaults to 'admin'."""
        env_user = os.getenv("CENTAURICONTROL_USERNAME", "")
        if env_user:
            return env_user
        record = self._store.read(_AUTH_FILE)
        if isinstance(record, dict):
            return record.get("username") or "admin"
        return "admin"

    def set_password(self, username: str, password: str) -> None:
        """Hash *password* with bcrypt and persist via DataStore.

        Raises:
            RuntimeError: if bcrypt is not installed.
            ValueError: if username is empty or password is fewer than 8 chars.
        """
        if not _BCRYPT_AVAILABLE or _bcrypt is None:
            raise RuntimeError("bcrypt package is required to set a password")
        if not username:
            raise ValueError("username must not be empty")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")

        pw_hash: str = _bcrypt.hashpw(
            password.encode("utf-8"),
            _bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")

        self._store.write(_AUTH_FILE, {"username": username, "pw_hash": pw_hash})

    def verify(self, username: str, password: str) -> bool:
        """Return True if credentials match the stored hash.

        Never raises — returns False on any error or missing dependency.
        """
        if not username or not password:
            return False

        if not _BCRYPT_AVAILABLE or _bcrypt is None:
            print("[Auth] bcrypt not installed — login always fails")
            return False

        # Username check
        if username != self.get_username():
            return False

        # Retrieve hash: env var takes precedence over file
        stored_hash: str = os.getenv("CENTAURICONTROL_PW_HASH", "")
        if not stored_hash:
            record = self._store.read(_AUTH_FILE)
            if not isinstance(record, dict):
                return False
            stored_hash = record.get("pw_hash") or ""

        if not stored_hash:
            return False

        try:
            return bool(
                _bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self) -> str:
        """Create a new 30-day session token and return it."""
        token = secrets.token_urlsafe(32)
        self._sessions[token] = time.time() + SESSION_TTL
        self._save_sessions()
        return token

    def validate_session(self, token: str) -> bool:
        """Return True if *token* exists and has not expired.

        Expired tokens are removed lazily on this call.
        """
        expiry = self._sessions.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._sessions[token]
            self._save_sessions()
            return False
        return True

    def revoke_session(self, token: str) -> None:
        """Remove *token* from the active sessions dict."""
        self._sessions.pop(token, None)
        self._save_sessions()

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        """Load sessions from disk, filtering out expired ones."""
        record = self._store.read(_SESSIONS_FILE)
        if not isinstance(record, dict):
            return
        now = time.time()
        for token, expiry in record.items():
            if isinstance(expiry, (int, float)) and expiry > now:
                self._sessions[token] = expiry

    def _save_sessions(self) -> None:
        """Persist active sessions to disk."""
        self._store.write(_SESSIONS_FILE, self._sessions)


# ---------------------------------------------------------------------------
# Middleware helpers (module-level)
# ---------------------------------------------------------------------------

def extract_token(cookie_header: str) -> str | None:
    """Parse the ``centauricontrol_sid`` value from a Cookie header string.

    Args:
        cookie_header: Raw value of the ``Cookie`` HTTP header.

    Returns:
        The token string, or ``None`` if the cookie name is not present.
    """
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name.strip() == SESSION_COOKIE:
            return value.strip() or None
    return None


def check_cookie(request_headers: dict[str, str]) -> bool:
    """Return True if the Cookie header contains a valid session token.

    Always returns True when AUTH_ENABLED is False.
    """
    if not AUTH_ENABLED:
        return True
    manager = get_auth_manager()
    if manager is None:
        return False
    cookie_header = request_headers.get("Cookie", "") or request_headers.get("cookie", "")
    token = extract_token(cookie_header)
    if not token:
        return False
    return manager.validate_session(token)
