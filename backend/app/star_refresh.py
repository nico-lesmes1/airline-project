import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.db import get_connection, release_connection


_TABLE = "star_refresh_runs"


def ensure_refresh_table() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(91001)")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
                job_name TEXT NOT NULL,
                job_run_id TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()
        cur.close()
    finally:
        release_connection(conn)


def start_refresh() -> str:
    job_name = os.getenv("GLUE_STAR_JOB_NAME")
    if not job_name:
        raise HTTPException(
            status_code=503,
            detail="Star refresh is unavailable until GLUE_STAR_JOB_NAME is configured",
        )

    client = boto3.client("glue", region_name=os.getenv("AWS_REGION", "us-east-1"))
    arguments = {}
    raw_events_uri = os.getenv("RAW_EVENTS_URI")
    database = os.getenv("ATHENA_STAR_DATABASE")
    if raw_events_uri:
        arguments["--raw_events_uri"] = raw_events_uri
    if database:
        arguments["--database"] = database

    try:
        run_id = client.start_job_run(
            JobName=job_name,
            Arguments=arguments,
        )["JobRunId"]
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(status_code=502, detail="Unable to start the star refresh job") from error

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO {_TABLE} (singleton_id, job_name, job_run_id, updated_at)
            VALUES (1, %s, %s, NOW())
            ON CONFLICT (singleton_id) DO UPDATE
            SET job_name = EXCLUDED.job_name,
                job_run_id = EXCLUDED.job_run_id,
                updated_at = NOW()
            """,
            (job_name, run_id),
        )
        conn.commit()
        cur.close()
    finally:
        release_connection(conn)
    return run_id


def refresh_status() -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT job_name, job_run_id FROM {_TABLE} WHERE singleton_id = 1")
        row = cur.fetchone()
        cur.close()
    finally:
        release_connection(conn)

    if row is None:
        return {"state": "FAILED"}

    client = boto3.client("glue", region_name=os.getenv("AWS_REGION", "us-east-1"))
    try:
        state = client.get_job_run(
            JobName=row["job_name"],
            RunId=row["job_run_id"],
            PredecessorsIncluded=False,
        )["JobRun"]["JobRunState"]
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(status_code=502, detail="Unable to read star refresh status") from error

    if state in {"STARTING", "RUNNING", "STOPPING", "WAITING"}:
        return {"state": "RUNNING"}
    if state == "SUCCEEDED":
        return {"state": "SUCCEEDED"}
    return {"state": "FAILED"}
