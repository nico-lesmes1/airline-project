from fastapi import FastAPI
from app.db import get_connection, release_connection
from app.routes import admin, flights, reservations

app = FastAPI(title="Airline API - Person A")

app.include_router(admin.router)
app.include_router(flights.router)
app.include_router(reservations.router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-check")
def db_check():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        cur.close()
        return {"postgres_version": version["version"]}
    finally:
        release_connection(conn)