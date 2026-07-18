import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import bootstrap_schema


BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_migration(filename):
    path = BACKEND_DIR / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInspector:
    def __init__(self, tables=(), indexes=None, unique_constraints=None):
        self.tables = set(tables)
        self.indexes = indexes or {}
        self.unique_constraints = unique_constraints or {}

    def has_table(self, table_name):
        return table_name in self.tables

    def get_indexes(self, table_name):
        return [{"name": name} for name in self.indexes.get(table_name, ())]

    def get_unique_constraints(self, table_name):
        return [{"name": name} for name in self.unique_constraints.get(table_name, ())]


class MigrationIdempotencyTests(unittest.TestCase):
    def test_git_refs_upgrade_preserves_an_existing_table(self):
        migration = load_migration("c2b9e3a1d4f6_git_ref_cache.py")
        inspector = FakeInspector(
            tables={"git_refs"},
            indexes={"git_refs": {"ix_git_refs_repo_url"}},
            unique_constraints={"git_refs": {"uq_git_refs_ref_key"}},
        )

        with patch.object(migration.op, "get_bind", return_value=object()), \
                patch.object(migration.sa, "inspect", return_value=inspector), \
                patch.object(migration.op, "create_table") as create_table, \
                patch.object(migration.op, "create_index") as create_index:
            migration.upgrade()

        create_table.assert_not_called()
        create_index.assert_not_called()

    def test_user_operation_logs_upgrade_preserves_an_existing_table(self):
        migration = load_migration("7c9a4f21d801_user_operation_logs.py")
        inspector = FakeInspector(
            tables={"user_operation_logs"},
            indexes={
                "user_operation_logs": {
                    "ix_user_operation_logs_operator_username",
                    "ix_user_operation_logs_request_path",
                    "ix_user_operation_logs_created_at",
                }
            },
        )

        with patch.object(migration.op, "get_bind", return_value=object()), \
                patch.object(migration.sa, "inspect", return_value=inspector), \
                patch.object(migration.op, "create_table") as create_table, \
                patch.object(migration.op, "create_index") as create_index:
            migration.upgrade()

        create_table.assert_not_called()
        create_index.assert_not_called()

    def test_bootstrap_schema_contains_user_operation_logs_before_stamping_head(self):
        ddl = "\n".join(bootstrap_schema.DDL_STATEMENTS).lower()

        self.assertIn("create table if not exists user_operation_logs", ddl)


if __name__ == "__main__":
    unittest.main()
