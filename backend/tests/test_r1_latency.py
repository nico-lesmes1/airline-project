import time
import uuid
import statistics
import requests
from concurrent.futures import ThreadPoolExecutor

BASE = "http://localhost:8000"

def setup_flights(n=20):
    for i in range(n):
        requests.post(f"{BASE}/admin/flights", json={
            "flight_id": f"R1-{uuid.uuid4()}-{i}",
            "route": "BOG-MDE",
            "flight_date": "2024-05-01",
            "capacity": 10,
            "price_cent": 9000 + i,
        })

def one_request(_):
    t0 = time.perf_counter()
    r = requests.get(f"{BASE}/flights/search",
                     params={"origin": "BOG", "destination": "MDE", "date": "2024-05-01"})
    dt = (time.perf_counter() - t0) * 1000  # ms
    return r.status_code, dt

def test_r1_p95_under_1s():
    setup_flights(20)
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(one_request, range(100)))
    codes = [c for c, _ in results]
    latencies = sorted(dt for _, dt in results)
    assert all(c == 200 for c in codes), f"status codes: {set(codes)}"
    p95 = latencies[int(0.95 * len(latencies)) - 1]
    print(f"p95 = {p95:.1f} ms, max = {max(latencies):.1f} ms")
    assert p95 <= 1000, f"p95 {p95:.1f} ms > 1000 ms"