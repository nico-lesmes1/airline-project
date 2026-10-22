from fastapi import FastAPI
from app.db import get_connection

app = FastAPI(title="Airline API - Person A")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-check")
def db_check():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    cur.close()
    conn.close()
    return {"postgres_version": version["version"]}