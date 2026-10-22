import pytest
import threading
import uuid
import requests

BASE = "http://localhost:8000"

def create_flight(capacity: int) -> str:
    fid = f"CONC-{uuid.uuid4()}"
    r = requests.post(f"{BASE}/admin/flights", json={
        "flight_id": fid, "route": "BOG-MDE",
        "flight_date": "2024-04-01", "capacity": capacity, "price_cent": 9000,
    })
    assert r.status_code == 201, r.text
    return fid

def run_concurrent_booking(flight_id: str, n_clients: int):
    """Dispara n_clients POST /reservations lo más simultáneo posible."""
    barrier = threading.Barrier(n_clients)
    results = []

    def book(i):
        barrier.wait()  # todos esperan aquí hasta que lleguen los n
        r = requests.post(f"{BASE}/reservations", json={
            "flight_id": flight_id,
            "passenger_name": f"p{i}",
            "fare_class": "ECONOMY",
        })
        results.append(r.status_code)

    threads = [threading.Thread(target=book, args=(i,)) for i in range(n_clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results

def test_r2_one_seat_exactly_one_201():
    fid = create_flight(capacity=1)
    codes = run_concurrent_booking(fid, n_clients=50)
    assert codes.count(201) == 1, f"esperado 1x201, got {codes.count(201)}: {codes}"
    assert codes.count(409) == 49, f"esperado 49x409, got {codes.count(409)}: {codes}"
    assert all(c in (201, 409) for c in codes), f"hubo 5xx u otro: {codes}"

def test_r2_k_seats_exactly_k_201():
    K = 5
    fid = create_flight(capacity=K)
    codes = run_concurrent_booking(fid, n_clients=50)
    assert codes.count(201) == K, f"esperado {K}x201, got {codes.count(201)}: {codes}"
    assert codes.count(409) == 50 - K, f"esperado {50-K}x409, got {codes.count(409)}: {codes}"
    assert all(c in (201, 409) for c in codes), f"hubo 5xx u otro: {codes}"

def test_r2_flight_shows_no_seats_after():
    fid = create_flight(capacity=2)
    codes = run_concurrent_booking(fid, n_clients=20)
    assert codes.count(201) == 2
    # buscar el vuelo: debe estar vacío
    r = requests.get(f"{BASE}/flights/search",
                     params={"origin": "BOG", "destination": "MDE", "date": "2024-04-01"})
    flights = r.json()
    assert all(f["flight_id"] != fid for f in flights), "el vuelo aún aparece con asientos"