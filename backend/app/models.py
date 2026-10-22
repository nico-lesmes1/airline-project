from pydantic import BaseModel, Field
from datetime import date
from uuid import UUID


class FlightIn(BaseModel):
    flight_id: str
    route: str
    flight_date: date
    capacity: int = Field(ge=0)
    price_cent: int = Field(gt=0)

class FlightOut(BaseModel):
    flight_id: str
    route: str
    flight_date: date
    capacity: int
    price_cent: int


class ReservationIn(BaseModel):
    flight_id: str
    passenger_name: str
    fare_class: str

class ReservationOut(BaseModel):
    reservation_id: UUID
    flight_id: str
    status: str
    passenger_name: str

class FlightSearchOut(BaseModel):
    flight_id: str
    route: str
    flight_date: date
    seats_available: int
    price_cent: int