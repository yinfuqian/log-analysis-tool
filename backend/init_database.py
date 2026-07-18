"""init database 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from sqlalchemy.engine.url import make_url
import pymysql

from app.config import Config


def create_database_if_missing():
    """创建并返回 create_database_if_missing 对应的业务数据，保持现有调用约定。"""
    url = make_url(Config.SQLALCHEMY_DATABASE_URI)
    database = url.database
    if not database:
        raise RuntimeError("SQLALCHEMY_DATABASE_URI 中没有数据库名")

    connect_kwargs = {
        "host": url.host or "localhost",
        "port": url.port or 3306,
        "user": url.username,
        "password": url.password or "",
        "charset": "utf8mb4",
    }

    safe_database = database.replace("`", "``")
    connection = pymysql.connect(**connect_kwargs)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{safe_database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        connection.commit()
    finally:
        connection.close()

    print(f"database ready: {database}")


if __name__ == "__main__":
    create_database_if_missing()
