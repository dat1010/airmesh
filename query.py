#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path


LATEST_SQL = """
SELECT received_at,
       source_node,
       pm1_standard,
       pm25_standard,
       pm10_standard,
       rx_rssi,
       rx_snr
FROM air_quality_readings
ORDER BY received_at DESC
LIMIT ?;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query meshair SQLite readings.")
    parser.add_argument("--db", type=Path, default=Path("data/meshair.db"))
    parser.add_argument("command", choices=["latest", "count"])
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def print_latest(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(LATEST_SQL, (limit,)).fetchall()
    for row in rows:
        print(
            f"{row[0]} node={row[1]} PM1={row[2]} PM2.5={row[3]} "
            f"PM10={row[4]} RSSI={row[5]} SNR={row[6]}"
        )


def print_count(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT count(*) FROM air_quality_readings;").fetchone()[0]
    print(count)


def main() -> int:
    args = parse_args()
    with sqlite3.connect(args.db) as conn:
        if args.command == "latest":
            print_latest(conn, args.limit)
        else:
            print_count(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
