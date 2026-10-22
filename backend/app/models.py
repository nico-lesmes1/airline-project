from pydantic import BaseModel, Field, model_validator
from datetime import date
from uuid import UUID


class FlightIn(BaseModel):
    flight_id: str
    route: str
    flight_date: date
    capacity: int = Field(ge=0)
    price_cents: int = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_price_name(cls, values):
        if isinstance(values, dict) and "price_cents" not in values and "price_cent" in values:
            values = {**values, "price_cents": values["price_cent"]}
        return values

class FlightOut(BaseModel):
    flight_id: str
    route: str
    flight_date: date
    capacity: int
    price_cents: int


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
    price_cents: int


class FlightAvailableOut(FlightSearchOut):
    available_fare_classes: list[str]