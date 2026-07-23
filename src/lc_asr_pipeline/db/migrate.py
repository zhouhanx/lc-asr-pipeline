"""Small, checksum-aware PostgreSQL migration runner."""

from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg

from lc_asr_pipeline.core.config import get_settings


def _migration_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError(f"No migrations found in {directory}")
    return files


def run_migrations() -> list[str]:
    """Apply pending SQL migrations and return the applied filenames."""
    settings = get_settings()
    files = _migration_files(settings.migrations_path)
    applied: list[str] = []

    with psycopg.connect(settings.postgres_conninfo) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('lc_asr_pipeline_migrations'))")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                checksum char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

        for path in files:
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            existing = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version = %s",
                (path.name,),
            ).fetchone()
            if existing:
                if existing[0] != checksum:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue

            connection.execute(sql, prepare=False)
            connection.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                (path.name, checksum),
            )
            applied.append(path.name)

    return applied


def main() -> None:
    """CLI entrypoint."""
    applied = run_migrations()
    print("Applied migrations: " + (", ".join(applied) if applied else "none"))


if __name__ == "__main__":
    main()
