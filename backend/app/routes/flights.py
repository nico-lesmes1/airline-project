from fastapi import APIRouter, Query
from typing import List, Optional
from datetime import date
from app.db import get_connection, release_connection
from app.models import FlightAvailableOut, FlightSearchOut

router = APIRouter()
FARE_CLASSES = ["ECONOMY", "BUSINESS", "FIRST"]


@router.get("/flights/available", response_model=List[FlightAvailableOut])
def available_flights(
    from_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT f.flight_id,
                   f.route,
                   f.flight_date,
                   f.capacity - COALESCE(r.sold, 0) AS seats_available,
                   f.price_cent AS price_cents
            FROM flights f
            LEFT JOIN (
                SELECT flight_id, COUNT(*) AS sold
                FROM reservations
                WHERE status = 'CONFIRMED'
                GROUP BY flight_id
            ) r ON r.flight_id = f.flight_id
            WHERE f.flight_date >= COALESCE(%s, CURRENT_DATE)
              AND f.capacity - COALESCE(r.sold, 0) > 0
            ORDER BY f.flight_date ASC, f.price_cent ASC
            LIMIT %s
            """,
            (from_date, limit),
        )
        return [
            {**row, "available_fare_classes": FARE_CLASSES}
            for row in cur.fetchall()
        ]
    finally:
        release_connection(conn)

@router.get("/flights/search", response_model=List[FlightSearchOut])
def search_flights(
    origin: str = Query(...),
    destination: str = Query(...),
    date: date = Query(...),
):
    # Construir la ruta en el mismo formato que usa la BD: "ORIGEN-DESTINO"
    route = f"{origin.upper()}-{destination.upper()}"

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT f.flight_id,
                   f.route,
                   f.flight_date,
                   f.capacity - COALESCE(COUNT(r.reservation_id), 0) AS seats_available,
                   f.price_cent AS price_cents
            FROM flights f
            LEFT JOIN reservations r
              ON r.flight_id = f.flight_id
             AND r.status = 'CONFIRMED'
            WHERE f.route = %s
              AND f.flight_date = %s
            GROUP BY f.flight_id, f.route, f.flight_date, f.capacity, f.price_cent
            HAVING f.capacity - COALESCE(COUNT(r.reservation_id), 0) > 0
            ORDER BY f.price_cent ASC
            """,
            (route, date),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        release_connection(conn)