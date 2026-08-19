import uuid

from psycopg import sql

from app import db


def create_test_schema() -> str:
    """Crée un schéma PostgreSQL isolé et retourne le schéma configuré auparavant."""
    original_schema = db.DATABASE_SCHEMA
    db.DATABASE_SCHEMA = f"test_{uuid.uuid4().hex}"
    db.init_db()
    return original_schema


def drop_test_schema(original_schema: str) -> None:
    """Supprime uniquement le schéma temporaire créé par le test courant."""
    test_schema = db.DATABASE_SCHEMA
    conn = db.get_connection()
    try:
        conn.execute("SET search_path TO public")
        conn.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(test_schema))
        )
        conn.commit()
    finally:
        conn.close()
        db.DATABASE_SCHEMA = original_schema
