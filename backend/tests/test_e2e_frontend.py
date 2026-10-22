import uuid

import pytest
import requests
from playwright.sync_api import sync_playwright


API = "http://localhost:8000"
FRONT = "http://localhost:5500"


@pytest.fixture
def flight_with_seats():
    flight_id = f"E2E-{uuid.uuid4()}"
    response = requests.post(
        f"{API}/admin/flights",
        json={
            "flight_id": flight_id,
            "route": "BOG-MDE",
            "flight_date": "2024-06-01",
            "capacity": 5,
            "price_cent": 12000,
        },
        timeout=10,
    )
    assert response.status_code == 201, response.text
    yield flight_id


def test_r8_full_flow(flight_with_seats):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{FRONT}/index.html")

        page.fill('[data-testid="search-origin"]', "BOG")
        page.fill('[data-testid="search-destination"]', "MDE")
        page.fill('[data-testid="search-date"]', "2024-06-01")
        page.click('[data-testid="search-submit"]')
        page.wait_for_selector('[data-testid="flight-row"]', timeout=5000)

        page.click('[data-testid="flight-row"] [data-testid="reserve-button"]')
        page.fill('[data-testid="passenger-name"]', "Playwright Tester")
        page.click('[data-testid="confirm-submit"]')
        page.wait_for_selector('[data-testid="confirmation-id"]', state="visible", timeout=5000)

        reservation_id = page.text_content('[data-testid="confirmation-id"]')
        assert reservation_id
        reservation = requests.get(f"{API}/reservations/{reservation_id}", timeout=10)
        assert reservation.status_code == 200, reservation.text
        assert reservation.json()["status"] == "CONFIRMED"
        browser.close()


def test_r9_manager_panel():
    analytics = requests.get(
        f"{API}/analytics/occupancy",
        params={"route": "BOG-MDE", "month": "2024-01"},
        timeout=10,
    )
    if analytics.status_code == 404:
        pytest.skip("endpoint analytics no disponible aún")
    assert analytics.status_code == 200, analytics.text
    expected = analytics.json()["occupancy"] * 100

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{FRONT}/manager.html")
        page.fill('[data-testid="manager-route"]', "BOG-MDE")
        page.fill('[data-testid="manager-month"]', "2024-01")
        page.click('[data-testid="manager-load"]')
        page.wait_for_function(
            "() => document.querySelector('[data-testid=\"occupancy-value\"]').textContent.includes('%')",
            timeout=5000,
        )
        assert page.text_content('[data-testid="occupancy-value"]') == f"{expected:.3f}%"
        browser.close()
