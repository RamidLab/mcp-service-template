#!/usr/bin/env python3
"""自动创建 PostgreSQL / MySQL 数据库（如果不存在）。

通过连接 postgres/mysql 系统数据库检测并创建目标库，
解决 persistent volume 复用时 PostgreSQL 不重新执行 init 的问题。

使用方式：
    # PostgreSQL
    python3 create_db.py postgresql --host HOST --port PORT --user USER --password PASS --db TARGET_DB

    # MySQL
    python3 create_db.py mysql --host HOST --port PORT --user USER --password PASS --db TARGET_DB
"""

import argparse
import sys


def _ensure_pg(args: argparse.Namespace) -> None:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, quote_ident

    conn = psycopg2.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        dbname="postgres",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (args.db,))
    exists = cur.fetchone()
    if not exists:
        cur.execute(f"CREATE DATABASE {quote_ident(args.db, cur)} ENCODING 'UTF8'")
        print(f"[INFO] 数据库 {args.db} 创建成功")
    else:
        print(f"[INFO] 数据库 {args.db} 已存在，跳过创建")
    conn.close()


def _ensure_mysql(args: argparse.Namespace) -> None:
    import pymysql

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (args.db,)
    )
    exists = cur.fetchone()
    if not exists:
        cur.execute(f"CREATE DATABASE `{args.db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"[INFO] 数据库 {args.db} 创建成功")
    else:
        print(f"[INFO] 数据库 {args.db} 已存在，跳过创建")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="自动创建数据库")
    parser.add_argument("engine", choices=["postgresql", "mysql"])
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default="")
    parser.add_argument("--db", required=True, help="目标数据库名")
    args = parser.parse_args()

    try:
        if args.engine == "postgresql":
            _ensure_pg(args)
        elif args.engine == "mysql":
            _ensure_mysql(args)
    except Exception as e:
        # 连接失败或创建失败时，让日志输出便于排查
        print(f"[WARN] 自动创建数据库 {args.db} 失败: {e}", file=sys.stderr)
        # 不退出，允许应用继续启动（可能数据库已存在或手动创建）


if __name__ == "__main__":
    main()
