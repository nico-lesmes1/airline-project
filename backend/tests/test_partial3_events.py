import json
from concurrent.futures import Future
from datetime import date, datetime, timezone

from app import live_view
from app.events import EventPublisher, reservation_event, search_event


class InlineExecutor:
    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)
        return future


class FakeKinesis:
    def __init__(self):
        self.records = []

    def put_record(self, **kwargs):
        self.records.append(kwargs)


def test_search_event_uses_session_partition_key_and_contract_envelope():
    event, partition_key = search_event(
        origin="bog",
        destination="mde",
        travel_date=date(2031, 3, 10),
        results_count=4,
        session_id="session-1",
    )

    assert partition_key == "session-1"
    assert event["event_type"] == "search_performed"
    assert event["schema_version"] == 1
    assert event["session_id"] == "session-1"
    assert event["origin"] == "BOG"
    assert event["destination"] == "MDE"
    assert event["travel_date"] == "2031-03-10"
    assert event["results_count"] == 4
    assert datetime.strptime(event["event_ts"], "%Y-%m-%dT%H:%M:%SZ")
    assert "passenger_name" not in event


def test_reservation_event_uses_flight_partition_key_and_excludes_personal_data():
    event, partition_key = reservation_event(
        "reservation_created",
        reservation_id="reservation-1",
        flight_id="flight-1",
        route="BOG-MDE",
        flight_date=date(2031, 3, 10),
        fare_class="ECONOMY",
        price_cents=125000,
    )

    assert partition_key == "flight-1"
    assert event["event_type"] == "reservation_created"
    assert event["flight_id"] == "flight-1"
    assert event["price_cents"] == 125000
    assert "passenger_name" not in event


def test_publisher_sends_json_to_configured_stream():
    publisher = EventPublisher()
    publisher.stream_name = "events"
    publisher._client = FakeKinesis()
    publisher._executor = InlineExecutor()
    event = {"event_id": "id-1", "event_type": "search_performed"}

    assert publisher.publish(event, "session-1")
    sent = publisher._client.records[0]
    assert sent["StreamName"] == "events"
    assert sent["PartitionKey"] == "session-1"
    assert json.loads(sent["Data"]) == event


def test_live_event_parser_rejects_bad_timestamp_and_accepts_utc_event():
    event = {
        "event_id": "id-1",
        "event_type": "search_performed",
        "event_ts": "2026-11-26T14:00:00Z",
        "schema_version": 1,
    }

    assert live_view.parse_live_event(event) == (
        "id-1",
        "search_performed",
        datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc),
    )
    assert live_view.parse_live_event({**event, "event_ts": "not-a-date"}) is None


def test_live_metrics_counts_event_types_and_conversion(monkeypatch):
    class Cursor:
        def execute(self, query, params):
            assert params[0] < params[1]

        def fetchall(self):
            return [
                {"event_type": "search_performed", "event_count": 10},
                {"event_type": "reservation_created", "event_count": 3},
                {"event_type": "reservation_cancelled", "event_count": 1},
            ]

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(live_view, "get_connection", Connection)
    monkeypatch.setattr(live_view, "release_connection", lambda connection: None)

    assert live_view.live_metrics(5) == {
        "window_minutes": 5,
        "searches": 10,
        "reservations": 3,
        "cancellations": 1,
        "conversion": 0.3,
    }
