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
  --aq1 0x84f3f1a7 \
  --mqtt-host localhost \
  --web \
  --jsonl data/airquality.jsonl \
  --db data/meshair.db
```

Flow:

```text
AQ1 -> LoRa -> AQ2 over USB -> collector.py -> MQTT -> writer.py -> JSONL + SQLite
```

## Run Separately

Terminal 1:

```bash
python collector.py \
  --port /dev/ttyACM0 \
  --aq1 0x84f3f1a7 \
  --mqtt-host localhost \
  --topic-prefix meshair
```

Terminal 2:

```bash
python writer.py \
  --mqtt-host localhost \
  --topic 'meshair/airquality/+' \
  --jsonl data/airquality.jsonl \
  --db data/meshair.db
```

The collector reads AQ1 packets through AQ2 on USB and publishes normalized
air-quality messages to MQTT. The writer creates `data/`, appends every matching
MQTT payload to `data/airquality.jsonl`, and inserts structured readings into
`data/meshair.db`.

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
  "select received_at, source_node, pm1_standard, pm25_standard, pm10_standard, rx_rssi, rx_snr from air_quality_readings order by received_at desc limit 10;"
```

## Web UI

Start the dashboard:

```bash
python web.py --host 0.0.0.0 --port 8080 --db data/meshair.db
```

Or include it with the combined runner:

```bash
python run_all.py --port /dev/ttyACM0 --aq1 0x84f3f1a7 --web
```

Open:

```text
http://192.168.1.22:8080/
```

The page refreshes every 10 seconds and also exposes:

```text
/api/summary
/api/readings?limit=80
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
