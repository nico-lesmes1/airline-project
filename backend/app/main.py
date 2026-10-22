from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.db import get_connection
from app.routes import admin, analytics, flights, reservations

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

@app.get("/health")
def health():
    return {"status": "ok"}