from fastapi import APIRouter, HTTPException
from uuid import uuid4, UUID
from app.db import get_connection, release_connection
from app.models import ReservationIn, ReservationOut
import psycopg2

router = APIRouter()

@router.post("/reservations", response_model=ReservationOut, status_code=201)
def create_reservation(body: ReservationIn):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT capacity FROM flights WHERE flight_id = %s FOR UPDATE",
            (body.flight_id,),
        )
        flight = cur.fetchone()
        if flight is None:
            conn.rollback()
            raise HTTPException(status_code=404, detail="flight not found")

        cur.execute(
            "SELECT COUNT(*) AS sold FROM reservations "
            "WHERE flight_id = %s AND status = 'CONFIRMED'",
            (body.flight_id,),
        )
        sold = cur.fetchone()["sold"]

        if sold >= flight["capacity"]:
            conn.rollback()
            raise HTTPException(status_code=409, detail="no seats available")

        reservation_id = uuid4()
        cur.execute(
            """
            INSERT INTO reservations
                (reservation_id, flight_id, passenger_name, fare_class, status)
            VALUES (%s, %s, %s, %s, 'CONFIRMED')
            RETURNING reservation_id, flight_id, status, passenger_name
            """,
            (reservation_id, body.flight_id, body.passenger_name, body.fare_class),
        )
        row = cur.fetchone()
        conn.commit()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"db error: {e}")
    finally:
        release_connection(conn)


@router.get("/reservations/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: UUID):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT reservation_id, flight_id, status, passenger_name "
            "FROM reservations WHERE reservation_id = %s",
            (reservation_id,),
        )
        row = cur.fetchone()
        cur.close()
        if row is None:
            raise HTTPException(status_code=404, detail="reservation not found")
        return row
    finally:
        release_connection(conn)