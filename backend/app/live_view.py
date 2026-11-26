import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import boto3
import psycopg2
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.db import get_connection, release_connection


logger = logging.getLogger(__name__)
_EVENT_TYPES = {"search_performed", "reservation_created", "reservation_cancelled"}
_TABLE = "live_stream_events"


def parse_live_event(event: dict):
    event_id = event.get("event_id")
    event_type = event.get("event_type")
    event_ts = event.get("event_ts")
    if not isinstance(event_id, str) or not event_id or event_type not in _EVENT_TYPES:
        return None
    if event.get("schema_version") != 1 or not isinstance(event_ts, str):
        return None
    try:
        parsed_ts = datetime.strptime(event_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return event_id, event_type, parsed_ts


def ensure_live_table() -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(91002)")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_ts TIMESTAMPTZ NOT NULL
            )
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_event_ts ON {_TABLE} (event_ts)"
        )
        conn.commit()
        cur.close()
    finally:
        release_connection(conn)


def live_metrics(window_minutes: int) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)
    counts = {event_type: 0 for event_type in _EVENT_TYPES}
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT event_type, COUNT(*) AS event_count
            FROM {_TABLE}
            WHERE event_ts >= %s AND event_ts <= %s
            GROUP BY event_type
            """,
            (cutoff, now),
        )
        for row in cur.fetchall():
            counts[row["event_type"]] = int(row["event_count"])
        cur.close()
    finally:
        release_connection(conn)

    searches = counts["search_performed"]
    reservations = counts["reservation_created"]
    return {
        "window_minutes": window_minutes,
        "searches": searches,
        "reservations": reservations,
        "cancellations": counts["reservation_cancelled"],
        "conversion": reservations / searches if searches else 0.0,
    }


class KinesisLiveConsumer:
    def __init__(self):
        self.stream_name = os.getenv("KINESIS_STREAM_NAME")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        ensure_live_table()
        if not self.stream_name:
            logger.info("Live stream consumer disabled: KINESIS_STREAM_NAME is unset")
            return
        self._thread = threading.Thread(
            target=self._consume,
            name="kinesis-live-consumer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _consume(self) -> None:
        client = boto3.client(
            "kinesis",
            region_name=self.region,
            config=Config(
                connect_timeout=2,
                read_timeout=5,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )
        iterators = {}
        last_shard_refresh = 0.0
        last_cleanup = 0.0

        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if now - last_shard_refresh >= 30:
                    shards = client.list_shards(StreamName=self.stream_name)["Shards"]
                    for shard in shards:
                        shard_id = shard["ShardId"]
                        if shard_id not in iterators:
                            iterators[shard_id] = client.get_shard_iterator(
                                StreamName=self.stream_name,
                                ShardId=shard_id,
                                ShardIteratorType="TRIM_HORIZON",
                            )["ShardIterator"]
                    last_shard_refresh = now

                for shard_id, iterator in list(iterators.items()):
                    if iterator is None:
                        del iterators[shard_id]
                        continue
                    result = client.get_records(ShardIterator=iterator, Limit=1000)
                    iterators[shard_id] = result.get("NextShardIterator")
                    parsed = []
                    for record in result["Records"]:
                        try:
                            event = json.loads(record["Data"])
                        except (json.JSONDecodeError, UnicodeDecodeError) as error:
                            logger.warning("Ignoring invalid Kinesis event: %s", error)
                            continue
                        row = parse_live_event(event)
                        if row is None:
                            logger.warning("Ignoring Kinesis event with an invalid envelope")
                            continue
                        parsed.append(row)
                    if parsed:
                        self._persist(parsed)

                if time.monotonic() - last_cleanup >= 60:
                    self._delete_expired()
                    last_cleanup = time.monotonic()
            except (BotoCoreError, ClientError, psycopg2.Error):
                logger.exception("Kinesis live consumer iteration failed")
                self._stop.wait(2)
                continue
            self._stop.wait(1)

    @staticmethod
    def _persist(events) -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_advisory_xact_lock(91003)")
            cur.executemany(
                f"""
                INSERT INTO {_TABLE} (event_id, event_type, event_ts)
                VALUES (%s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                events,
            )
            conn.commit()
            cur.close()
        finally:
            release_connection(conn)

    @staticmethod
    def _delete_expired() -> None:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"DELETE FROM {_TABLE} WHERE event_ts < NOW() - INTERVAL '1 hour'"
            )
            conn.commit()
            cur.close()
        finally:
            release_connection(conn)


live_consumer = KinesisLiveConsumer()
