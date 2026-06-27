from pathlib import Path
import re

import pymysql
from sqlalchemy.engine.url import make_url

from app.config import Config


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS branches (
        id INTEGER NOT NULL AUTO_INCREMENT,
        address VARCHAR(255) NOT NULL,
        tag_version VARCHAR(255),
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER NOT NULL AUTO_INCREMENT,
        log_name VARCHAR(255) NOT NULL,
        log_file_path VARCHAR(500) NOT NULL,
        created_at DATETIME,
        count INTEGER,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS git_refs (
        id INTEGER NOT NULL AUTO_INCREMENT,
        ref_key VARCHAR(64) NOT NULL,
        repo_url VARCHAR(500) NOT NULL,
        ref_name VARCHAR(255) NOT NULL,
        ref_type VARCHAR(20) NOT NULL,
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id),
        UNIQUE KEY uq_git_refs_ref_key (ref_key),
        KEY ix_git_refs_repo_url (repo_url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS module_branches (
        id INTEGER NOT NULL AUTO_INCREMENT,
        module_id INTEGER NOT NULL,
        branch_id INTEGER NOT NULL,
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS modules (
        id INTEGER NOT NULL AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        branch VARCHAR(255),
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_modules (
        id INTEGER NOT NULL AUTO_INCREMENT,
        product_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL,
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER NOT NULL AUTO_INCREMENT,
        name VARCHAR(255) NOT NULL,
        description VARCHAR(1000),
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS query_records (
        id INTEGER NOT NULL AUTO_INCREMENT,
        product_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL,
        log_id INTEGER,
        log_file_path VARCHAR(500) NOT NULL,
        branch_url VARCHAR(500) NOT NULL,
        branch_version VARCHAR(100) NOT NULL,
        created_at DATETIME,
        answer INTEGER,
        status VARCHAR(32),
        log_hash VARCHAR(64),
        error_fingerprint VARCHAR(64),
        duration_ms INTEGER,
        model_name VARCHAR(128),
        hit_cache BOOLEAN,
        knowledge_case_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(product_id) REFERENCES products (id),
        FOREIGN KEY(module_id) REFERENCES modules (id),
        FOREIGN KEY(log_id) REFERENCES logs (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_knowledge_cases (
        id INTEGER NOT NULL AUTO_INCREMENT,
        product_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL,
        error_fingerprint VARCHAR(64) NOT NULL,
        error_type VARCHAR(255),
        error_message TEXT,
        stack_top_file VARCHAR(500),
        stack_top_line INTEGER,
        branch_url VARCHAR(500),
        branch_version VARCHAR(100),
        log_excerpt TEXT,
        code_files TEXT,
        code_snippets TEXT,
        issue_category VARCHAR(64) NOT NULL DEFAULT 'unknown',
        conclusion_summary TEXT,
        root_cause TEXT,
        solution TEXT,
        ai_analysis TEXT,
        evidence TEXT,
        confidence FLOAT,
        hit_count INTEGER NOT NULL DEFAULT 0,
        last_hit_at DATETIME,
        created_at DATETIME,
        updated_at DATETIME,
        PRIMARY KEY (id),
        UNIQUE KEY uq_knowledge_case_scope_fingerprint (product_id, module_id, error_fingerprint),
        KEY ix_analysis_knowledge_cases_error_fingerprint (error_fingerprint),
        FOREIGN KEY(product_id) REFERENCES products (id),
        FOREIGN KEY(module_id) REFERENCES modules (id)
    )
    """,
]


def current_revision():
    versions_dir = Path(__file__).resolve().parent / "migrations" / "versions"
    revisions = {}
    down_revisions = set()
    for migration_file in versions_dir.glob("*.py"):
        text = migration_file.read_text(encoding="utf-8")
        revision_match = re.search(r"^revision = ['\"]([^'\"]+)['\"]", text, re.MULTILINE)
        down_match = re.search(r"^down_revision = ['\"]([^'\"]+)['\"]", text, re.MULTILINE)
        if revision_match:
            revision = revision_match.group(1)
            revisions[revision] = migration_file
            if down_match:
                down_revisions.add(down_match.group(1))
    heads = [revision for revision in revisions if revision not in down_revisions]
    if heads:
        return sorted(heads)[-1]
    raise RuntimeError("没有找到 migrations/versions 下的 revision")


def connect():
    url = make_url(Config.SQLALCHEMY_DATABASE_URI)
    return pymysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        database=url.database,
        charset="utf8mb4",
    )


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table_name,),
    )
    return cursor.fetchone()[0] > 0


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone()[0] > 0


def index_exists(cursor, table_name, index_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
        """,
        (table_name, index_name),
    )
    return cursor.fetchone()[0] > 0


def foreign_key_exists(cursor, table_name, constraint_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND constraint_name = %s
          AND constraint_type = 'FOREIGN KEY'
        """,
        (table_name, constraint_name),
    )
    return cursor.fetchone()[0] > 0


def add_column_if_missing(cursor, table_name, column_name, definition):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def add_index_if_missing(cursor, table_name, index_name, column_name):
    if not index_exists(cursor, table_name, index_name):
        cursor.execute(f"CREATE INDEX {index_name} ON {table_name} ({column_name})")


def drop_foreign_keys(cursor, table_name, column_name, referenced_table=None):
    params = [table_name, column_name]
    referenced_filter = ""
    if referenced_table:
        referenced_filter = "AND referenced_table_name = %s"
        params.append(referenced_table)
    cursor.execute(
        f"""
        SELECT constraint_name
        FROM information_schema.key_column_usage
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
          AND referenced_table_name IS NOT NULL
          {referenced_filter}
        """,
        tuple(params),
    )
    for (constraint_name,) in cursor.fetchall():
        cursor.execute(f"ALTER TABLE {table_name} DROP FOREIGN KEY {constraint_name}")


def has_invalid_reference(cursor, table_name, column_name, referenced_table, referenced_column="id"):
    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name} source
        LEFT JOIN {referenced_table} target
          ON source.{column_name} = target.{referenced_column}
        WHERE source.{column_name} IS NOT NULL
          AND target.{referenced_column} IS NULL
        """
    )
    return cursor.fetchone()[0] > 0


def add_foreign_key_if_safe(cursor, table_name, constraint_name, column_name, referenced_table):
    if foreign_key_exists(cursor, table_name, constraint_name):
        return
    if has_invalid_reference(cursor, table_name, column_name, referenced_table):
        print(
            f"skip foreign key {constraint_name}: {table_name}.{column_name} "
            f"has rows missing in {referenced_table}.id"
        )
        return
    cursor.execute(
        f"""
        ALTER TABLE {table_name}
        ADD CONSTRAINT {constraint_name}
        FOREIGN KEY ({column_name}) REFERENCES {referenced_table} (id)
        """
    )


def ensure_query_records_schema(cursor):
    if not table_exists(cursor, "query_records"):
        return

    add_column_if_missing(cursor, "query_records", "log_id", "INTEGER")
    add_column_if_missing(cursor, "query_records", "status", "VARCHAR(32)")
    add_column_if_missing(cursor, "query_records", "log_hash", "VARCHAR(64)")
    add_column_if_missing(cursor, "query_records", "error_fingerprint", "VARCHAR(64)")
    add_column_if_missing(cursor, "query_records", "duration_ms", "INTEGER")
    add_column_if_missing(cursor, "query_records", "model_name", "VARCHAR(128)")
    add_column_if_missing(cursor, "query_records", "hit_cache", "BOOLEAN DEFAULT FALSE")
    add_column_if_missing(cursor, "query_records", "knowledge_case_id", "INTEGER")
    add_index_if_missing(cursor, "query_records", "ix_query_records_error_fingerprint", "error_fingerprint")

    # Old schema incorrectly linked module_id to logs.id. module_id now means modules.id.
    drop_foreign_keys(cursor, "query_records", "module_id", referenced_table="logs")
    add_foreign_key_if_safe(cursor, "query_records", "fk_query_records_product_id_products", "product_id", "products")
    add_foreign_key_if_safe(cursor, "query_records", "fk_query_records_module_id_modules", "module_id", "modules")
    add_foreign_key_if_safe(cursor, "query_records", "fk_query_records_log_id_logs", "log_id", "logs")
    add_foreign_key_if_safe(
        cursor,
        "query_records",
        "fk_query_records_knowledge_case_id",
        "knowledge_case_id",
        "analysis_knowledge_cases",
    )


def bootstrap_schema():
    revision = current_revision()
    connection = connect()
    try:
        with connection.cursor() as cursor:
            for ddl in DDL_STATEMENTS:
                cursor.execute(ddl)
            ensure_query_records_schema(cursor)
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                ")"
            )
            cursor.execute("SELECT COUNT(*) FROM alembic_version")
            row_count = cursor.fetchone()[0]
            if row_count == 0:
                cursor.execute("INSERT INTO alembic_version (version_num) VALUES (%s)", (revision,))
            else:
                cursor.execute("UPDATE alembic_version SET version_num = %s", (revision,))
        connection.commit()
    finally:
        connection.close()
    print(f"schema ready, alembic revision: {revision}")


if __name__ == "__main__":
    bootstrap_schema()
