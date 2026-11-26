from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.db import get_connection
from app.routes import admin, analytics, flights, reservations
from app.live_view import live_consumer
from app.star_refresh import ensure_refresh_table

app = FastAPI(title="Airline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5500").split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(flights.router)
app.include_router(reservations.router)


@app.on_event("startup")
def start_streaming_services():
    ensure_refresh_table()
    live_consumer.start()


@app.on_event("shutdown")
def stop_streaming_services():
    live_consumer.stop()


@app.get("/health")
def health():
    return {"status": "ok"}