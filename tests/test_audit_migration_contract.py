"""No database access: validate controlled audit migration inputs."""
import pytest

from scripts.migrate_rhns_audit import ROLE, SCHEMA_FILE, validated_environment


def test_migration_requires_explicit_admin_url():
    with pytest.raises(ValueError):
        validated_environment({"RHNS_AUDIT_RUNTIME_PASSWORD": "a" * 48})


def test_migration_requires_strong_separate_role_password():
    with pytest.raises(ValueError):
        validated_environment({"RHNS_AUDIT_MIGRATION_URL": "postgresql://host/db",
                               "RHNS_AUDIT_RUNTIME_PASSWORD": "weak"})


def test_migration_password_rejects_unsafe_url_characters():
    with pytest.raises(ValueError):
        validated_environment({"RHNS_AUDIT_MIGRATION_URL": "postgresql://host/db",
                               "RHNS_AUDIT_RUNTIME_PASSWORD": "!" * 48})


def test_migration_schema_contains_append_only_trigger():
    schema = SCHEMA_FILE.read_text()
    assert "rhns_audit_no_mutation" in schema
    assert "BEFORE UPDATE OR DELETE" in schema
    assert ROLE == "rhns_audit_runtime"


def test_valid_configuration_never_leaks_values():
    value = "s" * 48
    assert validated_environment({"RHNS_AUDIT_MIGRATION_URL": "postgresql://host/db",
                                  "RHNS_AUDIT_RUNTIME_PASSWORD": value}) == (
                                      "postgresql://host/db", value)
