from datetime import date
import os
import time

from fastapi import APIRouter, HTTPException, Query
from app.db import get_connection, release_connection

router = APIRouter()


def _athena_occupancy(route: str, month: str):
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Athena integration is not installed") from exc

    database = os.getenv("ATHENA_DATABASE")
    table = os.getenv("ATHENA_METRICS_TABLE", "route_month_metrics")
    output = os.getenv("ATHENA_OUTPUT_LOCATION")
    if not database or not output:
        raise HTTPException(status_code=503, detail="Athena is not configured")

    client = boto3.client("athena", region_name=os.getenv("AWS_REGION"))
    query = (
        f"SELECT route, month, occupancy, seats_sold, seats_capacity "
        f"FROM {table} WHERE route = :route AND month = :month"
    )
    try:
        started = client.start_query_execution(
            QueryString=query.replace(":route", "'" + route.replace("'", "''") + "'")
            .replace(":month", "'" + month + "'"),
            QueryExecutionContext={"Database": database},
            ResultConfiguration={"OutputLocation": output},
        )
        execution_id = started["QueryExecutionId"]
        deadline = time.monotonic() + float(os.getenv("ATHENA_TIMEOUT_SECONDS", "8"))
        while time.monotonic() < deadline:
            execution = client.get_query_execution(QueryExecutionId=execution_id)
            state = execution["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                results = client.get_query_results(QueryExecutionId=execution_id)["ResultSet"]["Rows"]
                if len(results) < 2:
                    raise HTTPException(status_code=404, detail="analytics data not found")
                values = [item.get("VarCharValue") for item in results[1]["Data"]]
                return {
                    "route": values[0],
                    "month": values[1],
                    "occupancy": float(values[2]),
                    "seats_sold": int(values[3]),
                    "seats_capacity": int(values[4]),
                }
            if state in {"FAILED", "CANCELLED"}:
                reason = execution["QueryExecution"]["Status"].get("StateChangeReason", "Athena query failed")
                raise HTTPException(status_code=502, detail=reason)
            time.sleep(0.2)
        raise HTTPException(status_code=504, detail="Athena query timed out")
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="Athena request failed") from exc


@router.get("/analytics/occupancy")
def occupancy(
    route: str = Query(..., min_length=3),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
):
    year, month_number = (int(value) for value in month.split("-"))
    if not 1 <= month_number <= 12:
        raise HTTPException(status_code=422, detail="month must be between 01 and 12")
    month_start = date(year, month_number, 1)
    if month_number == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month_number + 1, 1)

    normalized_route = route.strip().upper()
    if os.getenv("ANALYTICS_BACKEND", "postgres").lower() == "athena":
        return _athena_occupancy(normalized_route, month)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(SUM(f.capacity), 0) AS seats_capacity,
                COALESCE(SUM(r.seats_sold), 0) AS seats_sold
            FROM flights f
            LEFT JOIN (
                SELECT flight_id, COUNT(*) AS seats_sold
                FROM reservations
                WHERE status = 'CONFIRMED'
                GROUP BY flight_id
            ) r ON r.flight_id = f.flight_id
            WHERE f.route = %s
              AND f.flight_date >= %s
              AND f.flight_date < %s
            """,
            (normalized_route, month_start, month_end),
        )
        row = cur.fetchone()
        capacity = int(row["seats_capacity"])
        sold = int(row["seats_sold"])
        if capacity == 0:
            raise HTTPException(status_code=404, detail="analytics data not found")
        occupancy_value = sold / capacity if capacity else 0
        return {
            "route": normalized_route,
            "month": month,
            "occupancy": occupancy_value,
            "seats_sold": sold,
            "seats_capacity": capacity,
        }
    finally:
        release_connection(conn)
