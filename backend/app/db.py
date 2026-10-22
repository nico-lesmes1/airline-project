import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, register_uuid

register_uuid()

DB_CONFIG = {
    "host": "localhost",
    "database": "airline_db",
    "user": "airline_app",
    "password": "localdev123",
    "port": 5432,
}

_connection_pool = ThreadedConnectionPool(
    minconn=20,
    maxconn=40,
    cursor_factory=RealDictCursor,
    **DB_CONFIG,
)


def get_connection():
    return _connection_pool.getconn()


def release_connection(conn):
    conn.rollback()
    _connection_pool.putconn(conn)