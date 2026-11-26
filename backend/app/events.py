import json
import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


logger = logging.getLogger(__name__)
_PUBLISH_TIMEOUT = float(os.getenv("KINESIS_PUBLISH_TIMEOUT_SECONDS", "1"))


def _event_envelope(event_type: str, **fields) -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "event_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": 1,
        **fields,
    }


def search_event(origin: str, destination: str, travel_date, results_count: int,
                 session_id: str | None = None) -> tuple[dict, str]:
    sid = session_id or str(uuid4())
    return (
        _event_envelope(
            "search_performed",
            session_id=sid,
            origin=origin.upper(),
            destination=destination.upper(),
            travel_date=travel_date.isoformat(),
            results_count=results_count,
        ),
        sid,
    )


def reservation_event(event_type: str, reservation_id, flight_id: str, route: str,
                      flight_date, fare_class: str, price_cents: int) -> tuple[dict, str]:
    if event_type not in {"reservation_created", "reservation_cancelled"}:
        raise ValueError(f"Unsupported reservation event type: {event_type}")
    return (
        _event_envelope(
            event_type,
            reservation_id=str(reservation_id),
            flight_id=flight_id,
            route=route,
            flight_date=flight_date.isoformat(),
            fare_class=fare_class,
            price_cents=int(price_cents),
        ),
        flight_id,
    )


class EventPublisher:
    def __init__(self):
        self.stream_name = os.getenv("KINESIS_STREAM_NAME")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self._executor = ThreadPoolExecutor(
            max_workers=int(os.getenv("KINESIS_PUBLISH_WORKERS", "16")),
            thread_name_prefix="kinesis-publisher",
        )
        self._client = None

    def publish(self, event: dict, partition_key: str, wait_seconds: float = 0) -> bool:
        if not self.stream_name:
            logger.debug("Kinesis publication disabled: KINESIS_STREAM_NAME is unset")
            return False

        payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        future = self._executor.submit(self._put_record, payload, partition_key)
        future.add_done_callback(self._log_failure)
        if wait_seconds > 0:
            try:
                future.result(timeout=wait_seconds)
            except TimeoutError:
                logger.debug("Kinesis publication continues asynchronously after its short wait")
            except (BotoCoreError, ClientError) as error:
                logger.error("Kinesis event publication failed: %s", error)
        return True

    def _put_record(self, payload: bytes, partition_key: str) -> None:
        if self._client is None:
            self._client = boto3.client(
                "kinesis",
                region_name=self.region,
                config=Config(
                    connect_timeout=_PUBLISH_TIMEOUT,
                    read_timeout=_PUBLISH_TIMEOUT,
                    retries={"mode": "standard", "total_max_attempts": 2},
                    max_pool_connections=32,
                ),
            )
        self._client.put_record(
            StreamName=self.stream_name,
            Data=payload,
            PartitionKey=partition_key,
        )

    @staticmethod
    def _log_failure(future: Future) -> None:
        error = future.exception()
        if error is not None:
            logger.error(
                "Kinesis event publication failed: %s",
                error,
                exc_info=(type(error), error, error.__traceback__),
            )


publisher = EventPublisher()
