from fastapi import APIRouter, HTTPException
from uuid import uuid4, UUID
from app.db import get_connection, release_connection
from app.events import publisher, reservation_event
from app.models import ReservationIn, ReservationOut
import psycopg2

router = APIRouter()

@router.post("/reservations", response_model=ReservationOut, status_code=201)
def create_reservation(body: ReservationIn):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT capacity, route, flight_date, price_cents "
            "FROM flights WHERE flight_id = %s FOR UPDATE",
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
        event, partition_key = reservation_event(
            "reservation_created",
            reservation_id=row["reservation_id"],
            flight_id=row["flight_id"],
            route=flight["route"],
            flight_date=flight["flight_date"],
            fare_class=body.fare_class,
            price_cents=flight["price_cents"],
        )
        publisher.publish(event, partition_key, wait_seconds=0.2)
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


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationOut,
    status_code=200,
)
def cancel_reservation(reservation_id: UUID):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.reservation_id, r.flight_id, r.status, r.passenger_name,
                   r.fare_class, f.route, f.flight_date,
                   f.price_cents
            FROM reservations r
            JOIN flights f ON f.flight_id = r.flight_id
            WHERE r.reservation_id = %s
            FOR UPDATE OF r
            """,
            (reservation_id,),
        )
        reservation = cur.fetchone()
        if reservation is None:
            conn.rollback()
            raise HTTPException(status_code=404, detail="reservation not found")
        if reservation["status"] != "CONFIRMED":
            conn.rollback()
            raise HTTPException(status_code=409, detail="reservation is already cancelled")

        cur.execute(
            """
            UPDATE reservations
            SET status = 'CANCELLED'
            WHERE reservation_id = %s AND status = 'CONFIRMED'
            RETURNING reservation_id, flight_id, status, passenger_name
            """,
            (reservation_id,),
        )
        row = cur.fetchone()
        conn.commit()
        event, partition_key = reservation_event(
            "reservation_cancelled",
            reservation_id=reservation["reservation_id"],
            flight_id=reservation["flight_id"],
            route=reservation["route"],
            flight_date=reservation["flight_date"],
            fare_class=reservation["fare_class"],
            price_cents=reservation["price_cents"],
        )
        publisher.publish(event, partition_key, wait_seconds=0.2)
        cur.close()
        return row
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"db error: {e}")
    finally:
        release_connection(conn)