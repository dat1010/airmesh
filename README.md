# meshair writer

Small persistence process for Meshtastic air-quality MQTT messages.

## Language choice

Python is the best fit right now because the collector is already Python, `paho-mqtt`
is simple, and `sqlite3` is in the standard library. Go would also be a good fit
later if you want a single static service binary, but it adds little value for
this first persistence step.

## Run locally

```bash
python -m pip install -r requirements.txt

python writer.py \
  --mqtt-host localhost \
  --topic 'meshair/airquality/+' \
  --jsonl data/airquality.jsonl \
  --db data/meshair.db
```

The writer creates `data/`, appends every MQTT payload to `data/airquality.jsonl`,
and inserts structured readings into `data/meshair.db`.

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

## Docker

On the Ubuntu server, `network_mode: host` lets the container reach Mosquitto at
`localhost:1883`.

```bash
docker compose up --build
```
