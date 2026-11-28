"""Guard against shipping an RHNS image without its audit package/migrator.

Offline build-contract checks; live PostgreSQL integration remains separate.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_docker_image_contains_runtime_audit_dependencies():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "from audit.ledger import" in main
    assert "from audit.postgres_ledger import" in main
    for directive in (
        "COPY main.py .",
        "COPY audit/ ./audit/",
        "COPY infra/postgres_audit_schema.sql ./infra/postgres_audit_schema.sql",
        "COPY scripts/migrate_rhns_audit.py ./scripts/migrate_rhns_audit.py",
    ):
        assert directive in docker
    assert (ROOT / "scripts/migrate_rhns_audit.py").is_file()
    assert (ROOT / "infra/postgres_audit_schema.sql").is_file()
