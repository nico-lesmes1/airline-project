from fastapi import APIRouter, HTTPException
from app.db import get_connection, release_connection
from app.models import FlightIn, FlightOut
from app.star_refresh import refresh_status, start_refresh
import psycopg2

router = APIRouter()


@router.post("/admin/refresh-star", status_code=202)
def refresh_star():
    return {"job_id": start_refresh()}


@router.get("/admin/refresh-status")
def get_refresh_status():
    return refresh_status()


@router.post("/admin/flights", response_model=FlightOut, status_code=201)
def create_flight(flight: FlightIn):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO flights (flight_id, route, flight_date, capacity, price_cents)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (flight_id) DO NOTHING
            RETURNING flight_id, route, flight_date, capacity, price_cents
            """,
            (flight.flight_id, flight.route, flight.flight_date,
             flight.capacity, flight.price_cents),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise HTTPException(status_code=409, detail="flight_id already exists")
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"db error: {e}")
    finally:
        release_connection(conn)