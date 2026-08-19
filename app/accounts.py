import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import get_connection

SESSION_COOKIE_NAME = "le_bras_session"
SESSION_DURATION_DAYS = 7
PASSWORD_ITERATIONS = 240_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(Exception):
    """Erreur de validation ou d'authentification d'un compte local."""


def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise AccountError("Adresse e-mail invalide")
    normalized = email.strip().lower()
    if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise AccountError("Adresse e-mail invalide")
    return normalized


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise AccountError("Le mot de passe doit contenir au moins 8 caractères")
    if len(password) > 128:
        raise AccountError("Le mot de passe est trop long")
    return password


def _password_hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    ).hex()


def create_user(email: str, password: str) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    validated_password = validate_password(password)
    salt = secrets.token_bytes(16)
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO users (email, password_hash, password_salt, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                normalized_email,
                _password_hash(validated_password, salt),
                salt.hex(),
                created_at,
            ),
        )
        conn.commit()
        return {"id": cursor.lastrowid, "email": normalized_email, "created_at": created_at}
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise AccountError("Un compte existe déjà avec cette adresse e-mail") from exc
        raise
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    validate_password(password)
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, email, password_hash, password_salt, created_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise AccountError("Adresse e-mail ou mot de passe incorrect")
    candidate = _password_hash(password, bytes.fromhex(row["password_salt"]))
    if not hmac.compare_digest(candidate, row["password_hash"]):
        raise AccountError("Adresse e-mail ou mot de passe incorrect")
    return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
        conn.execute(
            """
            INSERT INTO sessions (user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                token_hash,
                (now + timedelta(days=SESSION_DURATION_DAYS)).isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def get_user_from_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT users.id, users.email, users.created_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()
