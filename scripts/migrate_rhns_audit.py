"""One-shot, separately permissioned RHNS PostgreSQL audit migration.

This script is deliberately NOT imported by the web API. Admin credentials
live only in the short-lived migration service, not the runtime service.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROLE = "rhns_audit_runtime"
SCHEMA_FILE = Path(__file__).resolve().parents[1] / "infra" / "postgres_audit_schema.sql"


def validated_environment(env: dict[str, str]) -> tuple[str, str]:
    admin_url = env.get("RHNS_AUDIT_MIGRATION_URL", "")
    password = env.get("RHNS_AUDIT_RUNTIME_PASSWORD", "")
    if not admin_url.startswith(("postgres://", "postgresql://")):
        raise ValueError("PostgreSQL migration URL is not configured")
    if not isinstance(password, str) or len(password) < 40:
        raise ValueError("Strong separate runtime-role password is required")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", password):
        raise ValueError("Runtime-role password must be URL-safe")
    return admin_url, password


def migrate(admin_url: str, password: str, *, attempts: int = 12) -> None:
    import psycopg
    from psycopg import sql
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    if ("CREATE TABLE IF NOT EXISTS rhns_audit_entries" not in schema
            or "rhns_audit_no_mutation" not in schema):
        raise RuntimeError("Expected audit schema missing")
    last = None
    for retry in range(attempts):
        try:
            with psycopg.connect(admin_url, connect_timeout=5) as db:
                with db.cursor() as cur:
                    # Serialized migrations even if a deploy is retried.
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", (628183023,))
                    cur.execute(schema)
                    cur.execute("SELECT current_database()")
                    database_name = cur.fetchone()[0]
                    cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,))
                    if cur.fetchone() is None:
                        cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} "
                                            "NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                            "NOREPLICATION").format(
                            sql.Identifier(ROLE), sql.Literal(password)))
                    else:
                        cur.execute(sql.SQL("ALTER ROLE {} WITH PASSWORD {} "
                                            "NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                            "NOREPLICATION").format(
                            sql.Identifier(ROLE), sql.Literal(password)))
                    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database_name), sql.Identifier(ROLE)))
                    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                        sql.Identifier(ROLE)))
                    cur.execute("REVOKE ALL ON TABLE public.rhns_audit_entries FROM PUBLIC")
                    cur.execute(sql.SQL(
                        "GRANT SELECT, INSERT ON public.rhns_audit_entries TO {}"
                    ).format(sql.Identifier(ROLE)))
                    cur.execute("REVOKE ALL ON FUNCTION public.rhns_reject_audit_mutation() FROM PUBLIC")
                    # Validate trigger and expected grants without making a
                    # synthetic entry in the user's real audit history.
                    cur.execute(
                        "SELECT COUNT(*) FROM pg_trigger WHERE tgrelid = "
                        "'public.rhns_audit_entries'::regclass "
                        "AND tgname='rhns_audit_no_mutation' AND NOT tgisinternal"
                    )
                    if cur.fetchone()[0] != 1:
                        raise RuntimeError("Audit mutation protection missing")
            print("RHNS schema and least-privilege role verified; no audit entries changed.")
            return
        except psycopg.OperationalError:
            last = "postgres_unavailable"
            if retry < attempts - 1:
                time.sleep(5)
    raise RuntimeError(last or "postgres_unavailable")


def main() -> int:
    try:
        url, pwd = validated_environment(dict(os.environ))
        migrate(url, pwd)
    except (ValueError, OSError, RuntimeError) as exc:
        # Never print connection URLs, passwords, detailed DB exceptions, or
        # environment variable values in provider logs.
        print("RHNS audit bootstrap blocked: " +
              ("invalid_configuration" if isinstance(exc, ValueError) else
               "migration_unavailable"), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
