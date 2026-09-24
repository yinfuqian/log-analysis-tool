"""校验 skill_run_records.progress 的列类型与缺表自动创建、老表自动升级逻辑。"""
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.dialects import mysql, sqlite

import bootstrap_schema
from app.skillrun.models.model import SkillRunRecord


class FakeCursor:
    """记录执行过的 SQL，并按需返回 information_schema 的查询结果。"""

    def __init__(self, table_present=True, column_type=None):
        self.table_present = table_present
        self.column_type = column_type
        self.statements = []

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        self.statements.append(statement)
        # MySQL 的 DDL 立即生效，建表之后 information_schema 里就能看到 LONGTEXT 的 progress。
        if statement.upper().startswith("CREATE TABLE IF NOT EXISTS SKILL_RUN_RECORDS"):
            self.table_present = True
            self.column_type = "longtext"

    def fetchone(self):
        statement = self.statements[-1]
        if "information_schema.tables" in statement:
            return (1 if self.table_present else 0,)
        if "information_schema.columns" in statement:
            return None if self.column_type is None else (self.column_type,)
        raise AssertionError(f"未预期的查询：{statement}")

    def alters(self):
        """返回本次执行过的 ALTER TABLE 语句，便于断言自动升级行为。"""
        return [item for item in self.statements if item.upper().startswith("ALTER TABLE")]


class SkillRunProgressColumnTests(unittest.TestCase):
    def test_model_progress_uses_longtext_on_mysql(self):
        column = SkillRunRecord.__table__.c.progress

        self.assertEqual(str(column.type.compile(dialect=mysql.dialect())), "LONGTEXT")

    def test_model_progress_stays_text_on_other_dialects(self):
        column = SkillRunRecord.__table__.c.progress

        self.assertEqual(str(column.type.compile(dialect=sqlite.dialect())), "TEXT")

    def test_bootstrap_creates_table_with_longtext_progress_when_missing(self):
        cursor = FakeCursor(table_present=False)

        bootstrap_schema.ensure_skill_run_records_schema(cursor)

        created = [
            item for item in cursor.statements if "CREATE TABLE IF NOT EXISTS skill_run_records" in item
        ]
        self.assertEqual(len(created), 1)
        self.assertIn("progress LONGTEXT", created[0])
        self.assertEqual(cursor.alters(), [])

    def test_bootstrap_upgrades_existing_text_progress_to_longtext(self):
        cursor = FakeCursor(table_present=True, column_type="text")

        bootstrap_schema.ensure_skill_run_records_schema(cursor)

        self.assertEqual(
            cursor.alters(),
            ["ALTER TABLE skill_run_records MODIFY COLUMN progress LONGTEXT NULL"],
        )

    def test_bootstrap_adds_progress_column_when_absent(self):
        cursor = FakeCursor(table_present=True, column_type=None)

        bootstrap_schema.ensure_skill_run_records_schema(cursor)

        self.assertEqual(
            cursor.alters(),
            ["ALTER TABLE skill_run_records ADD COLUMN progress LONGTEXT NULL"],
        )

    def test_bootstrap_skips_when_progress_is_already_longtext(self):
        cursor = FakeCursor(table_present=True, column_type="longtext")

        bootstrap_schema.ensure_skill_run_records_schema(cursor)

        self.assertEqual(cursor.alters(), [])


if __name__ == "__main__":
    unittest.main()
