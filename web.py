#!/usr/bin/env python3
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>meshair</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #10110f;
      --panel: #191b17;
      --panel-2: #20231d;
      --line: #353b30;
      --text: #f4f0e6;
      --muted: #a9ad9e;
      --accent: #d7ff5f;
      --cyan: #6ee7d8;
      --rose: #ff8f70;
      --gold: #ffd166;
      --shadow: rgba(0, 0, 0, 0.32);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 18% 12%, rgba(215, 255, 95, 0.12), transparent 28rem),
        radial-gradient(circle at 84% 8%, rgba(110, 231, 216, 0.10), transparent 22rem),
        linear-gradient(135deg, #10110f, #151912 48%, #0f1312);
      color: var(--text);
      font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono", "Liberation Mono", monospace;
    }

    .shell {
      width: min(1180px, calc(100% - 28px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }

    header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      padding: 20px 0 24px;
      border-bottom: 1px solid var(--line);
    }

    h1 {
      margin: 0;
      font-size: clamp(2.25rem, 7vw, 5.6rem);
      line-height: 0.88;
      letter-spacing: 0;
      text-transform: lowercase;
    }

    .subtitle {
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.5;
    }

    .status {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      color: var(--muted);
      white-space: nowrap;
    }

    .pulse {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 8px rgba(215, 255, 95, 0.08);
    }

    .metric-groups {
      display: grid;
      gap: 14px;
      margin: 22px 0;
    }

    .metric-group {
      display: grid;
      gap: 12px;
    }

    .group-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      min-height: 24px;
    }

    .group-meta {
      color: var(--muted);
      font-size: 0.82rem;
      text-align: right;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }

    .tile,
    .chart,
    .table-wrap {
      background: color-mix(in srgb, var(--panel) 88%, black);
      border: 1px solid var(--line);
      box-shadow: 0 18px 60px var(--shadow);
    }

    .tile {
      min-height: 128px;
      padding: 18px;
      border-radius: 6px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .label {
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .value {
      margin-top: 18px;
      display: flex;
      align-items: baseline;
      gap: 0.35rem;
      min-width: 0;
      font-size: clamp(1.9rem, 3.2vw, 3rem);
      line-height: 1;
      font-weight: 800;
      white-space: nowrap;
    }

    .unit {
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 500;
      flex: 0 0 auto;
    }

    .chart {
      border-radius: 6px;
      padding: 18px;
      min-height: 300px;
    }

    .chart-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }

    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-size: 0.82rem;
    }

    .key::before {
      content: "";
      display: inline-block;
      width: 9px;
      height: 9px;
      margin-right: 7px;
      background: var(--key);
      vertical-align: 1px;
    }

    svg {
      display: block;
      width: 100%;
      height: 230px;
      overflow: visible;
    }

    .grid-line { stroke: rgba(244, 240, 230, 0.12); stroke-width: 1; }
    .axis-label { fill: var(--muted); font-size: 11px; }
    .series { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }

    .table-wrap {
      margin-top: 12px;
      border-radius: 6px;
      overflow: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }

    th,
    td {
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 0.9rem;
    }

    th {
      color: var(--muted);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: var(--panel-2);
      position: sticky;
      top: 0;
    }

    tr:last-child td { border-bottom: 0; }
    .numeric { text-align: right; font-variant-numeric: tabular-nums; }
    .empty { color: var(--muted); padding: 22px 14px; }

    @media (max-width: 820px) {
      header { grid-template-columns: 1fr; align-items: start; }
      .status { justify-content: flex-start; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .group-head { display: block; }
      .group-meta { margin-top: 8px; text-align: left; }
    }

    @media (max-width: 520px) {
      .shell { width: min(100% - 18px, 1180px); padding-top: 12px; }
      .metrics { grid-template-columns: 1fr; }
      .chart-head { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>meshair</h1>
        <p class="subtitle">AQ1 air-quality and environmental readings captured over Meshtastic and stored locally.</p>
      </div>
      <div class="status"><span class="pulse"></span><span id="statusText">loading</span></div>
    </header>

    <section class="metric-groups" aria-label="Latest readings">
      <div class="metric-group">
        <div class="group-head">
          <div class="label">Air Quality</div>
          <div class="group-meta" id="airMeta">Waiting for PM packet</div>
        </div>
        <div class="metrics">
          <article class="tile"><div class="label">PM1.0</div><div class="value"><span id="pm1">--</span><span class="unit">ug/m3</span></div></article>
          <article class="tile"><div class="label">PM2.5</div><div class="value"><span id="pm25">--</span><span class="unit">ug/m3</span></div></article>
          <article class="tile"><div class="label">PM10</div><div class="value"><span id="pm10">--</span><span class="unit">ug/m3</span></div></article>
        </div>
      </div>

      <div class="metric-group">
        <div class="group-head">
          <div class="label">Environment</div>
          <div class="group-meta" id="envMeta">Waiting for environment packet</div>
        </div>
        <div class="metrics">
          <article class="tile"><div class="label">Temp</div><div class="value"><span id="temp">--</span><span class="unit">C</span></div></article>
          <article class="tile"><div class="label">Humidity</div><div class="value"><span id="humidity">--</span><span class="unit">%</span></div></article>
          <article class="tile"><div class="label">Pressure</div><div class="value"><span id="pressure">--</span><span class="unit">hPa</span></div></article>
        </div>
      </div>
    </section>

    <section class="chart" aria-label="Recent trend">
      <div class="chart-head">
        <div>
          <div class="label">Recent Trend</div>
          <div class="subtitle" id="latestMeta">Waiting for readings</div>
        </div>
        <div class="legend">
          <span class="key" style="--key: var(--accent)">PM1</span>
          <span class="key" style="--key: var(--cyan)">PM2.5</span>
          <span class="key" style="--key: var(--rose)">PM10</span>
        </div>
      </div>
      <svg id="chart" role="img" aria-label="PM trend chart"></svg>
    </section>

    <section class="table-wrap" aria-label="Latest readings">
      <table>
        <thead>
          <tr>
            <th>Received</th>
            <th>Type</th>
            <th class="numeric">Node</th>
            <th class="numeric">PM1</th>
            <th class="numeric">PM2.5</th>
            <th class="numeric">PM10</th>
            <th class="numeric">Temp</th>
            <th class="numeric">Humidity</th>
            <th class="numeric">Pressure</th>
          </tr>
        </thead>
        <tbody id="rows"><tr><td class="empty" colspan="9">Loading readings</td></tr></tbody>
      </table>
    </section>
  </main>

  <script>
    const state = { readings: [], count: 0 };

    function fmtTime(value) {
      if (!value) return "--";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return date.toLocaleString();
    }

    function setText(id, value) {
      document.getElementById(id).textContent = value ?? "--";
    }

    function latestValue(key) {
      return state.readings.find((reading) => reading[key] !== null && reading[key] !== undefined)?.[key];
    }

    function latestReadingWith(...keys) {
      return state.readings.find((reading) =>
        keys.some((key) => reading[key] !== null && reading[key] !== undefined)
      );
    }

    function fmtNumber(value, digits = 1) {
      if (value === null || value === undefined || value === "") return "--";
      const number = Number(value);
      if (!Number.isFinite(number)) return "--";
      return number.toFixed(digits).replace(/\\.0$/, "");
    }

    function readingType(reading) {
      if (["pm1_standard", "pm25_standard", "pm10_standard"].some((key) => reading[key] !== null && reading[key] !== undefined)) {
        return "air";
      }
      if (["temperature_c", "relative_humidity", "barometric_pressure"].some((key) => reading[key] !== null && reading[key] !== undefined)) {
        return "env";
      }
      if (["battery_level", "voltage", "uptime_seconds"].some((key) => reading[key] !== null && reading[key] !== undefined)) {
        return "device";
      }
      return "telemetry";
    }

    function renderTiles() {
      const latestAir = latestReadingWith(
        "pm1_standard",
        "pm25_standard",
        "pm10_standard"
      );
      const latestEnv = latestReadingWith(
        "temperature_c",
        "relative_humidity",
        "barometric_pressure"
      );
      setText("pm1", latestValue("pm1_standard"));
      setText("pm25", latestValue("pm25_standard"));
      setText("pm10", latestValue("pm10_standard"));
      setText("temp", fmtNumber(latestValue("temperature_c")));
      setText("humidity", fmtNumber(latestValue("relative_humidity")));
      setText("pressure", fmtNumber(latestValue("barometric_pressure")));

      document.getElementById("airMeta").textContent = latestAir
        ? `${fmtTime(latestAir.received_at)} | node ${latestAir.source_node}`
        : "Waiting for PM packet";
      document.getElementById("envMeta").textContent = latestEnv
        ? `${fmtTime(latestEnv.received_at)} | node ${latestEnv.source_node}`
        : "Waiting for environment packet";

      const latest = latestAir || latestEnv;
      if (latest) {
        document.getElementById("latestMeta").textContent =
          `${fmtTime(latest.received_at)} | node ${latest.source_node} | ${state.count} saved readings`;
        document.getElementById("statusText").textContent = "live from SQLite";
      } else {
        document.getElementById("latestMeta").textContent = "Waiting for readings";
        document.getElementById("statusText").textContent = "no readings yet";
      }
    }

    function renderRows() {
      const body = document.getElementById("rows");
      if (!state.readings.length) {
        body.innerHTML = '<tr><td class="empty" colspan="9">No readings saved yet</td></tr>';
        return;
      }

      body.innerHTML = state.readings.slice(0, 40).map((reading) => `
        <tr>
          <td>${fmtTime(reading.received_at)}</td>
          <td>${readingType(reading)}</td>
          <td class="numeric">${reading.source_node}</td>
          <td class="numeric">${reading.pm1_standard ?? "--"}</td>
          <td class="numeric">${reading.pm25_standard ?? "--"}</td>
          <td class="numeric">${reading.pm10_standard ?? "--"}</td>
          <td class="numeric">${fmtNumber(reading.temperature_c)}</td>
          <td class="numeric">${fmtNumber(reading.relative_humidity)}</td>
          <td class="numeric">${fmtNumber(reading.barometric_pressure)}</td>
        </tr>
      `).join("");
    }

    function pointsFor(readings, key, width, height, pad) {
      const values = readings.map((reading) => Number(reading[key])).filter(Number.isFinite);
      const maxValue = Math.max(10, ...values);
      return readings.map((reading, index) => {
        const value = Number(reading[key]);
        if (!Number.isFinite(value)) return null;
        const x = pad + (index * (width - pad * 2)) / Math.max(1, readings.length - 1);
        const y = height - pad - (value / maxValue) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).filter(Boolean).join(" ");
    }

    function renderChart() {
      const svg = document.getElementById("chart");
      const readings = [...state.readings]
        .reverse()
        .filter((reading) => ["pm1_standard", "pm25_standard", "pm10_standard"].some((key) => reading[key] !== null && reading[key] !== undefined))
        .slice(-60);
      const width = 900;
      const height = 230;
      const pad = 28;
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

      if (readings.length < 2) {
        svg.innerHTML = '<text x="28" y="118" class="axis-label">Waiting for at least two readings</text>';
        return;
      }

      const grid = [0, 1, 2, 3].map((step) => {
        const y = pad + step * ((height - pad * 2) / 3);
        return `<line class="grid-line" x1="${pad}" x2="${width - pad}" y1="${y}" y2="${y}"></line>`;
      }).join("");

      svg.innerHTML = `
        ${grid}
        <polyline class="series" stroke="var(--accent)" points="${pointsFor(readings, "pm1_standard", width, height, pad)}"></polyline>
        <polyline class="series" stroke="var(--cyan)" points="${pointsFor(readings, "pm25_standard", width, height, pad)}"></polyline>
        <polyline class="series" stroke="var(--rose)" points="${pointsFor(readings, "pm10_standard", width, height, pad)}"></polyline>
      `;
    }

    async function refresh() {
      try {
        const [summary, readings] = await Promise.all([
          fetch("/api/summary").then((response) => response.json()),
          fetch("/api/readings?limit=80").then((response) => response.json()),
        ]);
        state.count = summary.count ?? 0;
        state.readings = readings.readings ?? [];
        renderTiles();
        renderRows();
        renderChart();
      } catch (error) {
        document.getElementById("statusText").textContent = "web read failed";
      }
    }

    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>
"""


READINGS_SQL = """
SELECT received_at,
       source_node,
       source_node_id,
       pm1_standard,
       pm25_standard,
       pm10_standard,
       pm1_environmental,
       pm25_environmental,
       pm10_environmental,
       temperature_c,
       relative_humidity,
       barometric_pressure,
       gas_resistance,
       voltage,
       current,
       battery_level,
       channel_utilization,
       air_util_tx,
       uptime_seconds,
       rx_snr,
       rx_rssi,
       hop_limit,
       packet_id
FROM air_quality_readings
ORDER BY received_at DESC
LIMIT ?;
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def clamp_limit(value: str | None, default: int = 80, maximum: int = 500) -> int:
    if value is None:
        return default
    try:
        return max(1, min(maximum, int(value)))
    except ValueError:
        return default


def query_readings(db_path: Path, limit: int) -> list[dict]:
    if not db_path.exists():
        return []

    try:
        with open_db(db_path) as conn:
            return [dict(row) for row in conn.execute(READINGS_SQL, (limit,)).fetchall()]
    except sqlite3.Error:
        return []


def query_summary(db_path: Path) -> dict:
    if not db_path.exists():
        return {"count": 0, "latest_received_at": None, "server_time": utc_now_iso()}

    try:
        with open_db(db_path) as conn:
            row = conn.execute(
                "SELECT count(*) AS count, max(received_at) AS latest_received_at "
                "FROM air_quality_readings;"
            ).fetchone()
    except sqlite3.Error:
        return {"count": 0, "latest_received_at": None, "server_time": utc_now_iso()}

    return {
        "count": row["count"],
        "latest_received_at": row["latest_received_at"],
        "server_time": utc_now_iso(),
    }


class MeshairHandler(BaseHTTPRequestHandler):
    db_path: Path

    def log_message(self, format, *args):
        return

    def send_body(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_body(status, "application/json; charset=utf-8", body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_body(HTTPStatus.OK, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
            return

        if parsed.path == "/health":
            self.send_json({"ok": True, "db_exists": self.db_path.exists()})
            return

        if parsed.path == "/api/summary":
            self.send_json(query_summary(self.db_path))
            return

        if parsed.path == "/api/readings":
            params = parse_qs(parsed.query)
            limit = clamp_limit((params.get("limit") or [None])[0])
            self.send_json({"readings": query_readings(self.db_path, limit)})
            return

        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a local web UI for meshair readings.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8055)
    parser.add_argument("--db", type=Path, default=Path("data/meshair.db"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    handler = type("ConfiguredMeshairHandler", (MeshairHandler,), {"db_path": args.db})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"web UI listening on http://{args.host}:{args.port} using {args.db}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
