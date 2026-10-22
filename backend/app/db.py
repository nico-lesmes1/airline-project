import psycopg2
import os
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, register_uuid

register_uuid()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "airline_db"),
    "user": os.getenv("DB_USER", "airline_app"),
    "password": os.getenv("DB_PASSWORD", "localdev123"),
    "port": int(os.getenv("DB_PORT", "5432")),
}

_connection_pool = ThreadedConnectionPool(
    minconn=int(os.getenv("DB_POOL_MIN", "20")),
    maxconn=int(os.getenv("DB_POOL_MAX", "60")),
    cursor_factory=RealDictCursor,
    **DB_CONFIG,
)


def get_connection():
    return _connection_pool.getconn()


def release_connection(conn):
    conn.rollback()
    _connection_pool.putconn(conn)