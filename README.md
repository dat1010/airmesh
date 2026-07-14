# meshair collector

Small Meshtastic air-quality collector and persistence process.

## Language choice

Python is the best fit right now because the collector is already Python, `paho-mqtt`
is simple, and `sqlite3` is in the standard library. Go would also be a good fit
later if you want a single static service binary, but it adds little value for
this first persistence step.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run Collector And Writer

This starts both halves:

```bash
python run_all.py \
  --port /dev/ttyACM0 \
  --mqtt-host localhost \
  --web \
  --jsonl data/airquality.jsonl \
  --db data/meshair.db
```

Flow:

```text
AQ nodes -> LoRa -> AQ2 over USB -> collector.py -> MQTT -> writer.py -> JSONL + SQLite
```

By default the collector stores telemetry from every node that sends supported
air-quality, environmental, or device metrics. To restrict collection, repeat
`--node`:

```bash
python run_all.py --port /dev/ttyACM0 --node 0x84f3f1a7 --web
```

## Run Separately

Terminal 1:

```bash
python collector.py \
  --port /dev/ttyACM0 \
  --mqtt-host localhost \
  --topic-prefix meshair
```

Terminal 2:

```bash
python writer.py \
  --mqtt-host localhost \
  --jsonl data/airquality.jsonl \
  --db data/meshair.db
```

The collector reads AQ node packets through AQ2 on USB and publishes normalized
telemetry to `meshair/nodes/<node>/telemetry`. The writer creates `data/`,
appends every matching MQTT payload to `data/airquality.jsonl`, and inserts
structured readings into `data/meshair.db`. The old `meshair/airquality/+` topic
is still accepted by the writer for compatibility with older collectors.

Duplicate packet IDs are ignored in SQLite using a unique index on
`(source_node, packet_id)`. The raw JSONL log still records every received
payload.

## Query

```bash
python query.py latest --db data/meshair.db --limit 10
python query.py count --db data/meshair.db
```

Or use SQLite directly:

```bash
sqlite3 data/meshair.db \
  "select received_at, source_node, pm1_standard, pm25_standard, pm10_standard, temperature_c, relative_humidity, barometric_pressure from air_quality_readings order by received_at desc limit 10;"
```

## Web UI

Start the dashboard:

```bash
python web.py --host 0.0.0.0 --port 8055 --db data/meshair.db
```

Or include it with the combined runner:

```bash
python run_all.py --port /dev/ttyACM0 --web
```

Open:

```text
http://192.168.1.22:8055/
```

The page refreshes every 10 seconds and also exposes:

```text
/api/summary
/api/readings?limit=250
/health
```

## Docker

On the Ubuntu server, `network_mode: host` lets the container reach Mosquitto at
`localhost:1883`. The Compose service runs the writer only; run the collector on
the host when using `/dev/ttyACM0`.

```bash
docker compose up --build
```

## Verify

Watch MQTT:

```bash
mosquitto_sub -h localhost -t 'meshair/#' -v
```

Watch saved raw payloads:

```bash
tail -f data/airquality.jsonl
```

Show latest stored readings:

```bash
python query.py latest --db data/meshair.db --limit 10
```
