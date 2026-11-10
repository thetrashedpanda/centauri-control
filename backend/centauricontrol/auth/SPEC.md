# auth — Specification

## Purpose

The `auth` module manages user authentication for the CentauriControl web interface. It owns: password hash storage and verification (via bcrypt), session token creation and validation, and HTTP cookie parsing. It does NOT own route handling (that is `api`'s responsibility), does NOT make network calls, and does NOT write files directly — all persistence goes through `DataStore`.

---

## Public API

### `class AuthManager`

```python
class AuthManager:
    def __init__(self, store: DataStore) -> None: ...

    def has_password(self) -> bool:
        """Return True if a password hash is configured (env var or persisted file)."""

    def verify(self, username: str, password: str) -> bool:
        """Return True if username matches and password verifies against the stored hash.
        Returns False (never raises) if bcrypt is not installed or no hash is set."""

    def create_session(self) -> str:
        """Create a new session token with a 30-day TTL. Return the token string."""

    def validate_session(self, token: str) -> bool:
        """Return True if the token exists and has not expired.
        Removes expired tokens lazily during this call."""

    def revoke_session(self, token: str) -> None:
        """Remove the token from the sessions dict if present. No-op if absent."""

    def set_password(self, username: str, password: str) -> None:
        """Hash password with bcrypt (rounds=12) and persist via DataStore.
        Raises RuntimeError if bcrypt is not installed.
        Raises ValueError if username is empty or password is fewer than 8 characters."""

    def get_username(self) -> str:
        """Return the configured username (env var override takes precedence over saved file).
        Returns 'admin' if neither is set."""
```

### Middleware helpers (module-level functions)

```python
def check_cookie(request_headers: dict[str, str]) -> bool:
    """Return True if the 'Cookie' header contains a valid session token.
    Delegates to AuthManager.validate_session(). Returns False if AUTH_ENABLED=False."""

def extract_token(cookie_header: str) -> str | None:
    """Parse the centauricontrol_sid value from a Cookie header string.
    Returns None if the cookie name is not present."""
```

### Constants

```python
SESSION_COOKIE: str = "centauricontrol_sid"
SESSION_TTL: int = 30 * 24 * 3600   # 30 days in seconds
BCRYPT_ROUNDS: int = 12
```

---

## Invariants

- The in-memory sessions dict (`_sessions: dict[str, float]`) maps token → Unix epoch expiry. It never contains entries with `expiry < time.time()` after any call to `validate_session`.
- `validate_session` removes the token from the dict before returning `False` if it has expired (lazy cleanup).
- `create_session` always uses `secrets.token_urlsafe(32)` — never a shorter token or a UUID.
- bcrypt rounds is always 12. This value is a named constant `BCRYPT_ROUNDS = 12` and must not be overridden by callers.
- `AuthManager` stores a reference to `DataStore` and never constructs file paths itself.
- When `CENTAURICONTROL_PW_HASH` env var is set, it takes precedence over the value in `auth.json`. The env var value is never written back to `auth.json`.
- When `CENTAURICONTROL_USERNAME` env var is set, it takes precedence over the saved username. The env var value is never written back to `auth.json`.
- `AUTH_ENABLED` is read from the environment at import time; if `False`, `check_cookie` always returns `True` and `verify` is never called by the API layer.

---

## Error Handling

| Failure | Behavior |
|---|---|
| `bcrypt` not installed, `verify()` called | Return `False`; log `[Auth] bcrypt not installed — login always fails` |
| `bcrypt` not installed, `set_password()` called | Raise `RuntimeError("bcrypt package is required to set a password")` |
| `DataStore.read("auth.json")` returns `None` | Treat as no credentials configured; `has_password()` returns `False` |
| `DataStore.write("auth.json", ...)` raises | Let the exception propagate to the API handler, which returns HTTP 500 |
| `verify()` called with empty username or password | Return `False` immediately without calling bcrypt |
| Token not found in `validate_session()` | Return `False`; do not raise |
| Expired token in `validate_session()` | Remove from dict, return `False`; do not raise |

---

## Test Requirements

- Given auth is enabled and a password is configured, when `verify("admin", correct_password)` is called, then it returns `True`.
- Given auth is enabled and a password is configured, when `verify("admin", wrong_password)` is called, then it returns `False`.
- Given auth is enabled and a password is configured, when `verify("wrong_user", correct_password)` is called, then it returns `False`.
- Given `create_session()` is called, when `validate_session(token)` is called within 30 days, then it returns `True`.
- Given `create_session()` is called and the token's expiry is set to `time.time() - 1` (simulated expiry), when `validate_session(token)` is called, then it returns `False` and the token is removed from `_sessions`.
- Given `revoke_session(token)` is called, when `validate_session(token)` is called, then it returns `False`.
- Given `extract_token("centauricontrol_sid=abc123; Path=/")` is called, then it returns `"abc123"`.
- Given `extract_token("other=xyz")` is called, then it returns `None`.
- Given `has_password()` is called when no `auth.json` exists and no env var is set, then it returns `False`.
- Given `set_password("admin", "short")` (7 chars) is called, then it raises `ValueError`.
- Given `set_password("", "validpassword")` is called, then it raises `ValueError`.
- Given `AUTH_ENABLED=False`, when `check_cookie({})` is called, then it returns `True`.

---

## Do Not

- `AuthManager` must NOT read or write files directly — all persistence goes through `DataStore`.
- Do not store plaintext passwords anywhere (not in memory, not in files).
- Do not log tokens, passwords, or password hashes at any log level.
- Do not use `hashlib`, `hmac`, or any hash function other than `bcrypt` for password verification.
- Do not implement token rotation or sliding-window expiry — tokens have a fixed TTL set at creation.
- Do not use `uuid4` for session tokens — use `secrets.token_urlsafe(32)`.
- Do not persist session tokens to disk — they are in-memory only and lost on restart (users must re-login).

---

## Dependencies

Allowed standard library imports:
- `os`, `time`, `secrets`, `typing`

Allowed third-party imports:
- `bcrypt` (optional; handle `ImportError` gracefully)

Allowed internal imports:
- `centauricontrol.persistence.datastore.DataStore`
