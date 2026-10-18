from scripts.apply_neon_migrations import classify_migration_state


def test_neon_migration_preflight_accepts_fresh_empty_schema() -> None:
    assert classify_migration_state(set(), [], False, False) == "fresh"


def test_neon_migration_preflight_accepts_only_the_expected_previous_revision() -> None:
    assert classify_migration_state(
        {"alembic_version", "users", "accounts"}, ["c5d7e9f1a2b4"], False, False
    ) == "migrate"


def test_neon_migration_preflight_recognizes_an_already_migrated_database() -> None:
    assert classify_migration_state(
        {"alembic_version", "users"}, ["1a2b3c4d5e6f"], True, True
    ) == "current"


def test_neon_migration_preflight_refuses_unexpected_or_partial_states() -> None:
    assert classify_migration_state(
        {"alembic_version", "users"}, ["other-revision"], False, False
    ) == "refuse"
    assert classify_migration_state(
        {"alembic_version", "users"}, ["c5d7e9f1a2b4"], True, False
    ) == "refuse"
