#!/usr/bin/env python3
import argparse
import json
import signal
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS air_quality_readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT NOT NULL,
  source_node INTEGER NOT NULL,
  source_node_id TEXT,
  mqtt_topic TEXT NOT NULL,

  pm1_standard INTEGER,
  pm25_standard INTEGER,
  pm10_standard INTEGER,

  pm1_environmental INTEGER,
  pm25_environmental INTEGER,
  pm10_environmental INTEGER,

  rx_snr REAL,
  rx_rssi INTEGER,
  hop_limit INTEGER,
  packet_id INTEGER,

  raw_json TEXT NOT NULL,

  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_air_quality_received_at
ON air_quality_readings(received_at);

CREATE INDEX IF NOT EXISTS idx_air_quality_source_time
ON air_quality_readings(source_node, received_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_air_quality_packet_id
ON air_quality_readings(source_node, packet_id);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def float_or_none(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def connect_db(db_path: Path) -> sqlite3.Connection:
    ensure_parent(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def source_id_from_topic(topic: str) -> str | None:
    parts = topic.rsplit("/", 1)
    if len(parts) != 2:
        return None
    return parts[1] or None


def reading_from_payload(topic: str, payload: bytes) -> dict:
    raw_text = payload.decode("utf-8")
    message = json.loads(raw_text)
    metrics = message.get("metrics") or {}

    source_node = int_or_none(message.get("source"))
    if source_node is None:
        source_node = int_or_none(message.get("from"))
    if source_node is None:
        source_node = int_or_none(source_id_from_topic(topic))
    if source_node is None:
        raise ValueError("payload does not include a numeric source node")

    return {
        "received_at": message.get("received_at") or utc_now_iso(),
        "source_node": source_node,
        "source_node_id": message.get("source_node_id") or source_id_from_topic(topic),
        "mqtt_topic": topic,
        "pm1_standard": int_or_none(metrics.get("pm1_standard")),
        "pm25_standard": int_or_none(metrics.get("pm25_standard")),
        "pm10_standard": int_or_none(metrics.get("pm10_standard")),
        "pm1_environmental": int_or_none(metrics.get("pm1_environmental")),
        "pm25_environmental": int_or_none(metrics.get("pm25_environmental")),
        "pm10_environmental": int_or_none(metrics.get("pm10_environmental")),
        "rx_snr": float_or_none(message.get("rx_snr")),
        "rx_rssi": int_or_none(message.get("rx_rssi")),
        "hop_limit": int_or_none(message.get("hop_limit")),
        "packet_id": int_or_none(message.get("id")),
        "raw_json": raw_text,
    }


def append_jsonl(jsonl_path: Path, raw_json: str) -> None:
    ensure_parent(jsonl_path)
    with jsonl_path.open("a", encoding="utf-8") as jsonl:
        jsonl.write(raw_json.rstrip("\n"))
        jsonl.write("\n")


def insert_reading(conn: sqlite3.Connection, reading: dict) -> bool:
    before = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO air_quality_readings (
          received_at,
          source_node,
          source_node_id,
          mqtt_topic,
          pm1_standard,
          pm25_standard,
          pm10_standard,
          pm1_environmental,
          pm25_environmental,
          pm10_environmental,
          rx_snr,
          rx_rssi,
          hop_limit,
          packet_id,
          raw_json
        ) VALUES (
          :received_at,
          :source_node,
          :source_node_id,
          :mqtt_topic,
          :pm1_standard,
          :pm25_standard,
          :pm10_standard,
          :pm1_environmental,
          :pm25_environmental,
          :pm10_environmental,
          :rx_snr,
          :rx_rssi,
          :hop_limit,
          :packet_id,
          :raw_json
        )
        """,
        reading,
    )
    conn.commit()
    return conn.total_changes > before


def format_saved_line(reading: dict, saved: bool) -> str:
    status = "saved" if saved else "duplicate"
    label = reading["source_node_id"] or "node"
    return (
        f"{reading['received_at']} {label}/{reading['source_node']} "
        f"PM1={reading['pm1_standard']} "
        f"PM2.5={reading['pm25_standard']} "
        f"PM10={reading['pm10_standard']} "
        f"RSSI={reading['rx_rssi']} "
        f"SNR={reading['rx_snr']} "
        f"{status}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist Meshtastic air-quality MQTT messages to JSONL and SQLite."
    )
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--topic", default="meshair/airquality/+")
    parser.add_argument("--jsonl", type=Path, default=Path("data/airquality.jsonl"))
    parser.add_argument("--db", type=Path, default=Path("data/meshair.db"))
    parser.add_argument("--client-id", default="meshair-writer")
    return parser.parse_args()


def main() -> int:
    import paho.mqtt.client as mqtt

    args = parse_args()
    conn = connect_db(args.db)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code:
            print(f"MQTT connect failed: {reason_code}", file=sys.stderr)
            return
        client.subscribe(args.topic)
        print(f"subscribed to {args.topic} on {args.mqtt_host}:{args.mqtt_port}")

    def on_message(client, userdata, message):
        try:
            reading = reading_from_payload(message.topic, message.payload)
            append_jsonl(args.jsonl, reading["raw_json"])
            saved = insert_reading(conn, reading)
            print(format_saved_line(reading, saved), flush=True)
        except Exception as exc:
            print(f"{utc_now_iso()} {message.topic} skipped: {exc}", file=sys.stderr)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.client_id,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.mqtt_host, args.mqtt_port)

    def shutdown(signum, frame):
        client.disconnect()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        client.loop_forever()
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
